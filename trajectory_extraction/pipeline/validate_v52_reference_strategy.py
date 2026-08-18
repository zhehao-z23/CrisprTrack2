#!/usr/bin/env python3
"""Run and visualize the v5.2 DSB reference/ROI strategy on a case manifest.

This utility runs only Python Stage 1 and constructs QC ROIs.  It never runs
MATLAB SPT and writes only below the explicitly supplied output directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tifffile

import max_step_model
from run_anchor_roi_spt import (
    REFERENCE_CONTINUITY_NM,
    locate_channel_tiffs,
    read_track_px,
    static_anchor_roi,
)


HERE = Path(__file__).resolve().parent
STAGE1_PATH = HERE / "auto_roi_for_published_v2.13.py"


def read_tsv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def normalized(image: np.ndarray) -> np.ndarray:
    low, high = np.percentile(image, (2.0, 99.7))
    return np.clip((image - low) / max(high - low, 1e-12), 0, 1)


def reference_paths(directory: Path, prefix: str) -> list[Path]:
    def key(path: Path) -> int:
        return int(path.name.split("loci", 1)[1].split("_", 1)[0])
    return sorted(directory.glob(f"{prefix}_loci*_traj_rela2wholeimg.csv"), key=key)


def locus(path: Path) -> int:
    return int(path.name.split("loci", 1)[1].split("_", 1)[0])


def old_baselines(root: Path, case_id: str) -> dict[int, Path]:
    case_root = root / "outputs" / "baseline_v51" / case_id
    matches = list(case_root.glob("*/anchor_roi_v4_dsb_53bp1_site1_site2/baseline_longest"))
    if len(matches) != 1:
        return {}
    result = {}
    for path in matches[0].glob("allele_*_site1_longest_spt_cleaned.csv"):
        allele = int(path.name.split("_", 2)[1])
        result[allele] = path
    return result


def old_mask(root: Path, case_id: str) -> Path:
    case_root = root / "outputs" / "baseline_v51" / case_id
    matches = list(case_root.glob(
        "*/anchor_roi_v4_dsb_53bp1_site1_site2/mask_alignment/"
        "microsam_mask_aligned_dilated_0px.tif"
    ))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one v5.1 aligned mask for {case_id}, found {len(matches)}")
    return matches[0]


def plot_track(axis, track, *, color, linewidth, linestyle="-", alpha=1.0, marker=None):
    if not track:
        return
    x = [point[1] for point in track]
    y = [point[2] for point in track]
    axis.plot(x, y, color=color, linewidth=linewidth, linestyle=linestyle,
              alpha=alpha, marker=marker, markersize=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--harvest-radius-um", type=float, default=2.5)
    parser.add_argument("--roi-dilation-px", type=int, default=5)
    parser.add_argument("--red-max-missing-frames", type=int, default=1)
    parser.add_argument("--red-min-movie-coverage-fraction", type=float, default=0.25)
    args = parser.parse_args()

    manifest_path = args.case_manifest.resolve()
    prior_project = manifest_path.parent.parent
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing validation output: {output}")
    (output / "cases").mkdir(parents=True)
    (output / "figures").mkdir()
    (output / "tables").mkdir()
    rows = read_tsv(manifest_path)
    metric_rows = []
    panels = []

    for case in rows:
        case_id = case["case_id"]
        analysis_dir = Path(case["staged_analysis_dir"])
        nucleus = next(analysis_dir.glob("*_Nucleus.tif"))
        mask_path = old_mask(prior_project, case_id)
        case_out = output / "cases" / case_id
        anchor_out = case_out / "anchor_stage1"
        anchor_out.mkdir(parents=True)
        command = [
            sys.executable, str(STAGE1_PATH), str(nucleus),
            "--reference-channel", "purple",
            "--nucleus-mask", str(mask_path),
            "--output-dir", str(anchor_out),
            "--reference-edge-width-px", "3.0",
            "--reference-max-edge-fraction", "0.10",
            "--target-reference-mode", "p_gated_r_autonomous",
            "--red-harvest-radius-um", str(args.harvest_radius_um),
            "--red-min-track-points", "5",
            "--red-min-shared-frames", "5",
            "--red-min-movie-coverage-fraction",
            str(args.red_min_movie_coverage_fraction),
            "--red-max-missing-frames", str(args.red_max_missing_frames),
            "--red-uniqueness-margin-px", "1.0",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        (case_out / "stage1.log").write_text(
            completed.stdout + "\n" + completed.stderr, encoding="utf-8"
        )
        if completed.returncode:
            metric_rows.append({
                "case_id": case_id, "split": case["split"], "status": "STAGE1_FAILED",
                "p_references": 0, "red_candidates": 0, "accepted_pairs": 0,
                "movie_frames": "", "r_reference_localizations": "",
                "r_reference_lengths": "", "p_roi_area_px": "", "r_roi_area_px": "",
            })
            panels.append((case_id, case["split"], None))
            continue

        tiffs = locate_channel_tiffs(analysis_dir)
        metadata = max_step_model.read_tracking_metadata(tiffs["red"])
        pixel_nm = float(metadata["pixel_size_nm_per_px"])
        red_stack = tifffile.imread(tiffs["red"]).astype(float)
        red_average = normalized(red_stack.mean(axis=0))
        support = tifffile.imread(mask_path) > 0
        support2d = support[0]
        p_paths = reference_paths(anchor_out, "P")
        r_paths = reference_paths(anchor_out, "R")
        candidate_paths = sorted(anchor_out.glob("R_candidate*_traj_rela2wholeimg.csv"))
        old_r = old_baselines(prior_project, case_id)
        p_tracks = {locus(path): read_track_px(path, pixel_nm) for path in p_paths}
        r_tracks = {locus(path): read_track_px(path, pixel_nm) for path in r_paths}
        candidate_tracks = [read_track_px(path, pixel_nm) for path in candidate_paths]
        p_rois, r_rois = {}, {}
        for label, track in p_tracks.items():
            p_rois[label] = static_anchor_roi(
                track, support2d, args.roi_dilation_px,
                "validated_segment_convex_hull",
                maximum_reference_step_px=REFERENCE_CONTINUITY_NM["purple"] / pixel_nm,
            )
            tifffile.imwrite(case_out / f"P_loci{label}_validated_hull5.tif",
                             p_rois[label].astype(np.uint8) * 255)
        for label, track in r_tracks.items():
            r_rois[label] = static_anchor_roi(
                track, support2d, args.roi_dilation_px,
                "validated_segment_convex_hull",
                maximum_reference_step_px=REFERENCE_CONTINUITY_NM["red"] / pixel_nm,
            )
            tifffile.imwrite(case_out / f"R_loci{label}_validated_hull5.tif",
                             r_rois[label].astype(np.uint8) * 255)

        metric_rows.append({
            "case_id": case_id,
            "split": case["split"],
            "status": "COMPLETE",
            "p_references": len(p_paths),
            "red_candidates": len(candidate_paths),
            "accepted_pairs": len(r_paths),
            "movie_frames": int(red_stack.shape[0]),
            "r_reference_localizations": int(sum(len(track) for track in r_tracks.values())),
            "r_reference_lengths": ";".join(
                f"loci{label}:{len(track)}/{red_stack.shape[0]}"
                for label, track in sorted(r_tracks.items())
            ),
            "p_roi_area_px": int(sum(mask.sum() for mask in p_rois.values())),
            "r_roi_area_px": int(sum(mask.sum() for mask in r_rois.values())),
        })
        panel = {
            "image": red_average,
            "p_tracks": p_tracks,
            "r_tracks": r_tracks,
            "candidate_tracks": candidate_tracks,
            "p_rois": p_rois,
            "r_rois": r_rois,
            "old_r": {
                label: read_track_px(path, pixel_nm) for label, path in old_r.items()
            },
        }
        panels.append((case_id, case["split"], panel))

        fig, axis = plt.subplots(figsize=(5.2, 5.2))
        render_panel(axis, case_id, case["split"], panel)
        fig.tight_layout()
        fig.savefig(output / "figures" / f"{case_id}_reference_roi_qc.png", dpi=220)
        plt.close(fig)

    figure, axes = plt.subplots(4, 4, figsize=(16, 16), squeeze=False)
    for axis, (case_id, split, panel) in zip(axes.flat, panels):
        if panel is None:
            axis.text(0.5, 0.5, f"{case_id}\nSTAGE1 FAILED", ha="center", va="center")
            axis.axis("off")
        else:
            render_panel(axis, case_id, split, panel)
    figure.tight_layout()
    figure.savefig(output / "figures" / "all_16_cases_reference_roi_qc.png", dpi=220)
    plt.close(figure)
    write_tsv(output / "tables" / "reference_roi_validation.tsv", metric_rows)
    (output / "validation_manifest.json").write_text(json.dumps({
        "case_manifest": str(manifest_path),
        "production_stage1": str(STAGE1_PATH),
        "harvest_radius_um": args.harvest_radius_um,
        "red_linking": (
            "Red-to-Red endpoints only; adjacent first; at most "
            f"{args.red_max_missing_frames} missing frame(s); 750 nm fixed radius; "
            "no interpolation or P fallback"
        ),
        "pairing": (
            "common-frame median P-R distance; >=5 shared frames and >="
            f"{args.red_min_movie_coverage_fraction:.3f} movie coverage; "
            "reciprocal unique; >=1 px bilateral margin"
        ),
        "roi": "per valid adjacent-frame segment convex hull; union; 5 px dilation; frame-1 aligned 0-px mask",
        "case_count": len(rows),
    }, indent=2), encoding="utf-8")


def render_panel(axis, case_id: str, split: str, panel: dict) -> None:
    axis.imshow(panel["image"], cmap="gray", origin="upper")
    for track in panel["candidate_tracks"]:
        plot_track(axis, track, color="#AAAAAA", linewidth=0.35, alpha=0.18)
    for mask in panel["p_rois"].values():
        axis.contour(mask, [0.5], colors=["#00A6D6"], linewidths=0.8, linestyles="--")
    for mask in panel["r_rois"].values():
        axis.contour(mask, [0.5], colors=["#E66101"], linewidths=1.2)
    for track in panel["old_r"].values():
        plot_track(axis, track, color="#F4B400", linewidth=0.8, alpha=0.65)
    for track in panel["p_tracks"].values():
        plot_track(axis, track, color="#00A6D6", linewidth=1.0, linestyle="--")
    for track in panel["r_tracks"].values():
        plot_track(axis, track, color="#E66101", linewidth=1.8, marker="o")
    axis.set_title(
        f"{case_id} | {split}\nP={len(panel['p_tracks'])}, "
        f"R candidates={len(panel['candidate_tracks'])}, pairs={len(panel['r_tracks'])}",
        fontsize=9,
    )
    axis.set_xlim(0, panel["image"].shape[1] - 1)
    axis.set_ylim(panel["image"].shape[0] - 1, 0)
    axis.set_xticks([])
    axis.set_yticks([])


if __name__ == "__main__":
    main()
