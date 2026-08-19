#!/usr/bin/env python3
"""Run the v5 profile-locked anchor-ROI SPT for every valid cell crop in one FOV."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "pipeline"))
from align_microsam_mask import discover_microsam_mask
import experiment_profiles


VERSION = "v5.2.1"
SINGLE_CELL_RUNNER = HERE / "run_full_pipeline_v4.py"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_cell_crop(
    path: Path, profile: experiment_profiles.ExperimentProfile
) -> tuple[bool, str]:
    try:
        validation = profile.validate_crop(path)
        mask = discover_microsam_mask(path)
    except Exception as exc:
        return False, str(exc)
    return True, (
        f"profile={profile.name}, axes={validation['axes']}, "
        f"shape={validation['shape']}, anchor={profile.anchor.marker}, "
        f"micro-SAM={mask.name}"
    )


def scientific_options(args: argparse.Namespace) -> dict:
    return {
        "experiment_profile": args.experiment_profile,
        "mask_dilation_px": args.mask_dilation_px,
        "reference_seed_k": args.reference_seed_k,
        "reference_tracking_k": args.reference_tracking_k,
        "reference_edge_width_px": args.reference_edge_width_px,
        "reference_max_edge_fraction": args.reference_max_edge_fraction,
        "roi_geometry": args.roi_geometry,
        "target_reference_mode": args.target_reference_mode,
        "red_harvest_radius_um": args.red_harvest_radius_um,
        "red_min_track_points": args.red_min_track_points,
        "red_min_shared_frames": args.red_min_shared_frames,
        "red_uniqueness_margin_px": args.red_uniqueness_margin_px,
        "roi_dilation_px": args.roi_dilation_px,
        "d_star": args.d_star,
        "alpha": args.alpha,
        "trajectory_coverage_probability": args.trajectory_coverage_probability,
        "localization_error_nm": args.localization_error_nm,
        "max_step_rounding_px": args.max_step_rounding_px,
        "max_step_px": args.max_step_px,
        "matlab_workers": args.matlab_workers,
        "matlab_save_filter_images": args.matlab_save_filter_images,
    }


def result_suffix(args: argparse.Namespace) -> str:
    if args.target_reference_mode == "p_gated_r_autonomous":
        return "_p_gated_r_autonomous_" + args.roi_geometry
    return "" if args.roi_geometry == "tube" else f"_{args.roi_geometry}"


def completion_matches(analysis_dir: Path, args: argparse.Namespace) -> bool:
    geometry_suffix = result_suffix(args)
    path = (
        analysis_dir
        / f"anchor_roi_v4_{args.experiment_profile}{geometry_suffix}"
        / "run_manifest.json"
    )
    if not path.is_file():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return (
            manifest.get("version") == VERSION
            and manifest.get("status") == "complete"
            and all(manifest.get("options", {}).get(key) == value for key, value in scientific_options(args).items())
        )
    except (OSError, ValueError, TypeError):
        return False


def tail_log(analysis_dir: Path, args: argparse.Namespace, line_count: int = 25) -> str:
    geometry_suffix = result_suffix(args)
    path = (
        analysis_dir
        / f"anchor_roi_v4_{args.experiment_profile}{geometry_suffix}"
        / "log_anchor_roi_v4.txt"
    )
    if not path.is_file():
        return "v4 log was not created"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-line_count:])


def bp1_output_info(analysis_dir: Path, args: argparse.Namespace) -> tuple[str, str]:
    if args.experiment_profile != "dsb_53bp1_site1_site2":
        return "not_applicable", ""
    result_dir = analysis_dir / (
        f"anchor_roi_v4_{args.experiment_profile}{result_suffix(args)}"
    )
    path = result_dir / "53bp1_metrics" / "bp1_analysis_manifest.json"
    if not path.is_file():
        return "missing_or_not_reached", str(path)
    try:
        status = str(json.loads(path.read_text(encoding="utf-8")).get("status", "unknown"))
    except (OSError, ValueError, TypeError):
        status = "unreadable_manifest"
    return status.lower(), str(path)


def run_cell(crop: Path, args: argparse.Namespace) -> dict:
    # Selection views contain symlinks into the immutable candidate archive.
    # Resolve first so resume checks and the child runner inspect the same result.
    analysis_dir = crop.resolve().with_suffix("")
    if args.resume and completion_matches(analysis_dir, args):
        bp1_status, bp1_manifest = bp1_output_info(analysis_dir, args)
        return {
            "crop": str(crop), "analysis_dir": str(analysis_dir), "status": "skipped_complete",
            "experiment_profile": args.experiment_profile,
            "bp1_metrics_status": bp1_status, "bp1_metrics_manifest": bp1_manifest,
            "started_at": "", "finished_at": now(), "duration_s": 0.0, "exit_code": 0, "error_tail": "",
        }
    command = [
        sys.executable, str(SINGLE_CELL_RUNNER), str(crop),
        "--fiji-bin", args.fiji_bin,
        "--matlab-bin", args.matlab_bin,
        "--matlab-workers", str(args.matlab_workers),
        "--experiment-profile", args.experiment_profile,
        "--mask-dilation-px", str(args.mask_dilation_px),
        "--reference-edge-width-px", str(args.reference_edge_width_px),
        "--reference-max-edge-fraction", str(args.reference_max_edge_fraction),
        "--roi-geometry", args.roi_geometry,
        "--target-reference-mode", args.target_reference_mode,
        "--red-harvest-radius-um", str(args.red_harvest_radius_um),
        "--red-min-track-points", str(args.red_min_track_points),
        "--red-min-shared-frames", str(args.red_min_shared_frames),
        "--red-min-movie-coverage-fraction", str(args.red_min_movie_coverage_fraction),
        "--red-max-missing-frames", str(args.red_max_missing_frames),
        "--red-uniqueness-margin-px", str(args.red_uniqueness_margin_px),
        "--roi-dilation-px", str(args.roi_dilation_px),
        "--d-star", str(args.d_star),
        "--alpha", str(args.alpha),
        "--trajectory-coverage-probability", str(args.trajectory_coverage_probability),
        "--localization-error-nm", str(args.localization_error_nm),
        "--max-step-rounding-px", str(args.max_step_rounding_px),
    ]
    if args.reference_seed_k is not None:
        command.extend(["--reference-seed-k", str(args.reference_seed_k)])
    if args.reference_tracking_k is not None:
        command.extend(["--reference-tracking-k", str(args.reference_tracking_k)])
    if args.max_step_px is not None:
        command.extend(["--max-step-px", str(args.max_step_px)])
    if args.matlab_save_filter_images:
        command.append("--matlab-save-filter-images")
    started_at, started = now(), time.perf_counter()
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=environment)
        exit_code = int(result.returncode)
        status = "complete" if exit_code == 0 else "failed"
        error_tail = "" if exit_code == 0 else tail_log(
            analysis_dir, args
        )
    except Exception as exc:
        exit_code, status, error_tail = -1, "failed_to_start", repr(exc)
    bp1_status, bp1_manifest = bp1_output_info(analysis_dir, args)
    return {
        "crop": str(crop), "analysis_dir": str(analysis_dir), "status": status,
        "experiment_profile": args.experiment_profile,
        "bp1_metrics_status": bp1_status, "bp1_metrics_manifest": bp1_manifest,
        "started_at": started_at, "finished_at": now(),
        "duration_s": round(time.perf_counter() - started, 1),
        "exit_code": exit_code, "error_tail": error_tail,
    }


def write_summary(path: Path, rows: list[dict]) -> None:
    fields = [
        "crop", "analysis_dir", "experiment_profile", "status", "started_at",
        "finished_at", "duration_s", "exit_code", "bp1_metrics_status",
        "bp1_metrics_manifest", "error_tail",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop_dir", type=Path)
    parser.add_argument("--crop-glob", default="*.tif")
    parser.add_argument("--fiji-bin", default="fiji")
    parser.add_argument("--matlab-bin", default="matlab")
    parser.add_argument(
        "--experiment-profile",
        choices=experiment_profiles.profile_choices(),
        required=True,
        help="Required locked biological channel contract; it determines the anchor automatically.",
    )
    parser.add_argument("--cell-workers", type=int, default=1)
    parser.add_argument("--matlab-workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--matlab-save-filter-images", action="store_true")
    parser.add_argument("--mask-dilation-px", type=int, default=0)
    parser.add_argument("--reference-seed-k", type=float)
    parser.add_argument("--reference-tracking-k", type=float)
    parser.add_argument("--reference-edge-width-px", type=float, default=3.0)
    parser.add_argument("--reference-max-edge-fraction", type=float, default=0.10)
    parser.add_argument(
        "--roi-geometry",
        choices=("auto", "tube", "convex_hull", "validated_segment_convex_hull"),
        default="auto",
    )
    parser.add_argument(
        "--target-reference-mode",
        choices=("auto", "legacy", "p_gated_r_autonomous"),
        default="auto",
    )
    parser.add_argument("--red-harvest-radius-um", type=float, default=2.5)
    parser.add_argument("--red-min-track-points", type=int, default=5)
    parser.add_argument("--red-min-shared-frames", type=int, default=5)
    parser.add_argument("--red-min-movie-coverage-fraction", type=float, default=0.25)
    parser.add_argument("--red-max-missing-frames", type=int, default=1)
    parser.add_argument("--red-uniqueness-margin-px", type=float, default=1.0)
    parser.add_argument("--roi-dilation-px", type=int, default=5)
    parser.add_argument("--d-star", type=float, default=4.1e-3)
    parser.add_argument("--alpha", type=float, default=0.38)
    parser.add_argument("--trajectory-coverage-probability", type=float, default=0.975)
    parser.add_argument("--localization-error-nm", type=float, default=0.0)
    parser.add_argument("--max-step-rounding-px", type=float, default=0.05)
    parser.add_argument("--max-step-px", type=float)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = experiment_profiles.get_profile(args.experiment_profile)
    is_dsb = profile.name == "dsb_53bp1_site1_site2"
    if args.target_reference_mode == "auto":
        args.target_reference_mode = "p_gated_r_autonomous" if is_dsb else "legacy"
    if args.roi_geometry == "auto":
        args.roi_geometry = "validated_segment_convex_hull" if is_dsb else "tube"
    if args.target_reference_mode == "p_gated_r_autonomous" and not is_dsb:
        raise SystemExit("ERROR: p_gated_r_autonomous is defined only for the DSB profile")
    crop_dir = args.crop_dir.resolve()
    if not crop_dir.is_dir() or args.cell_workers < 1:
        raise SystemExit("ERROR: crop_dir must exist and --cell-workers must be >= 1")
    candidates = sorted(path for path in crop_dir.glob(args.crop_glob) if path.is_file())
    crops = []
    for path in candidates:
        accepted, reason = is_cell_crop(path, profile)
        print(f"  [{'ACCEPT' if accepted else 'SKIP'}] {path.name}: {reason}")
        if accepted:
            crops.append(path)
    if not crops:
        raise SystemExit("ERROR: no valid cell crop with an associated micro-SAM mask")
    print(
        f"Profile={profile.name}; locked anchor={profile.anchor.marker} "
        f"(raw C{profile.anchor.raw_index})"
    )
    print(f"Valid crops={len(crops)}; cell workers={args.cell_workers}; MATLAB workers/cell={args.matlab_workers}")
    print(f"Maximum simultaneous MATLAB processes={args.cell_workers * args.matlab_workers}")
    if args.dry_run:
        print("Dry run complete; no analysis started.")
        return

    summary_path = crop_dir / f"trajectory_batch_v4_{profile.name}_summary.csv"
    results, started = [], time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.cell_workers) as executor:
        pending = {executor.submit(run_cell, crop, args) for crop in crops}
        while pending:
            completed, pending = wait(pending, timeout=60, return_when=FIRST_COMPLETED)
            if not completed:
                print(
                    f"Batch still running: {len(pending)} cell(s) pending, "
                    f"{time.perf_counter() - started:.0f} s elapsed",
                    flush=True,
                )
                continue
            for future in completed:
                row = future.result()
                results.append(row)
                print(f"[{row['status']}] {Path(row['crop']).name} ({row['duration_s']} s)")
                write_summary(summary_path, results)

    order = {str(path): index for index, path in enumerate(crops)}
    results.sort(key=lambda row: order[row["crop"]])
    write_summary(summary_path, results)
    failures = [row for row in results if row["status"].startswith("failed")]
    print(f"Batch elapsed={time.perf_counter() - started:.1f} s; summary={summary_path}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
