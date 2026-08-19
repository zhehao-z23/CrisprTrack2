#!/usr/bin/env python3
"""Continuous, locus-centred 53BP1 intensity and focus-distance metrics.

The intensity branch and the segmented-component branch are deliberately
independent:

* intensity is measured for every valid DNA-locus observation and is never
  thresholded into a positive/negative call;
* a segmented 53BP1 component is assigned only when it is uniquely within a
  fixed distance of the DNA locus;
* missing, distant, or ambiguous components receive distance score zero while
  the raw nearest-component audit remains available.

Coordinates use the repository pixel-centre contract: image arrays are
zero-based, x is column, y is row, and the origin is upper-left.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import ndimage
from skimage import measure


@dataclass(frozen=True)
class BP1MetricParameters:
    """Frozen v5.2 defaults for the DSB Site2/P-centred readout."""

    intensity_radius_nm: float = 1700.0
    background_inner_radius_nm: float = 2000.0
    background_outer_radius_nm: float = 3000.0
    association_boundary_cutoff_nm: float = 1000.0
    ambiguity_margin_nm: float = 250.0
    candidate_harvest_radius_nm: float = 3000.0
    core_minimum_valid_fraction: float = 0.8
    background_minimum_valid_fraction: float = 0.5

    def validate(self) -> None:
        if self.intensity_radius_nm <= 0:
            raise ValueError("intensity_radius_nm must be positive")
        if self.background_inner_radius_nm <= self.intensity_radius_nm:
            raise ValueError("background must start outside the intensity aperture")
        if self.background_outer_radius_nm <= self.background_inner_radius_nm:
            raise ValueError("background outer radius must exceed inner radius")
        if self.association_boundary_cutoff_nm <= 0:
            raise ValueError("association boundary cutoff must be positive")
        if self.candidate_harvest_radius_nm < self.association_boundary_cutoff_nm:
            raise ValueError("candidate harvest radius must cover association cutoff")
        if self.ambiguity_margin_nm < 0:
            raise ValueError("ambiguity margin must be non-negative")
        for name, value in (
            ("core_minimum_valid_fraction", self.core_minimum_valid_fraction),
            ("background_minimum_valid_fraction", self.background_minimum_valid_fraction),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


def finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def clipped_distance_score(
    unsigned_boundary_distance_nm: float | None,
    cutoff_nm: float,
    *,
    uniquely_assigned: bool,
) -> float:
    """Return a fail-closed proximity score in [0, 1].

    A locus inside a component has unsigned boundary distance zero and score
    one.  The score decreases linearly to zero at the cutoff.  A missing,
    distant, or ambiguous component has score zero.
    """

    if not uniquely_assigned or unsigned_boundary_distance_nm is None:
        return 0.0
    distance = float(unsigned_boundary_distance_nm)
    if not np.isfinite(distance) or distance < 0 or cutoff_nm <= 0:
        return 0.0
    return float(np.clip(1.0 - distance / float(cutoff_nm), 0.0, 1.0))


def _point_to_polyline_distance(
    x_px: float, y_px: float, contours: list[np.ndarray]
) -> float:
    point = np.asarray([y_px, x_px], dtype=float)
    best = math.inf
    for contour in contours:
        if len(contour) == 1:
            best = min(best, float(np.linalg.norm(point - contour[0])))
            continue
        starts = contour[:-1]
        ends = contour[1:]
        vectors = ends - starts
        denominator = np.sum(vectors * vectors, axis=1)
        numerator = np.sum((point - starts) * vectors, axis=1)
        fractions = np.divide(
            numerator,
            denominator,
            out=np.zeros_like(numerator),
            where=denominator > 0,
        )
        fractions = np.clip(fractions, 0.0, 1.0)
        projections = starts + fractions[:, None] * vectors
        best = min(best, float(np.min(np.linalg.norm(projections - point, axis=1))))
    return best


def signed_boundary_distance_nm(
    label_image: np.ndarray,
    object_id: int,
    x_px: float,
    y_px: float,
    pixel_size_nm: float,
) -> tuple[float, bool]:
    """Distance to a component contour; negative inside and positive outside."""

    if label_image.ndim != 2:
        raise ValueError("label_image must be 2D")
    if pixel_size_nm <= 0:
        raise ValueError("pixel_size_nm must be positive")
    if not np.isfinite(x_px) or not np.isfinite(y_px):
        return math.nan, False
    if not (
        0.0 <= x_px <= label_image.shape[1] - 1
        and 0.0 <= y_px <= label_image.shape[0] - 1
    ):
        return math.nan, False
    component = label_image == int(object_id)
    contours = measure.find_contours(component.astype(np.uint8), 0.5)
    if not contours:
        return math.nan, False
    distance_px = _point_to_polyline_distance(x_px, y_px, contours)
    inside = bool(
        ndimage.map_coordinates(
            component.astype(np.uint8),
            np.asarray([[y_px], [x_px]], dtype=float),
            order=0,
            mode="constant",
            cval=0,
            prefilter=False,
        )[0]
    )
    signed_nm = (-distance_px if inside else distance_px) * pixel_size_nm
    return float(signed_nm), inside


def associate_component(
    label_image: np.ndarray,
    object_ids: Iterable[int],
    x_px: float,
    y_px: float,
    pixel_size_nm: float,
    parameters: BP1MetricParameters,
) -> dict[str, object]:
    """Assign the uniquely nearest eligible component and calculate its score."""

    parameters.validate()
    candidates: list[dict[str, object]] = []
    for object_id in sorted(set(int(value) for value in object_ids if int(value) > 0)):
        signed_nm, inside = signed_boundary_distance_nm(
            label_image, object_id, x_px, y_px, pixel_size_nm
        )
        unsigned_nm = 0.0 if inside else signed_nm
        if np.isfinite(unsigned_nm) and unsigned_nm <= parameters.candidate_harvest_radius_nm:
            candidates.append(
                {
                    "object_id": object_id,
                    "signed_boundary_distance_nm": float(signed_nm),
                    "unsigned_boundary_distance_nm": float(unsigned_nm),
                    "inside": bool(inside),
                }
            )
    candidates.sort(
        key=lambda item: (
            float(item["unsigned_boundary_distance_nm"]),
            int(item["object_id"]),
        )
    )
    base: dict[str, object] = {
        "assignment_status": "NO_BP1_COMPONENT_IN_HARVEST_DOMAIN",
        "assigned_object_id": None,
        "nearest_candidate_object_id": None,
        "nearest_candidate_signed_boundary_distance_nm": None,
        "nearest_candidate_unsigned_boundary_distance_nm": None,
        "second_candidate_margin_nm": None,
        "candidate_count_in_harvest_domain": len(candidates),
        "candidate_count_within_association_gate": 0,
        "site2_to_bp1_signed_boundary_distance_nm": None,
        "site2_inside_bp1": None,
        "site2_bp1_distance_score": 0.0,
    }
    if not candidates:
        return base

    nearest = candidates[0]
    base.update(
        {
            "nearest_candidate_object_id": int(nearest["object_id"]),
            "nearest_candidate_signed_boundary_distance_nm": float(
                nearest["signed_boundary_distance_nm"]
            ),
            "nearest_candidate_unsigned_boundary_distance_nm": float(
                nearest["unsigned_boundary_distance_nm"]
            ),
        }
    )
    associated = [
        candidate
        for candidate in candidates
        if float(candidate["unsigned_boundary_distance_nm"])
        <= parameters.association_boundary_cutoff_nm
    ]
    base["candidate_count_within_association_gate"] = len(associated)
    if not associated:
        base["assignment_status"] = "NO_ASSOCIATED_FOCUS"
        return base

    selected = associated[0]
    margin_nm = (
        float(associated[1]["unsigned_boundary_distance_nm"])
        - float(selected["unsigned_boundary_distance_nm"])
        if len(associated) > 1
        else math.inf
    )
    base["second_candidate_margin_nm"] = finite_or_none(margin_nm)
    if margin_nm < parameters.ambiguity_margin_nm:
        base["assignment_status"] = "AMBIGUOUS_ASSIGNMENT"
        return base

    unsigned_nm = float(selected["unsigned_boundary_distance_nm"])
    base.update(
        {
            "assignment_status": "VALID",
            "assigned_object_id": int(selected["object_id"]),
            "site2_to_bp1_signed_boundary_distance_nm": float(
                selected["signed_boundary_distance_nm"]
            ),
            "site2_inside_bp1": bool(selected["inside"]),
            "site2_bp1_distance_score": clipped_distance_score(
                unsigned_nm,
                parameters.association_boundary_cutoff_nm,
                uniquely_assigned=True,
            ),
        }
    )
    return base


def measure_continuous_intensity(
    image: np.ndarray,
    nucleus_mask: np.ndarray,
    segmented_foreground: np.ndarray,
    x_px: float,
    y_px: float,
    pixel_size_nm: float,
    parameters: BP1MetricParameters,
) -> dict[str, object]:
    """Measure a continuous non-negative Site2-centred 53BP1 enrichment score.

    The primary score is the background-normalized excess clipped only at its
    physical floor of zero.  No positive/negative intensity threshold is used.
    Signed audit values are retained alongside the non-negative score.
    """

    parameters.validate()
    if image.ndim != 2 or nucleus_mask.shape != image.shape:
        raise ValueError("image and nucleus_mask must be matching 2D arrays")
    if segmented_foreground.shape != image.shape:
        raise ValueError("segmented_foreground must match image")
    if pixel_size_nm <= 0:
        raise ValueError("pixel_size_nm must be positive")

    empty: dict[str, object] = {
        "site2_bp1_aperture_mean_au": None,
        "site2_bp1_aperture_sum_au": None,
        "site2_bp1_local_background_median_au": None,
        "site2_bp1_background_subtracted_mean_au": None,
        "site2_bp1_background_subtracted_sum_au": None,
        "site2_bp1_nonnegative_excess_mean_au": None,
        "site2_bp1_nonnegative_excess_sum_au": None,
        "site2_bp1_local_excess_ratio": None,
        "site2_bp1_continuous_intensity_score": None,
        "intensity_aperture_nominal_pixel_count": 0,
        "intensity_aperture_valid_pixel_count": 0,
        "intensity_background_nominal_pixel_count": 0,
        "intensity_background_valid_pixel_count": 0,
        "intensity_aperture_valid_fraction": 0.0,
        "intensity_background_valid_fraction": 0.0,
        "intensity_metric_valid": False,
        "intensity_missing_reason": "ANCHOR_OUTSIDE_IMAGE",
    }
    if (
        not np.isfinite(x_px)
        or not np.isfinite(y_px)
        or not (0.0 <= x_px <= image.shape[1] - 1)
        or not (0.0 <= y_px <= image.shape[0] - 1)
    ):
        return empty

    yy, xx = np.ogrid[: image.shape[0], : image.shape[1]]
    radius2 = (xx - x_px) ** 2 + (yy - y_px) ** 2
    core_px = parameters.intensity_radius_nm / pixel_size_nm
    inner_px = parameters.background_inner_radius_nm / pixel_size_nm
    outer_px = parameters.background_outer_radius_nm / pixel_size_nm
    aperture_nominal = radius2 <= core_px**2
    background_nominal = (radius2 > inner_px**2) & (radius2 <= outer_px**2)
    aperture = aperture_nominal & nucleus_mask
    background_in_nucleus = background_nominal & nucleus_mask
    background = background_in_nucleus & ~segmented_foreground

    aperture_fraction = float(aperture.sum() / max(1, aperture_nominal.sum()))
    background_fraction = float(background.sum() / max(1, background_nominal.sum()))
    aperture_mean = float(np.mean(image[aperture])) if aperture.any() else math.nan
    aperture_sum = float(np.sum(image[aperture])) if aperture.any() else math.nan
    background_median = (
        float(np.median(image[background])) if background.any() else math.nan
    )
    signed_mean = (
        aperture_mean - background_median
        if np.isfinite(aperture_mean) and np.isfinite(background_median)
        else math.nan
    )
    signed_sum = (
        signed_mean * int(aperture.sum()) if np.isfinite(signed_mean) else math.nan
    )
    ratio = (
        signed_mean / background_median
        if np.isfinite(signed_mean)
        and np.isfinite(background_median)
        and background_median > 0
        else math.nan
    )
    valid = (
        aperture_fraction >= parameters.core_minimum_valid_fraction
        and background_fraction >= parameters.background_minimum_valid_fraction
        and np.isfinite(ratio)
    )
    if aperture_fraction < parameters.core_minimum_valid_fraction:
        reason = "APERTURE_SUPPORT_INSUFFICIENT"
    elif background_fraction < parameters.background_minimum_valid_fraction:
        reason = "BACKGROUND_SUPPORT_INSUFFICIENT"
    elif not np.isfinite(background_median) or background_median <= 0:
        reason = "NONPOSITIVE_BACKGROUND"
    elif not np.isfinite(ratio):
        reason = "NONFINITE_INTENSITY"
    else:
        reason = ""

    return {
        "site2_bp1_aperture_mean_au": finite_or_none(aperture_mean),
        "site2_bp1_aperture_sum_au": finite_or_none(aperture_sum),
        "site2_bp1_local_background_median_au": finite_or_none(background_median),
        "site2_bp1_background_subtracted_mean_au": finite_or_none(signed_mean),
        "site2_bp1_background_subtracted_sum_au": finite_or_none(signed_sum),
        "site2_bp1_nonnegative_excess_mean_au": finite_or_none(
            max(0.0, signed_mean) if np.isfinite(signed_mean) else math.nan
        ),
        "site2_bp1_nonnegative_excess_sum_au": finite_or_none(
            max(0.0, signed_sum) if np.isfinite(signed_sum) else math.nan
        ),
        "site2_bp1_local_excess_ratio": finite_or_none(ratio),
        "site2_bp1_continuous_intensity_score": finite_or_none(
            max(0.0, ratio) if np.isfinite(ratio) else math.nan
        ),
        "intensity_aperture_nominal_pixel_count": int(aperture_nominal.sum()),
        "intensity_aperture_valid_pixel_count": int(aperture.sum()),
        "intensity_background_nominal_pixel_count": int(background_nominal.sum()),
        "intensity_background_valid_pixel_count": int(background.sum()),
        "intensity_aperture_valid_fraction": aperture_fraction,
        "intensity_background_valid_fraction": background_fraction,
        "intensity_metric_valid": bool(valid),
        "intensity_missing_reason": reason,
    }
