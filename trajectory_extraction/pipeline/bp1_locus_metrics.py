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


@dataclass(frozen=True)
class BP1SegmentationParameters:
    """Frozen, sensitivity-first component-generation settings.

    These are engineering parameters for producing reviewable component
    candidates.  They are not a biological 53BP1-positive/negative classifier.
    """

    gaussian_sigma_px: float = 1.0
    threshold_robust_z: float = 2.5
    minimum_component_area_px: int = 3
    lineage_dilation_px: int = 1

    def validate(self) -> None:
        if self.gaussian_sigma_px < 0:
            raise ValueError("gaussian_sigma_px must be non-negative")
        if self.threshold_robust_z <= 0:
            raise ValueError("threshold_robust_z must be positive")
        if self.minimum_component_area_px < 1:
            raise ValueError("minimum_component_area_px must be >= 1")
        if self.lineage_dilation_px < 0:
            raise ValueError("lineage_dilation_px must be non-negative")


def _robust_threshold(
    image: np.ndarray, nucleus_mask: np.ndarray, robust_z: float
) -> tuple[float, float, float, str]:
    values = np.asarray(image[nucleus_mask], dtype=float)
    if values.size == 0:
        return math.nan, math.nan, math.nan, "NO_NUCLEAR_BACKGROUND"
    location = float(np.median(values))
    scale = 1.4826 * float(np.median(np.abs(values - location)))
    method = "MEDIAN_MAD"
    if not np.isfinite(scale) or scale <= 0:
        scale = float(np.std(values))
        method = "MEDIAN_STD_FALLBACK"
    if not np.isfinite(scale) or scale <= 0:
        return math.nan, location, scale, "ZERO_BACKGROUND_SCALE"
    return location + robust_z * scale, location, scale, method


def _joined_ids(values: Iterable[int]) -> str:
    return ";".join(str(value) for value in sorted(set(int(item) for item in values)))


