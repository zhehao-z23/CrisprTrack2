#!/usr/bin/env python3
"""Run v5 static anchor-ROI SPT and select a deterministic longest baseline."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
import scipy.io as sio
import tifffile
from scipy import ndimage
from skimage.draw import line
from skimage.morphology import convex_hull_image

import max_step_model
import experiment_profiles
import coordinate_system


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


VERSION = "v5.2.0"
HERE = Path(__file__).resolve().parent
MATLAB_DEPS = HERE / "matlab_deps"
CHANNELS = ("green", "red", "purple")
PREFIX = {"green": "G", "red": "R", "purple": "P"}
GAUSSIAN_FIT_BOX_SIZE_PX = 9
MIN_ROI_DILATION_PX = math.ceil(GAUSSIAN_FIT_BOX_SIZE_PX / 2)
REFERENCE_CONTINUITY_NM = {"purple": 500.0, "red": 750.0}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def matlab_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def locate_channel_tiffs(analysis_dir: Path) -> dict[str, Path]:
    green = sorted(analysis_dir.glob("*_green.tif"))
    if len(green) != 1:
        raise FileNotFoundError(
            f"Expected exactly one *_green.tif in {analysis_dir}, found {len(green)}"
        )
    stem = green[0].name[: -len("_green.tif")]
    paths = {channel: analysis_dir / f"{stem}_{channel}.tif" for channel in CHANNELS}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing channel TIFF(s): " + ", ".join(missing))
    return paths


def read_track_px(path: Path, pixel_size_nm: float) -> list[tuple[int, float, float]]:
    points = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            points.append(
                (
                    int(float(row["frame"])),
                    float(coordinate_system.automatic_nm_to_image_px(row["x_nm"], pixel_size_nm)),
                    float(coordinate_system.automatic_nm_to_image_px(row["y_nm"], pixel_size_nm)),
                )
            )
    return sorted(points)


def read_candidate_nm(path: Path) -> list[tuple[int, float, float]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            (int(float(row["frame"])), float(row["x_nm"]), float(row["y_nm"]))
            for row in csv.DictReader(handle)
        ]


def locus_number(path: Path) -> int:
    match = re.search(r"loci(\d+)", path.name)
    if not match:
        raise ValueError(f"Cannot parse locus number: {path}")
    return int(match.group(1))


def static_anchor_roi(
    anchor: list[tuple[int, float, float]],
    nucleus_support_2d: np.ndarray,
    dilation_px: int,
    geometry: str = "tube",
    maximum_reference_step_px: float | None = None,
) -> np.ndarray:
    """Build one static ROI from the complete anchor path."""
    if dilation_px < MIN_ROI_DILATION_PX:
        raise ValueError(
            f"ROI dilation must be >= {MIN_ROI_DILATION_PX} px so the "
            f"{GAUSSIAN_FIT_BOX_SIZE_PX}px-wide Gaussian fit box is not under-supported"
        )
    if geometry not in {"tube", "convex_hull", "validated_segment_convex_hull"}:
        raise ValueError(f"Unknown ROI geometry: {geometry}")
    if geometry == "validated_segment_convex_hull" and (
        maximum_reference_step_px is None or maximum_reference_step_px <= 0
    ):
        raise ValueError(
            "validated_segment_convex_hull requires a positive maximum_reference_step_px"
        )
    centerline = np.zeros_like(nucleus_support_2d, dtype=bool)
    ordered = sorted(anchor)
    points = [(int(round(y)), int(round(x))) for _frame, x, y in ordered]
    for y, x in points:
        if 0 <= y < centerline.shape[0] and 0 <= x < centerline.shape[1]:
            centerline[y, x] = True
    for index, ((y0, x0), (y1, x1)) in enumerate(zip(points[:-1], points[1:])):
        if geometry == "validated_segment_convex_hull":
            frame0, x0_float, y0_float = ordered[index]
            frame1, x1_float, y1_float = ordered[index + 1]
            step = float(np.hypot(x1_float - x0_float, y1_float - y0_float))
            if frame1 - frame0 != 1 or step > maximum_reference_step_px:
                continue
        rows, columns = line(y0, x0, y1, x1)
        valid = (
            (rows >= 0)
            & (rows < centerline.shape[0])
            & (columns >= 0)
            & (columns < centerline.shape[1])
        )
        centerline[rows[valid], columns[valid]] = True
    if geometry == "tube":
        roi_seed = centerline
    elif geometry == "convex_hull":
        roi_seed = convex_hull_image(centerline)
    else:
        roi_seed = np.zeros_like(centerline)
        segment_start = 0
        for index in range(len(ordered)):
            is_end = index == len(ordered) - 1
            if not is_end:
                frame0, x0, y0 = ordered[index]
                frame1, x1, y1 = ordered[index + 1]
                step = float(np.hypot(x1 - x0, y1 - y0))
                is_end = frame1 - frame0 != 1 or step > maximum_reference_step_px
            if not is_end:
                continue
            segment_mask = np.zeros_like(centerline)
            segment = ordered[segment_start:index + 1]
            segment_points = [
                (int(round(y)), int(round(x))) for _frame, x, y in segment
            ]
            for y, x in segment_points:
                if 0 <= y < segment_mask.shape[0] and 0 <= x < segment_mask.shape[1]:
                    segment_mask[y, x] = True
            for (y0, x0), (y1, x1) in zip(segment_points[:-1], segment_points[1:]):
                rows, columns = line(y0, x0, y1, x1)
                valid = (
                    (rows >= 0) & (rows < segment_mask.shape[0])
                    & (columns >= 0) & (columns < segment_mask.shape[1])
                )
                segment_mask[rows[valid], columns[valid]] = True
            roi_seed |= convex_hull_image(segment_mask)
            segment_start = index + 1
    return ndimage.binary_dilation(
        roi_seed, iterations=dilation_px
    ) & nucleus_support_2d


def static_anchor_union(
    anchor: list[tuple[int, float, float]],
    nucleus_support_2d: np.ndarray,
    dilation_px: int,
) -> np.ndarray:
    """Backward-compatible name for the original tube ROI."""
    return static_anchor_roi(
        anchor,
        nucleus_support_2d,
        dilation_px,
        geometry="tube",
    )


def partition_channels(worker_count: int, channels: tuple[str, ...] = CHANNELS) -> list[list[str]]:
    groups = [[] for _ in range(min(worker_count, len(channels)))]
    for index, channel in enumerate(channels):
        groups[index % len(groups)].append(channel)
    return groups


def matlab_group_command(
    channels: list[str],
    tiffs: dict[str, Path],
    roi_path: Path,
    frame_rate: float,
    pixel_um: float,
    output_dir: Path,
    save_filter_images: bool,
    max_step_px: float,
) -> str:
    keep = "true" if save_filter_images else "false"
    calls = "; ".join(
        f"spt_batch_anchor_roi('{matlab_quote(tiffs[channel])}', "
        f"'{matlab_quote(roi_path)}', {frame_rate:.17g}, {pixel_um:.17g}, "
        f"'{matlab_quote(output_dir)}', {keep}, {max_step_px:.17g})"
        for channel in channels
    )
    return (
        f"addpath('{matlab_quote(MATLAB_DEPS)}','-begin'); "
        f"addpath('{matlab_quote(HERE)}','-begin'); {calls}"
    )


def run_matlab_group(
    channels: list[str],
    *,
    matlab_bin: str,
    **kwargs,
) -> tuple[list[str], int, str, float]:
    started = time.perf_counter()
    command = matlab_group_command(channels, **kwargs)
    result = subprocess.run(
        [matlab_bin, "-batch", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(
        part for part in (result.stdout.rstrip(), result.stderr.rstrip()) if part
    )
    return channels, result.returncode, output, time.perf_counter() - started


def run_locus_spt(
    *,
    tiffs: dict[str, Path],
    roi_path: Path,
    frame_rate: float,
    pixel_um: float,
    output_dir: Path,
    matlab_bin: str,
    matlab_workers: int,
    save_filter_images: bool,
    max_step_px: float,
    log_path: Path,
    channels: tuple[str, ...] = CHANNELS,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = partition_channels(matlab_workers, channels)
    common = {
        "tiffs": tiffs,
        "roi_path": roi_path,
        "frame_rate": frame_rate,
        "pixel_um": pixel_um,
        "output_dir": output_dir,
        "save_filter_images": save_filter_images,
        "max_step_px": max_step_px,
    }
    results = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(groups)) as executor:
        pending = {
            executor.submit(
                run_matlab_group,
                group,
                matlab_bin=matlab_bin,
                **common,
            )
            for group in groups
        }
        while pending:
            completed, pending = wait(pending, timeout=60, return_when=FIRST_COMPLETED)
            if not completed:
                print(
                    f"  MATLAB still running: {len(pending)} process(es), "
                    f"{time.perf_counter() - started:.0f} s elapsed",
                    flush=True,
                )
                continue
            for future in completed:
                results.append(future.result())

    failures = []
    with log_path.open("w", encoding="utf-8") as log:
        for channels, returncode, output, elapsed in results:
            label = ",".join(channels)
            block = f"--- MATLAB {label} ({elapsed:.1f} s) ---\n{output}\n"
            print(block)
            log.write(block)
            if returncode:
                failures.append((label, returncode))
    if failures:
        raise RuntimeError(
            "MATLAB SPT failed: "
            + ", ".join(f"{label}=exit {code}" for label, code in failures)
        )


def export_candidates(tiffs: dict[str, Path], matlab_dir: Path) -> list[Path]:
    csv_dir = matlab_dir / "matlab_trajectory"
    csv_dir.mkdir(exist_ok=True)
    for prefix in PREFIX.values():
        for stale in csv_dir.glob(f"{prefix}_m2DGaussian_traj*.csv"):
            stale.unlink()

    outputs = []
    for channel, tiff in tiffs.items():
        mat_path = matlab_dir / f"{tiff.stem}.mat"
        if not mat_path.is_file():
            raise FileNotFoundError(mat_path)
        mat = sio.loadmat(str(mat_path))
        trajectory_struct = mat["traj"]
        pixel_nm = float(mat["sptpara"][0, 0]["pixl"].flat[0]) * 1000.0
        exported = 0
        for item in trajectory_struct.flat:
            try:
                positions = item["pos"]
            except (IndexError, TypeError, ValueError):
                continue
            if positions.shape == (1, 1):
                positions = positions[0, 0]
            if positions.ndim != 2 or positions.shape[0] == 0 or positions.shape[1] < 3:
                continue
            exported += 1
            path = csv_dir / f"{PREFIX[channel]}_m2DGaussian_traj{exported}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["frame", "x_nm", "y_nm"])
                for x, y, frame in positions[:, :3]:
                    x_nm = coordinate_system.matlab_one_based_px_to_automatic_nm(x, pixel_nm)
                    y_nm = coordinate_system.matlab_one_based_px_to_automatic_nm(y, pixel_nm)
                    writer.writerow([int(frame), f"{float(x_nm):.2f}", f"{float(y_nm):.2f}"])
            outputs.append(path)
    return outputs


def candidate_audit(
    path: Path,
    *,
    allele_index: int,
    anchor_locus: int,
    channel: str,
    roi: np.ndarray,
    pixel_size_nm: float,
    profile: experiment_profiles.ExperimentProfile,
) -> dict:
    points = read_candidate_nm(path)
    frames = np.asarray([point[0] for point in points], dtype=int)
    xy_nm = np.asarray([[point[1], point[2]] for point in points], dtype=float)
    x_px, y_px = coordinate_system.automatic_nm_to_image_xy(
        xy_nm[:, 0], xy_nm[:, 1], pixel_size_nm
    )
    xy_px = np.column_stack([x_px, y_px])
    frame_diffs = np.diff(frames)
    step_px = np.linalg.norm(np.diff(xy_px, axis=0), axis=1) if len(points) > 1 else np.array([])
    inside = []
    for x, y in xy_px:
        xi, yi = int(round(x)), int(round(y))
        inside.append(0 <= yi < roi.shape[0] and 0 <= xi < roi.shape[1] and bool(roi[yi, xi]))
    span = int(frames[-1] - frames[0] + 1)
    trajectory_match = re.search(r"traj(\d+)", path.stem)
    channel_spec = profile.channel_from_prefix(channel)
    return {
        "experiment_profile": profile.name,
        "allele_index": allele_index,
        "anchor_locus": anchor_locus,
        "channel": channel,
        "corrected_channel": channel_spec.corrected_channel,
        "raw_channel_index": channel_spec.raw_index,
        "marker": channel_spec.marker,
        "marker_slug": channel_spec.marker_slug,
        "site_id": channel_spec.site_id,
        "genomic_locus": channel_spec.genomic_locus,
        "fluorophore": channel_spec.fluorophore,
        "candidate_number": int(trajectory_match.group(1)) if trajectory_match else 0,
        "candidate_csv": str(path.resolve()),
        "points": len(points),
        "first_frame": int(frames[0]),
        "last_frame": int(frames[-1]),
        "frame_span": span,
        "temporal_coverage_fraction": len(points) / span,
        "maximum_missing_frames_between_points": int(np.max(frame_diffs - 1)) if len(frame_diffs) else 0,
        "median_step_px": float(np.median(step_px)) if len(step_px) else 0.0,
        "p95_step_px": float(np.percentile(step_px, 95)) if len(step_px) else 0.0,
        "inside_static_roi_fraction": float(np.mean(inside)),
    }


def longest_sort_key(row: dict) -> tuple:
    """Deterministic baseline: points, span, earliest start, candidate number."""
    return (-row["points"], -row["frame_span"], row["first_frame"], row["candidate_number"])


def select_longest_baselines(
    candidate_rows: list[dict],
    baseline_dir: Path,
    allele_anchors: list[tuple[int, int]],
    profile: experiment_profiles.ExperimentProfile,
) -> tuple[list[dict], list[dict]]:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for stale in baseline_dir.glob("*.csv"):
        stale.unlink()
    selected_rows = []
    audit_rows = []
    for allele_index, anchor_locus in allele_anchors:
        for channel in PREFIX.values():
            channel_spec = profile.channel_from_prefix(channel)
            pool = [
                row
                for row in candidate_rows
                if row["allele_index"] == allele_index and row["channel"] == channel
            ]
            if not pool:
                audit_rows.append(
                    {
                        "experiment_profile": profile.name,
                        "allele_index": allele_index,
                        "anchor_locus": anchor_locus,
                        "channel": channel,
                        "corrected_channel": channel_spec.corrected_channel,
                        "raw_channel_index": channel_spec.raw_index,
                        "marker": channel_spec.marker,
                        "marker_slug": channel_spec.marker_slug,
                        "site_id": channel_spec.site_id,
                        "genomic_locus": channel_spec.genomic_locus,
                        "fluorophore": channel_spec.fluorophore,
                        "candidate_count": 0,
                        "selection_status": "no candidate; no baseline output",
                        "selected_candidate_csv": "",
                        "selected_points": 0,
                        "selected_frame_span": 0,
                        "baseline_csv": "",
                    }
                )
                continue
            selected = sorted(pool, key=longest_sort_key)[0]
            destination = baseline_dir / (
                f"allele_{allele_index:03d}_{channel_spec.marker_slug}_longest_spt_cleaned.csv"
            )
            shutil.copy2(selected["candidate_csv"], destination)
            baseline = {
                **selected,
                "selection_rule": "maximum points; tie: maximum frame span, earliest first frame, lowest candidate number",
                "cleaned_definition": "automatic ROI-restricted SPT baseline selected by the declared longest-track rule; no reference-distance matching",
                "baseline_csv": str(destination.resolve()),
            }
            selected_rows.append(baseline)
            audit_rows.append(
                {
                    "experiment_profile": profile.name,
                    "allele_index": allele_index,
                    "anchor_locus": anchor_locus,
                    "channel": channel,
                    "corrected_channel": channel_spec.corrected_channel,
                    "raw_channel_index": channel_spec.raw_index,
                    "marker": channel_spec.marker,
                    "marker_slug": channel_spec.marker_slug,
                    "site_id": channel_spec.site_id,
                    "genomic_locus": channel_spec.genomic_locus,
                    "fluorophore": channel_spec.fluorophore,
                    "candidate_count": len(pool),
                    "selection_status": "selected longest baseline",
                    "selected_candidate_csv": selected["candidate_csv"],
                    "selected_points": selected["points"],
                    "selected_frame_span": selected["frame_span"],
                    "baseline_csv": str(destination.resolve()),
                }
            )
    return selected_rows, audit_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_dir", type=Path)
    parser.add_argument("--anchor-dir", type=Path, required=True)
    parser.add_argument("--aligned-microsam-mask", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--experiment-profile",
        choices=experiment_profiles.profile_choices(),
        required=True,
    )
    parser.add_argument(
        "--roi-geometry",
        choices=("tube", "convex_hull", "validated_segment_convex_hull"),
        default="tube",
        help=(
            "Static ROI seed: the temporally ordered anchor-path tube "
            "(backward-compatible default), or the filled convex hull of "
            "that path. Both are dilated and intersected with micro-SAM support."
        ),
    )
    parser.add_argument(
        "--channel-specific-reference-mode",
        choices=("legacy", "p_r_specific"),
        default="legacy",
        help=(
            "p_r_specific uses P reference/ROI for Green+Purple and the uniquely "
            "paired autonomous R reference/ROI for Red."
        ),
    )
    parser.add_argument("--roi-dilation-px", type=int, default=5)
    parser.add_argument("--matlab-bin", default="matlab")
    parser.add_argument("--matlab-workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--matlab-save-filter-images", action="store_true")
    parser.add_argument(
        "--crop-metadata-sidecar",
        type=Path,
        help="Crop _metadata.json containing exact ND2 frame intervals; uniform TIFF timing is the audited fallback.",
    )
    parser.add_argument("--d-star", type=float, default=4.1e-3)
    parser.add_argument("--alpha", type=float, default=0.38)
    parser.add_argument("--trajectory-coverage-probability", type=float, default=0.975)
    parser.add_argument("--localization-error-nm", type=float, default=0.0)
    parser.add_argument("--max-step-rounding-px", type=float, default=0.05)
    parser.add_argument("--max-step-px", type=float, help="Explicit override; otherwise use the metadata/physical model.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = experiment_profiles.get_profile(args.experiment_profile)
    anchor_channel = profile.anchor_channel
    analysis_dir = args.analysis_dir.resolve()
    anchor_dir = args.anchor_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else analysis_dir / "anchor_roi_v4"
    roi_dir = output_dir / "static_union_rois"
    spt_dir = output_dir / "roi_spt"
    baseline_dir = output_dir / "baseline_longest"
    audit_dir = output_dir / "audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    for directory in (roi_dir, spt_dir, baseline_dir, audit_dir):
        if directory.exists():
            if directory.resolve().parent != output_dir:
                raise RuntimeError(f"Refusing to clean output outside {output_dir}: {directory}")
            shutil.rmtree(directory)
    for directory in (roi_dir, spt_dir, baseline_dir, audit_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if args.roi_dilation_px < MIN_ROI_DILATION_PX:
        raise ValueError(f"--roi-dilation-px must be >= {MIN_ROI_DILATION_PX}")
    tiffs = locate_channel_tiffs(analysis_dir)
    metadata_by_channel = max_step_model.validate_channel_metadata(tiffs)
    metadata = metadata_by_channel["green"]
    frame_intervals_s, timing_provenance = max_step_model.read_movie_intervals(
        metadata,
        args.crop_metadata_sidecar,
    )
    derivation = max_step_model.derive_from_metadata(
        metadata,
        diffusion_coefficient_um2_per_s_alpha=args.d_star,
        anomalous_exponent=args.alpha,
        trajectory_coverage_probability=args.trajectory_coverage_probability,
        localization_error_nm=args.localization_error_nm,
        rounding_increment_px=args.max_step_rounding_px,
        track_mem=3,
        explicit_max_step_px=args.max_step_px,
        frame_intervals_s=frame_intervals_s,
        timing_provenance=timing_provenance,
    )
    derivation["metadata_consistency_across_channel_tiffs"] = {
        "verified": True,
        "metadata_by_channel": metadata_by_channel,
    }
    (audit_dir / "max_step_model.json").write_text(
        json.dumps(derivation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    max_step_px = float(derivation["operational_max_step_px"])
    pixel_size_nm = float(metadata["pixel_size_nm_per_px"])

    aligned_mask = tifffile.imread(args.aligned_microsam_mask.resolve()) > 0
    if aligned_mask.ndim != 3 or aligned_mask.shape[0] != metadata["frame_count"]:
        raise ValueError(
            f"Expected aligned TYX mask with {metadata['frame_count']} frames, "
            f"found {aligned_mask.shape}"
        )
    with tifffile.TiffFile(tiffs["green"]) as tif:
        green_series = tif.series[0]
        yx_shape = tuple(
            int(green_series.shape[green_series.axes.index(axis)]) for axis in "YX"
        )
    if aligned_mask.shape[1:] != yx_shape:
        raise ValueError(
            f"Aligned mask YX shape {aligned_mask.shape[1:]} does not match "
            f"corrected channel TIFF YX shape {yx_shape}"
        )
    prefix = PREFIX[anchor_channel]
    anchor_paths = sorted(anchor_dir.glob(f"{prefix}_loci*_traj_rela2wholeimg.csv"), key=locus_number)
    if not anchor_paths:
        raise RuntimeError(f"No {prefix} anchor trajectories found in {anchor_dir}")

    channel_specific = args.channel_specific_reference_mode == "p_r_specific"
    if channel_specific and profile.name != "dsb_53bp1_site1_site2":
        raise ValueError("p_r_specific is defined only for the DSB experiment profile")

    candidate_rows = []
    roi_rows = []
    allele_anchors = []

    def build_record_and_run(
        *,
        allele_index: int,
        anchor_locus: int,
        reference_path: Path,
        reference_channel: str,
        channels: tuple[str, ...],
    ) -> None:
        reference = read_track_px(reference_path, pixel_size_nm)
        reference_step_px = REFERENCE_CONTINUITY_NM.get(
            reference_channel, 500.0
        ) / pixel_size_nm
        roi = static_anchor_roi(
            reference,
            aligned_mask[0],
            args.roi_dilation_px,
            args.roi_geometry,
            maximum_reference_step_px=reference_step_px,
        )
        if not roi.any():
            raise RuntimeError(
                f"Allele {allele_index}/loci{anchor_locus}/{reference_channel} ROI is empty"
            )
        components = int(ndimage.label(roi)[1])
        if components != 1 and args.roi_geometry != "validated_segment_convex_hull":
            raise RuntimeError(
                f"Allele {allele_index}/loci{anchor_locus} ROI has {components} components"
            )
        roi_label = {
            "tube": "roi",
            "convex_hull": "convex_hull",
            "validated_segment_convex_hull": "validated_segment_convex_hull",
        }[args.roi_geometry]
        roi_path = roi_dir / (
            f"allele_{allele_index:03d}_loci{anchor_locus}_{reference_channel}_"
            f"static_anchor_{roi_label}.tif"
        )
        tifffile.imwrite(roi_path, roi.astype(np.uint8) * 255)
        rows, columns = np.where(roi)
        ordered = sorted(reference)
        transitions = [
            {
                "frame_delta": int(second[0] - first[0]),
                "step_px": float(np.hypot(second[1] - first[1], second[2] - first[2])),
            }
            for first, second in zip(ordered[:-1], ordered[1:])
        ]
        roi_rows.append({
            "allele_index": allele_index,
            "anchor_locus": anchor_locus,
            "experiment_profile": profile.name,
            "reference_channel": reference_channel,
            "spt_channels": ",".join(channels),
            "reference_csv": str(reference_path.resolve()),
            "reference_points": len(reference),
            "reference_maximum_legal_step_px": reference_step_px,
            "legal_adjacent_transitions": sum(
                row["frame_delta"] == 1 and row["step_px"] <= reference_step_px
                for row in transitions
            ),
            "rejected_gap_transitions": sum(row["frame_delta"] != 1 for row in transitions),
            "rejected_step_transitions": sum(
                row["frame_delta"] == 1 and row["step_px"] > reference_step_px
                for row in transitions
            ),
            "roi_geometry": args.roi_geometry,
            "roi_dilation_px": args.roi_dilation_px,
            "gaussian_fit_box_size_px": GAUSSIAN_FIT_BOX_SIZE_PX,
            "nucleus_support": "frame 1 of drift-aligned micro-SAM mask (mask dilation independently audited)",
            "roi_area_px": int(roi.sum()),
            "connected_components": components,
            "bbox_top": int(rows.min()),
            "bbox_left": int(columns.min()),
            "bbox_bottom_exclusive": int(rows.max() + 1),
            "bbox_right_exclusive": int(columns.max() + 1),
            "roi_tiff": str(roi_path.resolve()),
        })

        locus_output = (
            spt_dir / f"allele_{allele_index:03d}_loci{anchor_locus}" / reference_channel
        )
        matlab_output = locus_output / "matlab_result"
        print(
            f"Allele {allele_index} loci{anchor_locus} {reference_channel}-reference: "
            f"channels={channels}, ROI={int(roi.sum())} px, components={components}; "
            f"SPT max_step={max_step_px:.3f} px",
            flush=True,
        )
        selected_tiffs = {channel: tiffs[channel] for channel in channels}
        run_locus_spt(
            tiffs=selected_tiffs,
            roi_path=roi_path,
            frame_rate=metadata["frame_rate_hz"],
            pixel_um=metadata["pixel_size_x_um_per_px"],
            output_dir=matlab_output,
            matlab_bin=args.matlab_bin,
            matlab_workers=args.matlab_workers,
            save_filter_images=args.matlab_save_filter_images,
            max_step_px=max_step_px,
            log_path=locus_output / "matlab_spt.log",
            channels=channels,
        )
        for path in export_candidates(selected_tiffs, matlab_output):
            candidate_rows.append(candidate_audit(
                path,
                allele_index=allele_index,
                anchor_locus=anchor_locus,
                channel=path.name[0],
                roi=roi,
                pixel_size_nm=pixel_size_nm,
                profile=profile,
            ))

    for allele_index, anchor_path in enumerate(anchor_paths, start=1):
        anchor_locus = locus_number(anchor_path)
        allele_anchors.append((allele_index, anchor_locus))
        if channel_specific:
            build_record_and_run(
                allele_index=allele_index,
                anchor_locus=anchor_locus,
                reference_path=anchor_path,
                reference_channel="purple",
                channels=("green", "purple"),
            )
            red_reference = anchor_dir / f"R_loci{anchor_locus}_traj_rela2wholeimg.csv"
            if red_reference.is_file():
                build_record_and_run(
                    allele_index=allele_index,
                    anchor_locus=anchor_locus,
                    reference_path=red_reference,
                    reference_channel="red",
                    channels=("red",),
                )
            else:
                print(
                    f"Allele {allele_index} loci{anchor_locus}: no uniquely paired autonomous "
                    "Red reference; Red SPT skipped fail-closed",
                    flush=True,
                )
        else:
            build_record_and_run(
                allele_index=allele_index,
                anchor_locus=anchor_locus,
                reference_path=anchor_path,
                reference_channel=anchor_channel,
                channels=CHANNELS,
            )
    selected_rows, selection_audit = select_longest_baselines(
        candidate_rows, baseline_dir, allele_anchors, profile
    )
    for row in selected_rows:
        row["frame_interval_s"] = metadata["frame_interval_s"]
        row["movie_frame_count"] = metadata["frame_count"]
        row["pixel_size_nm_per_px"] = pixel_size_nm
    write_csv(audit_dir / "static_anchor_roi_geometry.csv", roi_rows)
    write_csv(audit_dir / "all_candidate_trajectories.csv", candidate_rows)
    write_csv(audit_dir / "baseline_selection.csv", selection_audit)
    write_csv(baseline_dir / "baseline_manifest.csv", selected_rows)

    summary = {
        "version": VERSION,
        "experiment_profile": profile.name,
        "profile_contract": profile.to_manifest(),
        "analysis_dir": str(analysis_dir),
        "output_dir": str(output_dir),
        "anchor_channel": anchor_channel,
        "anchor_raw_channel_index": profile.anchor.raw_index,
        "anchor_marker": profile.anchor.marker,
        "anchor_count": len(anchor_paths),
        "roi_geometry": args.roi_geometry,
        "static_roi_rule": {
            "tube": "complete temporally ordered anchor path used as a centerline",
            "convex_hull": "filled global convex hull of the complete anchor path",
            "validated_segment_convex_hull": (
                "split at non-adjacent frames or channel-fixed excessive steps; "
                "filled convex hull per legal adjacent-frame segment; union segments"
            ),
        }[args.roi_geometry]
        + ", dilated, intersected with frame-1 aligned micro-SAM support, reused for every frame",
        "roi_dilation_px": args.roi_dilation_px,
        "channel_specific_reference_mode": args.channel_specific_reference_mode,
        "candidate_matching_to_reference_used": channel_specific,
        "baseline_rule": "longest candidate independently within each allele/channel; no cleaned/manual input",
        "candidate_count": len(candidate_rows),
        "selected_baseline_count": len(selected_rows),
        "max_step_model_audit": str((audit_dir / "max_step_model.json").resolve()),
        "operational_max_step_px": max_step_px,
        "coordinate_contract": coordinate_system.contract_manifest(),
        "outputs": {
            "roi_geometry": str((audit_dir / "static_anchor_roi_geometry.csv").resolve()),
            "all_candidates": str((audit_dir / "all_candidate_trajectories.csv").resolve()),
            "baseline_selection": str((audit_dir / "baseline_selection.csv").resolve()),
            "baseline_manifest": str((baseline_dir / "baseline_manifest.csv").resolve()),
        },
    }
    (output_dir / "anchor_roi_v4_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
