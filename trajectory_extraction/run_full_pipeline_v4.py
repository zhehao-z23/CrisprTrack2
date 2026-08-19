#!/usr/bin/env python3
"""Run the v5 profile-locked irregular-ROI SPT for one cropped cell TIFF."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
PIPELINE = HERE / "pipeline"
sys.path.insert(0, str(PIPELINE))

import align_microsam_mask
import experiment_profiles
import fiji_preprocess


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


VERSION = "v5.2.1"
STAGE1 = PIPELINE / "auto_roi_for_published_v2.13.py"
SPT = PIPELINE / "run_anchor_roi_spt.py"
BP1_METRICS = PIPELINE / "export_bp1_locus_metrics.py"
PYTHON_QC = PIPELINE / "visualize_anchor_roi_results.py"
MATLAB_QC = PIPELINE / "plot_longest_trajectories.m"


class Tee:
    def __init__(self, stream, handle):
        self.stream = stream
        self.handle = handle

    def write(self, data):
        self.stream.write(data)
        self.handle.write(data)

    def flush(self):
        self.stream.flush()
        self.handle.flush()


def run(command: list[str]) -> None:
    print("\n" + "=" * 72)
    print("Running: " + " ".join(f'\"{item}\"' if " " in item else item for item in command))
    print("=" * 72, flush=True)
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
    process.wait()
    if process.returncode:
        raise RuntimeError(f"Command exited with code {process.returncode}: {command[0]}")


def matlab_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path, help="Step-3 crop TIFF, or Fiji analysis directory with --no-fiji.")
    parser.add_argument("--no-fiji", action="store_true", help="Reuse an existing Fiji analysis directory.")
    parser.add_argument("--crop-tif", type=Path, help="Original crop TIFF for --no-fiji if it cannot be inferred as <analysis_dir>.tif.")
    parser.add_argument("--crop-metadata-sidecar", type=Path, help="Override the standard <crop>_metadata.json timing sidecar.")
    parser.add_argument("--microsam-mask", type=Path, help="Override the crop-associated micro-SAM mask.")
    parser.add_argument("--fiji-bin", default="fiji")
    parser.add_argument("--matlab-bin", default="matlab")
    parser.add_argument("--matlab-workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--matlab-save-filter-images", action="store_true")
    parser.add_argument(
        "--experiment-profile",
        choices=experiment_profiles.profile_choices(),
        required=True,
        help="Required locked biological channel contract; it determines the anchor automatically.",
    )
    parser.add_argument(
        "--mask-dilation-px",
        type=int,
        default=0,
        help="Drift-aligned micro-SAM support expansion. Final v5.1 default is 0 px.",
    )
    parser.add_argument("--reference-seed-k", type=float)
    parser.add_argument("--reference-tracking-k", type=float)
    parser.add_argument("--reference-edge-width-px", type=float, default=3.0)
    parser.add_argument("--reference-max-edge-fraction", type=float, default=0.10)
    parser.add_argument(
        "--roi-geometry",
        choices=("auto", "tube", "convex_hull", "validated_segment_convex_hull"),
        default="auto",
        help=(
            "Static anchor ROI geometry. Tube preserves the v4.2.1 behavior; "
            "convex_hull writes to an isolated result directory."
        ),
    )
    parser.add_argument(
        "--target-reference-mode",
        choices=("auto", "legacy", "p_gated_r_autonomous"),
        default="auto",
        help="auto selects the v5.2 P-gated autonomous Red mode for DSB only.",
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
    parser.add_argument("--max-step-px", type=float, help="Explicit override; default is metadata + physical-prior model.")
    return parser.parse_args()


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, bool]:
    requested = args.input_path.resolve()
    if args.no_fiji:
        if not requested.is_dir():
            raise ValueError(f"--no-fiji requires an analysis directory: {requested}")
        crop_tiff = args.crop_tif.resolve() if args.crop_tif else requested.with_suffix(".tif")
        if not crop_tiff.is_file():
            raise FileNotFoundError(
                f"Original crop TIFF not found: {crop_tiff}. Pass --crop-tif explicitly; "
                "it is required to align the saved micro-SAM mask."
            )
        return crop_tiff, requested, False
    if not requested.is_file() or requested.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError(f"Expected a Step-3 crop TIFF: {requested}")
    analysis_dir = fiji_preprocess.analysis_dir_for_crop(requested)
    analysis_dir.mkdir(exist_ok=True)
    return requested, analysis_dir, True


def main() -> None:
    args = parse_args()
    started = datetime.now()
    crop_tiff, analysis_dir, run_fiji_now = resolve_inputs(args)
    standard_sidecar = crop_tiff.with_name(crop_tiff.stem + "_metadata.json")
    crop_metadata_sidecar = (
        args.crop_metadata_sidecar.resolve()
        if args.crop_metadata_sidecar
        else (standard_sidecar.resolve() if standard_sidecar.is_file() else None)
    )
    profile = experiment_profiles.get_profile(args.experiment_profile)
    profile_validation = profile.validate_crop(crop_tiff)
    anchor_channel = profile.anchor_channel
    is_dsb = profile.name == "dsb_53bp1_site1_site2"
    if args.target_reference_mode == "auto":
        args.target_reference_mode = "p_gated_r_autonomous" if is_dsb else "legacy"
    if args.roi_geometry == "auto":
        args.roi_geometry = "validated_segment_convex_hull" if is_dsb else "tube"
    if args.target_reference_mode == "p_gated_r_autonomous" and not is_dsb:
        raise ValueError("p_gated_r_autonomous is defined only for the DSB profile")
    if args.target_reference_mode == "p_gated_r_autonomous":
        geometry_suffix = "_p_gated_r_autonomous_" + args.roi_geometry
    else:
        geometry_suffix = "" if args.roi_geometry == "tube" else f"_{args.roi_geometry}"
    results_dir = analysis_dir / (
        f"anchor_roi_v4_{profile.name}{geometry_suffix}"
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "mask_alignment",
        "anchor_stage1",
        "static_union_rois",
        "roi_spt",
        "baseline_longest",
        "53bp1_metrics",
        "audit",
        "figures",
    ):
        generated = results_dir / name
        if generated.exists():
            if generated.resolve().parent != results_dir.resolve():
                raise RuntimeError(f"Refusing to clean generated output outside {results_dir}: {generated}")
            shutil.rmtree(generated)
    log_path = results_dir / "log_anchor_roi_v4.txt"
    manifest_path = results_dir / "run_manifest.json"
    manifest = {
        "version": VERSION,
        "status": "running",
        "started_at": started.isoformat(timespec="seconds"),
        "crop_tiff": str(crop_tiff),
        "crop_metadata_sidecar": str(crop_metadata_sidecar) if crop_metadata_sidecar else None,
        "analysis_dir": str(analysis_dir),
        "results_dir": str(results_dir),
        "experiment_profile": profile.name,
        "profile_contract": profile.to_manifest(),
        "profile_validation": profile_validation,
        "python_executable": sys.executable,
        "options": vars(args),
        "sidecar_stages": {
            "53bp1_locus_metrics": {
                "enabled": is_dsb,
                "schema_version": "v5.2.1-bp1-locus-sidecar-v1" if is_dsb else None,
                "output_dir": str(results_dir / "53bp1_metrics") if is_dsb else None,
                "measurement_only": True,
            }
        },
    }
    manifest["options"] = {key: str(value) if isinstance(value, Path) else value for key, value in manifest["options"].items()}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    completed = False
    with log_path.open("w", encoding="utf-8") as log_handle:
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(original_stdout, log_handle), Tee(original_stderr, log_handle)
        try:
            print(f"Pipeline version  : {VERSION}")
            print(f"Crop TIFF         : {crop_tiff}")
            print(f"Analysis dir      : {analysis_dir}")
            print(f"Results dir       : {results_dir}")
            print(f"Experiment profile: {profile.name}")
            print(
                f"Locked anchor      : {anchor_channel} / raw C{profile.anchor.raw_index} / "
                f"{profile.anchor.marker}"
            )

            if run_fiji_now:
                fiji_preprocess.run_fiji(crop_tiff, args.fiji_bin)
            fiji_preprocess.create_synthetic_nucleus_if_needed(analysis_dir)
            nucleus_tiff = fiji_preprocess.one_nucleus_tiff(analysis_dir)

            mask_source = args.microsam_mask.resolve() if args.microsam_mask else align_microsam_mask.discover_microsam_mask(crop_tiff)
            alignment_channel = profile.alignment_channel
            raw_index = profile.alignment_raw_index
            corrected_tiff = align_microsam_mask.corrected_channel_path(analysis_dir, alignment_channel)
            alignment = align_microsam_mask.align_mask(
                crop_tiff,
                mask_source,
                corrected_tiff,
                raw_channel_index=raw_index,
                dilation_px=args.mask_dilation_px,
                output_dir=results_dir / "mask_alignment",
            )
            aligned_mask = Path(alignment["aligned_dilated_mask"])

            anchor_dir = results_dir / "anchor_stage1"
            stage1_command = [
                sys.executable,
                str(STAGE1),
                str(nucleus_tiff),
                "--reference-channel",
                anchor_channel,
                "--nucleus-mask",
                str(aligned_mask),
                "--output-dir",
                str(anchor_dir),
                "--reference-edge-width-px",
                str(args.reference_edge_width_px),
                "--reference-max-edge-fraction",
                str(args.reference_max_edge_fraction),
                "--target-reference-mode",
                args.target_reference_mode,
                "--red-harvest-radius-um",
                str(args.red_harvest_radius_um),
                "--red-min-track-points",
                str(args.red_min_track_points),
                "--red-min-shared-frames",
                str(args.red_min_shared_frames),
                "--red-min-movie-coverage-fraction",
                str(args.red_min_movie_coverage_fraction),
                "--red-max-missing-frames",
                str(args.red_max_missing_frames),
                "--red-uniqueness-margin-px",
                str(args.red_uniqueness_margin_px),
            ]
            if args.reference_seed_k is not None:
                stage1_command.extend(["--reference-seed-k", str(args.reference_seed_k)])
            if args.reference_tracking_k is not None:
                stage1_command.extend(["--reference-tracking-k", str(args.reference_tracking_k)])
            run(stage1_command)

            spt_command = [
                sys.executable,
                str(SPT),
                str(analysis_dir),
                "--anchor-dir",
                str(anchor_dir),
                "--aligned-microsam-mask",
                str(aligned_mask),
                "--output-dir",
                str(results_dir),
                "--experiment-profile",
                profile.name,
                "--roi-geometry",
                args.roi_geometry,
                "--channel-specific-reference-mode",
                (
                    "p_r_specific"
                    if args.target_reference_mode == "p_gated_r_autonomous"
                    else "legacy"
                ),
                "--roi-dilation-px",
                str(args.roi_dilation_px),
                "--matlab-bin",
                args.matlab_bin,
                "--matlab-workers",
                str(args.matlab_workers),
                "--d-star",
                str(args.d_star),
                "--alpha",
                str(args.alpha),
                "--trajectory-coverage-probability",
                str(args.trajectory_coverage_probability),
                "--localization-error-nm",
                str(args.localization_error_nm),
                "--max-step-rounding-px",
                str(args.max_step_rounding_px),
            ]
            if crop_metadata_sidecar is not None:
                spt_command.extend(["--crop-metadata-sidecar", str(crop_metadata_sidecar)])
            if args.matlab_save_filter_images:
                spt_command.append("--matlab-save-filter-images")
            if args.max_step_px is not None:
                spt_command.extend(["--max-step-px", str(args.max_step_px)])
            run(spt_command)

            if is_dsb:
                bp1_command = [
                    sys.executable,
                    str(BP1_METRICS),
                    str(analysis_dir),
                    "--aligned-nucleus-mask",
                    str(aligned_mask),
                    "--baseline-manifest",
                    str(results_dir / "baseline_longest" / "baseline_manifest.csv"),
                    "--output-dir",
                    str(results_dir / "53bp1_metrics"),
                ]
                if crop_metadata_sidecar is not None:
                    bp1_command.extend(
                        ["--crop-metadata-sidecar", str(crop_metadata_sidecar)]
                    )
                run(bp1_command)

            run([sys.executable, str(PYTHON_QC), str(analysis_dir), "--results-dir", str(results_dir)])
            matlab_output = results_dir / "figures" / "matlab_longest"
            matlab_output.mkdir(parents=True, exist_ok=True)
            matlab_expression = (
                f"addpath('{matlab_quote(PIPELINE)}','-begin'); "
                f"plot_longest_trajectories('{matlab_quote(results_dir / 'baseline_longest' / 'baseline_manifest.csv')}', "
                f"'{matlab_quote(matlab_output)}')"
            )
            run([args.matlab_bin, "-batch", matlab_expression])
            completed = True
            print(f"Pipeline complete : {datetime.now().isoformat(timespec='seconds')}")
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            manifest["status"] = "complete" if completed else "failed_or_interrupted"
            manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
            manifest["elapsed_seconds"] = (datetime.now() - started).total_seconds()
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    main()