def _assign_focus_lineages(
    labels: np.ndarray, object_rows: list[dict[str, object]], dilation_px: int
) -> None:
    """Track components using reciprocal maximum adjacent-frame mask overlap.

    There is deliberately no centroid fallback, gap closing, interpolation, or
    use of a DNA trajectory.  Split/merge edges are retained in the audit even
    when the dominant reciprocal branch keeps its track identity.
    """

    if not object_rows:
        return
    assignments: dict[tuple[int, int], dict[str, object]] = {}
    children: dict[tuple[int, int], set[int]] = {}
    child_tracks: dict[tuple[int, int], set[int]] = {}
    next_track = 1
    for object_id in (int(value) for value in np.unique(labels[0]) if int(value) > 0):
        assignments[(1, object_id)] = {
            "focus_track_id": next_track,
            "lineage_event": "NEW",
            "previous_frame_object_ids": "",
            "parent_focus_track_ids": "",
            "overlap_px_previous": 0,
            "dilated_overlap_px_previous": 0,
        }
        next_track += 1

    structure = ndimage.generate_binary_structure(2, 1)
    for frame_index in range(1, labels.shape[0]):
        frame = frame_index + 1
        previous_frame = frame - 1
        previous_ids = [int(value) for value in np.unique(labels[frame_index - 1]) if int(value) > 0]
        current_ids = [int(value) for value in np.unique(labels[frame_index]) if int(value) > 0]
        previous_masks = {value: labels[frame_index - 1] == value for value in previous_ids}
        current_masks = {value: labels[frame_index] == value for value in current_ids}
        previous_dilated = {
            value: ndimage.binary_dilation(mask, structure=structure, iterations=dilation_px)
            if dilation_px else mask
            for value, mask in previous_masks.items()
        }
        current_dilated = {
            value: ndimage.binary_dilation(mask, structure=structure, iterations=dilation_px)
            if dilation_px else mask
            for value, mask in current_masks.items()
        }
        previous_to_current = {value: set() for value in previous_ids}
        current_to_previous = {value: set() for value in current_ids}
        overlaps: dict[tuple[int, int], tuple[int, int]] = {}
        for previous_id, previous_mask in previous_masks.items():
            for current_id, current_mask in current_masks.items():
                direct = int(np.count_nonzero(previous_mask & current_mask))
                dilated = int(np.count_nonzero(previous_dilated[previous_id] & current_dilated[current_id]))
                if direct <= 0 and dilated <= 0:
                    continue
                previous_to_current[previous_id].add(current_id)
                current_to_previous[current_id].add(previous_id)
                overlaps[(previous_id, current_id)] = (direct, dilated)

        def unique_best(candidates: Iterable[int], score) -> int | None:
            candidates = sorted(candidates)
            if not candidates:
                return None
            values = {candidate: score(candidate) for candidate in candidates}
            best = max(values.values())
            winners = [candidate for candidate, value in values.items() if value == best]
            return winners[0] if len(winners) == 1 else None

        for current_id in current_ids:
            parents = current_to_previous[current_id]
            parent_tracks = {
                int(assignments[(previous_frame, parent)]["focus_track_id"])
                for parent in parents
            }
            primary_parent = unique_best(
                parents, lambda parent: overlaps[(parent, current_id)]
            )
            reciprocal = primary_parent is not None and unique_best(
                previous_to_current[primary_parent],
                lambda child: overlaps[(primary_parent, child)],
            ) == current_id
            if reciprocal:
                track_id = int(assignments[(previous_frame, primary_parent)]["focus_track_id"])
                has_merge = len(parents) > 1
                has_split = len(previous_to_current[primary_parent]) > 1
                event = (
                    "CONTINUE_COMPLEX" if has_merge and has_split else
                    "CONTINUE_THROUGH_MERGE" if has_merge else
                    "CONTINUE_THROUGH_SPLIT" if has_split else "CONTINUE"
                )
                parent_track_text = _joined_ids(parent_tracks - {track_id})
            else:
                track_id = next_track
                next_track += 1
                parent_track_text = _joined_ids(parent_tracks)
                if not parents:
                    event = "NEW"
                elif len(parents) > 1 and any(len(previous_to_current[parent]) > 1 for parent in parents):
                    event = "COMPLEX_CHILD"
                elif len(parents) > 1:
                    event = "MERGE_CHILD"
                else:
                    event = "SPLIT_CHILD"
            assignments[(frame, current_id)] = {
                "focus_track_id": track_id,
                "lineage_event": event,
                "previous_frame_object_ids": _joined_ids(parents),
                "parent_focus_track_ids": parent_track_text,
                "overlap_px_previous": sum(overlaps[(parent, current_id)][0] for parent in parents),
                "dilated_overlap_px_previous": sum(overlaps[(parent, current_id)][1] for parent in parents),
            }
            for parent in parents:
                children.setdefault((previous_frame, parent), set()).add(current_id)
                child_tracks.setdefault((previous_frame, parent), set()).add(track_id)

    track_frames: dict[int, set[int]] = {}
    for row in object_rows:
        key = (int(row["frame"]), int(row["object_id"]))
        assignment = assignments[key]
        row.update(assignment)
        track_id = int(assignment["focus_track_id"])
        row["next_frame_object_ids"] = _joined_ids(children.get(key, set()))
        row["child_focus_track_ids"] = _joined_ids(
            child_tracks.get(key, set()) - {track_id}
        )
        track_frames.setdefault(track_id, set()).add(int(row["frame"]))
    for row in object_rows:
        frames = track_frames[int(row["focus_track_id"])]
        row["focus_track_first_frame"] = min(frames)
        row["focus_track_last_frame"] = max(frames)
        row["focus_track_length_frames"] = len(frames)


