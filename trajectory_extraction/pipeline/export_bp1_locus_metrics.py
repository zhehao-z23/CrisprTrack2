#!/usr/bin/env python3
"""Export per-frame 53BP1 components and Site2-centred metrics for one crop.

This is a measurement-only sidecar stage.  It consumes the corrected Green
movie, the aligned nucleus mask, and the already selected baseline tracks.  It
does not alter candidate QC, reference detection, SPT ROIs, linking, or
baseline selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

import coordinate_system
import max_step_model
import run_anchor_roi_spt
from bp1_locus_metrics import (
    BP1MetricParameters,
    BP1SegmentationParameters,
    associate_component,
    measure_continuous_intensity,
    segment_focus_stack,
)


SCHEMA_VERSION = "v5.2.1-bp1-locus-sidecar-v1"
FOCUS_OBJECT_COLUMNS = (
    "frame", "time_s", "object_id", "source_threshold_component_id",
    "area_px", "area_um2", "equivalent_radius_nm", "centroid_x_px",
    "centroid_y_px", "centroid_x_nm", "centroid_y_nm", "bbox_x_min_px",
    "bbox_x_max_px", "bbox_y_min_px", "bbox_y_max_px", "mean_intensity_au",
    "median_intensity_au", "maximum_intensity_au",
    "integrated_excess_intensity_au", "dtype_saturated_pixel_fraction",
    "touches_nucleus_boundary", "touches_image_boundary", "focus_track_id",
    "lineage_event", "previous_frame_object_ids", "parent_focus_track_ids",
    "overlap_px_previous", "dilated_overlap_px_previous",
    "next_frame_object_ids", "child_focus_track_ids", "focus_track_first_frame",
    "focus_track_last_frame", "focus_track_length_frames",
)
ALLELE_BASE_COLUMNS = (
    "allele_index", "frame", "time_s", "pixel_size_nm", "site2_track_csv",
    "site1_track_csv", "site2_valid", "site1_valid", "site2_x_nm",
    "site2_y_nm", "site2_x_px", "site2_y_px", "site1_x_nm", "site1_y_nm",
    "site1_x_px", "site1_y_px",
)
FOCUS_ASSIGNMENT_COLUMNS = (
    "assigned_focus_track_id", "assigned_focus_lineage_event",
    "assigned_focus_area_px", "assigned_focus_equivalent_radius_nm",
    "assigned_focus_centroid_x_nm", "assigned_focus_centroid_y_nm",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_baseline_manifest(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Baseline manifest not found: {path}")
    if path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_track(path: Path, pixel_size_nm: float) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            frame = int(float(row["frame"]))
            x_nm, y_nm = float(row["x_nm"]), float(row["y_nm"])
            if frame in result:
                raise ValueError(f"Duplicate frame {frame} in {path}")
            result[frame] = {
                "x_nm": x_nm,
                "y_nm": y_nm,
                "x_px": float(coordinate_system.automatic_nm_to_image_px(x_nm, pixel_size_nm)),
                "y_px": float(coordinate_system.automatic_nm_to_image_px(y_nm, pixel_size_nm)),
            }
    return result


def write_table(path: Path, table: pd.DataFrame) -> None:
    table.to_csv(path, index=False, lineterminator="\n")


def add_motion_columns(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    result = table.copy()
    for allele, indices in result.groupby("allele_index", sort=False).groups.items():
        index = list(indices)
        group = result.loc[index]
        frames = group["frame"].to_numpy(int)
        for prefix in ("site1", "site2"):
            x = pd.to_numeric(group[f"{prefix}_x_nm"], errors="coerce").to_numpy(float)
            y = pd.to_numeric(group[f"{prefix}_y_nm"], errors="coerce").to_numpy(float)
            step = np.full(len(group), np.nan)
            valid = (
                (np.diff(frames) == 1)
                & np.isfinite(x[:-1]) & np.isfinite(x[1:])
                & np.isfinite(y[:-1]) & np.isfinite(y[1:])
            )
            positions = np.flatnonzero(valid) + 1
            step[positions] = np.hypot(
                x[positions] - x[positions - 1],
                y[positions] - y[positions - 1],
            )
            result.loc[index, f"{prefix}_one_frame_step_nm"] = step
    p_x = pd.to_numeric(result["site2_x_nm"], errors="coerce")
    p_y = pd.to_numeric(result["site2_y_nm"], errors="coerce")
    r_x = pd.to_numeric(result["site1_x_nm"], errors="coerce")
    r_y = pd.to_numeric(result["site1_y_nm"], errors="coerce")
    result["site1_site2_separation_nm"] = np.hypot(p_x - r_x, p_y - r_y)
    return result


def finite_median(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.median()) if len(numeric) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_dir", type=Path)
    parser.add_argument("--aligned-nucleus-mask", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--crop-metadata-sidecar", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    analysis_dir = args.analysis_dir.resolve()
    mask_path = args.aligned_nucleus_mask.resolve()
    baseline_manifest = args.baseline_manifest.resolve()
    sidecar = args.crop_metadata_sidecar.resolve() if args.crop_metadata_sidecar else None
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing 53BP1 output: {output}")
    output.mkdir(parents=True)

    channel_tiffs = run_anchor_roi_spt.locate_channel_tiffs(analysis_dir)
    metadata = max_step_model.validate_channel_metadata(channel_tiffs)["green"]
    pixel_size_nm = float(metadata["pixel_size_nm_per_px"])
    intervals, timing = max_step_model.read_movie_intervals(metadata, sidecar)
    times_s = np.concatenate([[0.0], np.cumsum(np.asarray(intervals, dtype=float))])
    green_path = channel_tiffs["green"].resolve()
    green = tifffile.imread(green_path)
    masks = tifffile.imread(mask_path) > 0
    if green.ndim != 3:
        raise ValueError(f"Corrected Green TIFF must be TYX, found {green.shape}")
    if masks.ndim == 2:
        masks = np.repeat(masks[None], green.shape[0], axis=0)
    if masks.shape != green.shape:
        raise ValueError(f"Mask/Green shape mismatch: {masks.shape} vs {green.shape}")
    if len(times_s) != green.shape[0]:
        raise ValueError(f"Timing/Green frame mismatch: {len(times_s)} vs {green.shape[0]}")

    metric_parameters = BP1MetricParameters()
    segmentation_parameters = BP1SegmentationParameters()
    labels, frame_rows, object_rows = segment_focus_stack(
        green, masks, pixel_size_nm, segmentation_parameters
    )
    frame_table = pd.DataFrame(frame_rows)
    frame_table.insert(1, "time_s", times_s)
    object_table = pd.DataFrame(object_rows)
    if not object_table.empty:
        object_table.insert(
            1,
            "time_s",
            object_table["frame"].map(lambda value: float(times_s[int(value) - 1])),
        )
    else:
        object_table = pd.DataFrame(columns=FOCUS_OBJECT_COLUMNS)
    tifffile.imwrite(
        output / "bp1_focus_labels.tif",
        labels,
        photometric="minisblack",
        compression="zlib",
        metadata={"axes": "TYX"},
    )
    write_table(output / "bp1_frame_segmentation.csv", frame_table)
    write_table(output / "bp1_focus_objects.csv", object_table)

    manifest_rows = read_baseline_manifest(baseline_manifest)
    track_paths: dict[tuple[int, str], Path] = {}
    for row in manifest_rows:
        channel = str(row.get("channel", ""))
        if channel not in {"P", "R"}:
            continue
        path = Path(row["baseline_csv"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Baseline CSV listed in manifest is missing: {path}")
        track_paths[(int(row["allele_index"]), channel)] = path
    p_alleles = sorted(allele for allele, channel in track_paths if channel == "P")
    object_ids_by_frame: dict[int, list[int]] = {}
    object_index: dict[tuple[int, int], dict[str, object]] = {}
    for row in object_rows:
        frame, object_id = int(row["frame"]), int(row["object_id"])
        object_ids_by_frame.setdefault(frame, []).append(object_id)
        object_index[(frame, object_id)] = row

    allele_rows: list[dict[str, object]] = []
    for allele in p_alleles:
        p_path = track_paths[(allele, "P")]
        r_path = track_paths.get((allele, "R"))
        p_track = read_track(p_path, pixel_size_nm)
        r_track = read_track(r_path, pixel_size_nm) if r_path else {}
        for frame in range(1, green.shape[0] + 1):
            p, r = p_track.get(frame), r_track.get(frame)
            row: dict[str, object] = {
                "allele_index": allele,
                "frame": frame,
                "time_s": float(times_s[frame - 1]),
                "pixel_size_nm": pixel_size_nm,
                "site2_track_csv": str(p_path),
                "site1_track_csv": str(r_path) if r_path else "",
                "site2_valid": p is not None,
                "site1_valid": r is not None,
                "site2_x_nm": p["x_nm"] if p else None,
                "site2_y_nm": p["y_nm"] if p else None,
                "site2_x_px": p["x_px"] if p else None,
                "site2_y_px": p["y_px"] if p else None,
                "site1_x_nm": r["x_nm"] if r else None,
                "site1_y_nm": r["y_nm"] if r else None,
                "site1_x_px": r["x_px"] if r else None,
                "site1_y_px": r["y_px"] if r else None,
            }
            if p is None:
                intensity = measure_continuous_intensity(
                    green[frame - 1], masks[frame - 1], labels[frame - 1] > 0,
                    math.nan, math.nan, pixel_size_nm, metric_parameters,
                )
                intensity["intensity_missing_reason"] = "DNA_ANCHOR_MISSING"
                association = associate_component(
                    labels[frame - 1], [], math.nan, math.nan,
                    pixel_size_nm, metric_parameters,
                )
                association["assignment_status"] = "DNA_ANCHOR_MISSING"
                association["site2_bp1_distance_score"] = None
            else:
                intensity = measure_continuous_intensity(
                    green[frame - 1], masks[frame - 1], labels[frame - 1] > 0,
                    p["x_px"], p["y_px"], pixel_size_nm, metric_parameters,
                )
                association = associate_component(
                    labels[frame - 1], object_ids_by_frame.get(frame, []),
                    p["x_px"], p["y_px"], pixel_size_nm, metric_parameters,
                )
            row.update(intensity)
            row.update(association)
            assigned_id = association.get("assigned_object_id")
            focus = object_index.get((frame, int(assigned_id))) if assigned_id is not None else None
            row.update({
                "assigned_focus_track_id": focus.get("focus_track_id") if focus else None,
                "assigned_focus_lineage_event": focus.get("lineage_event") if focus else "",
                "assigned_focus_area_px": focus.get("area_px") if focus else None,
                "assigned_focus_equivalent_radius_nm": focus.get("equivalent_radius_nm") if focus else None,
                "assigned_focus_centroid_x_nm": focus.get("centroid_x_nm") if focus else None,
                "assigned_focus_centroid_y_nm": focus.get("centroid_y_nm") if focus else None,
            })
            allele_rows.append(row)

    if allele_rows:
        allele_table = add_motion_columns(pd.DataFrame(allele_rows))
    else:
        dummy_intensity = measure_continuous_intensity(
            np.zeros((1, 1), dtype=float),
            np.zeros((1, 1), dtype=bool),
            np.zeros((1, 1), dtype=bool),
            math.nan,
            math.nan,
            pixel_size_nm,
            metric_parameters,
        )
        dummy_association = associate_component(
            np.zeros((1, 1), dtype=np.uint16),
            [],
            math.nan,
            math.nan,
            pixel_size_nm,
            metric_parameters,
        )
        allele_table = pd.DataFrame(
            columns=(
                *ALLELE_BASE_COLUMNS,
                *dummy_intensity,
                *dummy_association,
                *FOCUS_ASSIGNMENT_COLUMNS,
                "site1_one_frame_step_nm",
                "site2_one_frame_step_nm",
                "site1_site2_separation_nm",
            )
        )
    write_table(output / "bp1_allele_frame_metrics.csv", allele_table)
    summary_rows: list[dict[str, object]] = []
    if not allele_table.empty:
        for allele, group in allele_table.groupby("allele_index", sort=True):
            p_valid = group["site2_valid"].astype(bool)
            r_valid = group["site1_valid"].astype(bool)
            intensity_valid = group["intensity_metric_valid"].astype(bool)
            associated = group["assignment_status"].eq("VALID")
            summary_rows.append({
                "allele_index": int(allele),
                "movie_frames": int(len(group)),
                "site2_localizations": int(p_valid.sum()),
                "site1_localizations": int(r_valid.sum()),
                "shared_site_frames": int((p_valid & r_valid).sum()),
                "intensity_valid_frames": int(intensity_valid.sum()),
                "associated_component_frames": int(associated.sum()),
                "associated_fraction_of_site2_frames": float(associated.sum() / max(1, p_valid.sum())),
                "median_continuous_intensity_score": finite_median(group.loc[intensity_valid, "site2_bp1_continuous_intensity_score"]),
                "median_distance_score": finite_median(group.loc[p_valid, "site2_bp1_distance_score"]),
            })
    summary_table = pd.DataFrame(summary_rows)
    write_table(output / "bp1_allele_summary.csv", summary_table)

    source_files = [
        ("green_corrected_tiff", green_path),
        ("aligned_nucleus_mask", mask_path),
        ("baseline_manifest", baseline_manifest),
    ]
    if sidecar is not None:
        source_files.append(("crop_metadata_sidecar", sidecar))
    source_files.extend(
        (
            f"allele_{allele:03d}_{'site2' if channel == 'P' else 'site1'}_baseline",
            path,
        )
        for (allele, channel), path in sorted(track_paths.items())
    )
    provenance = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "measurement_only": True,
        "coordinate_contract": (
            "image arrays are 0-based pixel centres; x=column, y=row; "
            "automatic CSV image_px=nm/pixel_size_nm-1; CSV frame is 1-based"
        ),
        "segmentation_parameters": asdict(segmentation_parameters),
        "metric_parameters": asdict(metric_parameters),
        "timing_provenance": timing,
        "counts": {
            "movie_frames": int(green.shape[0]),
            "eligible_focus_objects": int(len(object_rows)),
            "focus_tracks": int(len({int(row["focus_track_id"]) for row in object_rows})),
            "site2_alleles": int(len(p_alleles)),
            "dense_allele_frame_rows": int(len(allele_table)),
        },
        "source_files": [
            {"role": role, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for role, path in source_files
        ],
        "non_interference_contract": [
            "No candidate QC decisions are changed.",
            "No reference trajectory or SPT ROI is changed.",
            "No localization, linker, or baseline selection is changed.",
            "P/Site2 may exist without a matched R/Site1 trajectory.",
        ],
        "interpretation_limits": [
            "Two-dimensional corrected-image geometry only.",
            "The intensity score is continuous and has no positivity threshold.",
            "The distance score is zero for absent, distant, or ambiguous components.",
            "Component segmentation is a sensitivity-first engineering measurement, not a repair-state classifier.",
        ],
        "elapsed_seconds": time.perf_counter() - started,
    }
    (output / "bp1_analysis_manifest.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(provenance["counts"], indent=2))


if __name__ == "__main__":
    main()
