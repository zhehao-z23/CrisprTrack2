#!/usr/bin/env python3
"""Derive one reproducible SPT displacement gate from movie metadata.

The production rule locks the motion prior globally and calibrates a single
radius for the complete acquisition.  It does not estimate D* per cell and it
does not enlarge the radius after a gap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

import tifffile


MODEL_VERSION = "v5.1.0-trajectory-coverage"
DEFAULT_D_STAR = 4.1e-3
DEFAULT_ANOMALOUS_EXPONENT = 0.38
DEFAULT_TRAJECTORY_COVERAGE = 0.975
DEFAULT_LOCALIZATION_ERROR_NM = 0.0
DEFAULT_ROUNDING_INCREMENT_PX = 0.05


def _resolution_value(value) -> float:
    if isinstance(value, tuple) and len(value) == 2:
        return float(value[0]) / float(value[1])
    return float(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_spatial_unit(unit: object) -> str:
    """Normalize explicit micron spellings without depending on console encoding."""
    value = re.sub(
        r"\\u(?:00b5|03bc)", "u", str(unit), flags=re.IGNORECASE
    ).lower()
    value = value.replace("\u00b5", "u").replace("\u03bc", "u")
    if value not in {"micron", "microns", "um"}:
        raise ValueError(f"TIFF spatial unit must explicitly be microns; found {unit!r}")
    return "um"


def read_tracking_metadata(tiff_path: Path) -> dict:
    """Read calibrated time and isotropic x/y pixel size from one channel TIFF."""
    tiff_path = Path(tiff_path).resolve()
    with tifffile.TiffFile(tiff_path) as tif:
        page = tif.pages[0]
        imagej = tif.imagej_metadata or {}
        description = page.description or ""

        frame_interval_s = imagej.get("finterval")
        if frame_interval_s is None:
            match = re.search(r"finterval=([0-9.eE+\-]+)", description)
            if not match:
                raise ValueError(f"finterval not found in TIFF metadata: {tiff_path}")
            frame_interval_s = float(match.group(1))
        frame_interval_s = float(frame_interval_s)
        if frame_interval_s <= 0:
            raise ValueError(f"finterval must be positive: {frame_interval_s}")

        if "XResolution" not in page.tags:
            raise ValueError(f"XResolution not found in TIFF metadata: {tiff_path}")
        x_resolution_px_per_um = _resolution_value(page.tags["XResolution"].value)
        y_resolution_px_per_um = (
            _resolution_value(page.tags["YResolution"].value)
            if "YResolution" in page.tags
            else x_resolution_px_per_um
        )
        pixel_size_x_um = 1.0 / x_resolution_px_per_um
        pixel_size_y_um = 1.0 / y_resolution_px_per_um
        if not math.isclose(pixel_size_x_um, pixel_size_y_um, rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError(
                "The scalar radial linker requires isotropic pixels; "
                f"found x={pixel_size_x_um} and y={pixel_size_y_um} um/px"
            )

        raw_unit = imagej.get("unit", "")
        try:
            unit = normalize_spatial_unit(raw_unit)
        except ValueError as error:
            raise ValueError(f"{error} in {tiff_path}") from error

        series = tif.series[0]
        axes = series.axes
        shape = tuple(int(value) for value in series.shape)
        frame_count = shape[axes.index("T")] if "T" in axes else len(tif.pages)
        return {
            "source_tiff": str(tiff_path),
            "frame_interval_s": frame_interval_s,
            "frame_rate_hz": 1.0 / frame_interval_s,
            "x_resolution_px_per_um": x_resolution_px_per_um,
            "y_resolution_px_per_um": y_resolution_px_per_um,
            "pixel_size_x_um_per_px": pixel_size_x_um,
            "pixel_size_y_um_per_px": pixel_size_y_um,
            "pixel_size_nm_per_px": pixel_size_x_um * 1000.0,
            "spatial_unit": unit,
            "frame_count": int(frame_count),
            "series_axes": axes,
            "series_shape": shape,
            "isotropic_pixels_verified": True,
        }


def validate_channel_metadata(channel_tiffs: dict[str, Path]) -> dict[str, dict]:
    """Require G/R/P TIFFs to share the calibration used by one scalar model."""
    metadata = {
        channel: read_tracking_metadata(path) for channel, path in channel_tiffs.items()
    }
    if not metadata:
        raise ValueError("At least one channel TIFF is required")
    canonical_channel = next(iter(metadata))
    canonical = metadata[canonical_channel]
    numeric_fields = (
        "frame_interval_s",
        "pixel_size_x_um_per_px",
        "pixel_size_y_um_per_px",
    )
    exact_fields = ("spatial_unit", "frame_count")
    for channel, item in metadata.items():
        for field in numeric_fields:
            if not math.isclose(item[field], canonical[field], rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError(
                    f"{channel} TIFF {field} differs from {canonical_channel}: "
                    f"{item[field]} != {canonical[field]}"
                )
        for field in exact_fields:
            if item[field] != canonical[field]:
                raise ValueError(
                    f"{channel} TIFF {field} differs from {canonical_channel}: "
                    f"{item[field]!r} != {canonical[field]!r}"
                )
    return metadata


def _validated_intervals(values: object, expected_count: int, source: str) -> list[float]:
    if not isinstance(values, list) or len(values) != expected_count:
        raise ValueError(
            f"{source} must contain exactly {expected_count} adjacent-frame intervals"
        )
    intervals = [float(value) for value in values]
    if any(not math.isfinite(value) or value <= 0 for value in intervals):
        raise ValueError(f"{source} contains a non-positive or non-finite interval")
    return intervals


def read_movie_intervals(
    metadata: dict,
    crop_metadata_sidecar: Path | None = None,
) -> tuple[list[float], dict]:
    """Prefer exact ND2 intervals in the crop sidecar; audit any uniform fallback."""
    frame_count = int(metadata["frame_count"])
    expected = frame_count - 1
    if expected < 1:
        raise ValueError("At least two movie frames are required to derive max_disp")

    if crop_metadata_sidecar is not None:
        path = Path(crop_metadata_sidecar).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Crop metadata sidecar not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        time_metadata = payload.get("time", {})
        raw_intervals = time_metadata.get("frame_intervals_s")
        method = "time.frame_intervals_s"
        if not raw_intervals:
            times = time_metadata.get("relative_time_s")
            if times is not None:
                if not isinstance(times, list) or len(times) != frame_count:
                    raise ValueError(
                        f"{path}:time.relative_time_s must contain {frame_count} timestamps"
                    )
                times = [float(value) for value in times]
                raw_intervals = [right - left for left, right in zip(times[:-1], times[1:])]
                method = "diff(time.relative_time_s)"
        if raw_intervals:
            intervals = _validated_intervals(raw_intervals, expected, f"{path}:{method}")
        else:
            representative = float(
                time_metadata.get("finterval_s") or metadata["frame_interval_s"]
            )
            if not math.isfinite(representative) or representative <= 0:
                raise ValueError(f"No valid timing interval is available in {path}")
            intervals = [representative] * expected
            return intervals, {
                "source": "uniform_sidecar_finterval_fallback",
                "method": "repeat sidecar/TIFF finterval for frame_count - 1 steps",
                "path": str(path),
                "sha256": _sha256(path),
                "source_nd2": payload.get("source_nd2"),
                "fallback_used": True,
                "warning": (
                    "The crop sidecar has no exact frame intervals/timestamps. "
                    "A representative interval was repeated explicitly."
                ),
            }
        return intervals, {
            "source": "exact_crop_sidecar",
            "method": method,
            "path": str(path),
            "sha256": _sha256(path),
            "source_nd2": payload.get("source_nd2"),
            "fallback_used": False,
        }

    representative = float(metadata["frame_interval_s"])
    intervals = [representative] * expected
    return intervals, {
        "source": "uniform_tiff_finterval_fallback",
        "method": "repeat TIFF finterval for frame_count - 1 steps",
        "path": None,
        "sha256": None,
        "source_nd2": None,
        "fallback_used": True,
        "warning": (
            "Exact crop sidecar was unavailable. The run remains reproducible, "
            "but it does not use per-frame ND2 timing jitter."
        ),
    }


def _variance_terms(
    frame_intervals_s: list[float],
    diffusion_coefficient_um2_per_s_alpha: float,
    anomalous_exponent: float,
    localization_error_um: float,
) -> list[float]:
    if diffusion_coefficient_um2_per_s_alpha < 0 or localization_error_um < 0:
        raise ValueError("diffusion coefficient and localization error cannot be negative")
    if not 0 < anomalous_exponent <= 2:
        raise ValueError("anomalous_exponent must be in (0, 2]")
    if not frame_intervals_s:
        raise ValueError("At least one adjacent-frame interval is required")
    terms = [
        diffusion_coefficient_um2_per_s_alpha * interval**anomalous_exponent
        + localization_error_um**2
        for interval in frame_intervals_s
    ]
    if any(term <= 0 for term in terms):
        raise ValueError("At least one modeled motion/localization variance term must be positive")
    return terms


def step_coverages(radius_um: float, variance_terms_um2: list[float]) -> list[float]:
    if radius_um < 0:
        raise ValueError("radius cannot be negative")
    return [
        -math.expm1(-(radius_um**2) / (4.0 * variance))
        for variance in variance_terms_um2
    ]


def whole_trajectory_coverage(radius_um: float, variance_terms_um2: list[float]) -> float:
    coverages = step_coverages(radius_um, variance_terms_um2)
    if any(value <= 0 for value in coverages):
        return 0.0
    return math.exp(sum(math.log(value) for value in coverages))


def solve_trajectory_radius(
    variance_terms_um2: list[float], target_coverage: float
) -> float:
    if not 0 < target_coverage < 1:
        raise ValueError("trajectory_coverage_probability must be in (0, 1)")
    lower = 0.0
    upper = math.sqrt(max(variance_terms_um2))
    while whole_trajectory_coverage(upper, variance_terms_um2) < target_coverage:
        upper *= 2.0
    for _ in range(100):
        middle = (lower + upper) / 2.0
        if whole_trajectory_coverage(middle, variance_terms_um2) < target_coverage:
            lower = middle
        else:
            upper = middle
    return upper


def ceil_to_increment(value: float, increment: float) -> float:
    if increment <= 0:
        raise ValueError("rounding increment must be positive")
    return math.ceil((value - 1e-12) / increment) * increment


def derive_from_metadata(
    metadata: dict,
    *,
    diffusion_coefficient_um2_per_s_alpha: float = DEFAULT_D_STAR,
    anomalous_exponent: float = DEFAULT_ANOMALOUS_EXPONENT,
    trajectory_coverage_probability: float = DEFAULT_TRAJECTORY_COVERAGE,
    localization_error_nm: float = DEFAULT_LOCALIZATION_ERROR_NM,
    rounding_increment_px: float = DEFAULT_ROUNDING_INCREMENT_PX,
    track_mem: int = 3,
    explicit_max_step_px: float | None = None,
    frame_intervals_s: list[float] | None = None,
    timing_provenance: dict | None = None,
) -> dict:
    """Combine movie timing and locked priors into one operational max_disp."""
    pixel_size_um = float(metadata["pixel_size_x_um_per_px"])
    if pixel_size_um <= 0:
        raise ValueError("pixel size must be positive")
    if frame_intervals_s is None:
        frame_count = int(metadata.get("frame_count", 2))
        frame_intervals_s = [float(metadata["frame_interval_s"])] * (frame_count - 1)
        timing_provenance = timing_provenance or {
            "source": "uniform_metadata_fallback",
            "fallback_used": True,
        }
    frame_intervals_s = [float(value) for value in frame_intervals_s]
    variance_terms = _variance_terms(
        frame_intervals_s,
        diffusion_coefficient_um2_per_s_alpha,
        anomalous_exponent,
        localization_error_nm / 1000.0,
    )
    theoretical_radius_um = solve_trajectory_radius(
        variance_terms, trajectory_coverage_probability
    )
    theoretical_radius_px = theoretical_radius_um / pixel_size_um
    modeled_px = ceil_to_increment(theoretical_radius_px, rounding_increment_px)
    if explicit_max_step_px is not None:
        if explicit_max_step_px <= 0:
            raise ValueError("explicit_max_step_px must be positive")
        operational_px = float(explicit_max_step_px)
        operational_source = "explicit CLI override"
    else:
        operational_px = modeled_px
        operational_source = "locked prior + movie timing + trajectory coverage + upward rounding"

    operational_um = operational_px * pixel_size_um
    operational_step_coverages = step_coverages(operational_um, variance_terms)
    achieved_trajectory_coverage = whole_trajectory_coverage(
        operational_um, variance_terms
    )
    n_steps = len(frame_intervals_s)
    equivalent_step_target = trajectory_coverage_probability ** (1.0 / n_steps)
    return {
        "version": MODEL_VERSION,
        "formula": (
            "p_i(r)=1-exp[-r^2/(4*(D_star*dt_i^alpha+sigma_loc^2))]; "
            "Q(r)=product_i p_i(r); solve Q(r)=Q_target; "
            "max_step_px=ceil_increment(r/pixel_size_um)"
        ),
        "metadata": metadata,
        "timing": {
            "provenance": timing_provenance or {},
            "adjacent_interval_count": n_steps,
            "frame_intervals_s": frame_intervals_s,
            "minimum_interval_s": min(frame_intervals_s),
            "median_interval_s": statistics.median(frame_intervals_s),
            "mean_interval_s": sum(frame_intervals_s) / n_steps,
            "maximum_interval_s": max(frame_intervals_s),
        },
        "physical_prior": {
            "diffusion_coefficient_D_star_um2_per_s_alpha": diffusion_coefficient_um2_per_s_alpha,
            "anomalous_exponent_alpha": anomalous_exponent,
            "localization_error_per_frame_per_axis_nm": localization_error_nm,
            "D_star_policy": "locked global prior; no per-cell or per-ND2 refit",
        },
        "coverage_policy": {
            "scope": "complete acquisition adjacent-frame transitions",
            "target_whole_trajectory_no_exceedance_probability": trajectory_coverage_probability,
            "one_sided_at_least_one_exceedance_probability": 1.0 - trajectory_coverage_probability,
            "equivalent_uniform_per_step_coverage": equivalent_step_target,
            "independence_assumption": True,
        },
        "calculation": {
            "theoretical_radius_um": theoretical_radius_um,
            "theoretical_radius_nm": theoretical_radius_um * 1000.0,
            "theoretical_radius_px": theoretical_radius_px,
        },
        "rounding_policy": {"mode": "ceiling", "increment_px": rounding_increment_px},
        "modeled_max_step_px": modeled_px,
        "explicit_max_step_px": explicit_max_step_px,
        "operational_source": operational_source,
        "operational_max_step_px": operational_px,
        "operational_max_step_um": operational_um,
        "operational_max_step_nm": operational_um * 1000.0,
        "achieved_trajectory_coverage": achieved_trajectory_coverage,
        "achieved_step_coverage": {
            "minimum": min(operational_step_coverages),
            "mean": sum(operational_step_coverages) / n_steps,
            "maximum": max(operational_step_coverages),
            "expected_exceeding_steps_per_trajectory": sum(
                1.0 - value for value in operational_step_coverages
            ),
        },
        "tracker_implementation": {
            "track_mem": track_mem,
            "maximum_detection_frame_gap": track_mem + 1,
            "gap_scaled_radius_implemented": False,
            "rule": "the same movie-level scalar max_disp is used after every permitted gap",
        },
    }


def derive_from_tiff(
    tiff_path: Path,
    *,
    crop_metadata_sidecar: Path | None = None,
    **kwargs,
) -> dict:
    metadata = read_tracking_metadata(tiff_path)
    intervals, provenance = read_movie_intervals(metadata, crop_metadata_sidecar)
    return derive_from_metadata(
        metadata,
        frame_intervals_s=intervals,
        timing_provenance=provenance,
        **kwargs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tiff", type=Path)
    parser.add_argument("--crop-metadata-sidecar", type=Path)
    parser.add_argument("--d-star", type=float, default=DEFAULT_D_STAR)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ANOMALOUS_EXPONENT)
    parser.add_argument(
        "--trajectory-coverage",
        type=float,
        default=DEFAULT_TRAJECTORY_COVERAGE,
    )
    parser.add_argument("--localization-error-nm", type=float, default=0.0)
    parser.add_argument("--rounding-increment-px", type=float, default=0.05)
    parser.add_argument("--track-mem", type=int, default=3)
    parser.add_argument("--max-step-px", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = derive_from_tiff(
        args.tiff,
        crop_metadata_sidecar=args.crop_metadata_sidecar,
        diffusion_coefficient_um2_per_s_alpha=args.d_star,
        anomalous_exponent=args.alpha,
        trajectory_coverage_probability=args.trajectory_coverage,
        localization_error_nm=args.localization_error_nm,
        rounding_increment_px=args.rounding_increment_px,
        track_mem=args.track_mem,
        explicit_max_step_px=args.max_step_px,
    )
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