def segment_focus_stack(
    stack: np.ndarray,
    nucleus_masks: np.ndarray,
    pixel_size_nm: float,
    parameters: BP1SegmentationParameters | None = None,
) -> tuple[np.ndarray, list[dict[str, object]], list[dict[str, object]]]:
    """Segment all eligible per-frame Green components and assign lineages."""

    parameters = parameters or BP1SegmentationParameters()
    parameters.validate()
    if stack.ndim != 3 or nucleus_masks.shape != stack.shape:
        raise ValueError("stack and nucleus_masks must be matching TYX arrays")
    if pixel_size_nm <= 0:
        raise ValueError("pixel_size_nm must be positive")
    labels = np.zeros(stack.shape, dtype=np.uint16)
    frame_rows: list[dict[str, object]] = []
    object_rows: list[dict[str, object]] = []
    dtype_max = np.iinfo(stack.dtype).max if np.issubdtype(stack.dtype, np.integer) else math.nan
    for frame_index, (raw_image, nucleus) in enumerate(zip(stack, nucleus_masks, strict=True)):
        frame = frame_index + 1
        nucleus = np.asarray(nucleus, dtype=bool)
        smoothed = ndimage.gaussian_filter(raw_image.astype(float), parameters.gaussian_sigma_px)
        threshold, background, scale, method = _robust_threshold(
            smoothed, nucleus, parameters.threshold_robust_z
        )
        foreground = (smoothed > threshold) & nucleus if np.isfinite(threshold) else np.zeros(nucleus.shape, bool)
        raw_labels, raw_count = ndimage.label(foreground)
        sizes = np.bincount(raw_labels.ravel(), minlength=raw_count + 1)
        eligible = [value for value in range(1, raw_count + 1) if sizes[value] >= parameters.minimum_component_area_px]
        nucleus_edge = nucleus & ~ndimage.binary_erosion(nucleus, iterations=1)
        for object_id, source_id in enumerate(eligible, start=1):
            component = raw_labels == source_id
            labels[frame_index][component] = object_id
            yy, xx = np.nonzero(component)
            values = raw_image[component].astype(float)
            weights = np.maximum(values - background, 0.0)
            centroid_y = float(np.average(yy, weights=weights)) if weights.sum() > 0 else float(np.mean(yy))
            centroid_x = float(np.average(xx, weights=weights)) if weights.sum() > 0 else float(np.mean(xx))
            area = int(values.size)
            y_min, y_max = int(yy.min()), int(yy.max())
            x_min, x_max = int(xx.min()), int(xx.max())
            object_rows.append({
                "frame": frame,
                "object_id": object_id,
                "source_threshold_component_id": source_id,
                "area_px": area,
                "area_um2": area * (pixel_size_nm / 1000.0) ** 2,
                "equivalent_radius_nm": math.sqrt(area / math.pi) * pixel_size_nm,
                "centroid_x_px": centroid_x,
                "centroid_y_px": centroid_y,
                "centroid_x_nm": (centroid_x + 1.0) * pixel_size_nm,
                "centroid_y_nm": (centroid_y + 1.0) * pixel_size_nm,
                "bbox_x_min_px": x_min,
                "bbox_x_max_px": x_max,
                "bbox_y_min_px": y_min,
                "bbox_y_max_px": y_max,
                "mean_intensity_au": float(values.mean()),
                "median_intensity_au": float(np.median(values)),
                "maximum_intensity_au": float(values.max()),
                "integrated_excess_intensity_au": float(np.sum(values - background)),
                "dtype_saturated_pixel_fraction": float(np.mean(values >= dtype_max)) if np.isfinite(dtype_max) else None,
                "touches_nucleus_boundary": bool(np.any(component & nucleus_edge)),
                "touches_image_boundary": bool(y_min == 0 or x_min == 0 or y_max == raw_image.shape[0] - 1 or x_max == raw_image.shape[1] - 1),
            })
        frame_rows.append({
            "frame": frame,
            "segmentation_status": "VALID" if np.isfinite(threshold) else method,
            "segmentation_gaussian_sigma_px": parameters.gaussian_sigma_px,
            "segmentation_threshold_au": finite_or_none(threshold),
            "nuclear_background_median_au": finite_or_none(background),
            "robust_background_scale_au": finite_or_none(scale),
            "threshold_method": method,
            "threshold_robust_z": parameters.threshold_robust_z,
            "nucleus_area_px": int(nucleus.sum()),
            "raw_threshold_component_count": int(raw_count),
            "eligible_component_count": len(eligible),
            "raw_foreground_area_px": int(foreground.sum()),
            "eligible_foreground_area_px": int(np.count_nonzero(labels[frame_index])),
        })
    _assign_focus_lineages(labels, object_rows, parameters.lineage_dilation_px)
    return labels, frame_rows, object_rows


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
