#!/usr/bin/env python3
"""Overlay two baseline versions on the same corrected channel image."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tifffile

import coordinate_system
import max_step_model
from run_anchor_roi_spt import locate_channel_tiffs, read_candidate_nm


PREFIX_CHANNEL = {"G": "green", "R": "red", "P": "purple"}


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def projection(path: Path) -> np.ndarray:
    image = tifffile.imread(path).astype(float).mean(axis=0)
    low, high = np.percentile(image, (2, 99.7))
    return np.clip((image - low) / max(high - low, 1e-12), 0, 1)


def track(path: Path, pixel_nm: float):
    data = read_candidate_nm(path)
    frames = np.asarray([point[0] for point in data], dtype=int)
    x, y = coordinate_system.automatic_nm_to_image_xy(
        [point[1] for point in data], [point[2] for point in data], pixel_nm
    )
    return frames, np.asarray(x), np.asarray(y)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_dir", type=Path)
    parser.add_argument("old_results", type=Path)
    parser.add_argument("new_results", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--channel", choices=("G", "R", "P"), default="R")
    args = parser.parse_args()

    tiffs = locate_channel_tiffs(args.analysis_dir.resolve())
    channel = PREFIX_CHANNEL[args.channel]
    background = projection(tiffs[channel])
    pixel_nm = float(max_step_model.read_tracking_metadata(tiffs[channel])["pixel_size_nm_per_px"])
    old = {
        int(row["allele_index"]): row
        for row in rows(args.old_results / "baseline_longest" / "baseline_manifest.csv")
        if row["channel"] == args.channel
    }
    new = {
        int(row["allele_index"]): row
        for row in rows(args.new_results / "baseline_longest" / "baseline_manifest.csv")
        if row["channel"] == args.channel
    }
    roi_rows = rows(args.new_results / "audit" / "static_anchor_roi_geometry.csv")
    roi_by_allele = {
        int(row["allele_index"]): tifffile.imread(row["roi_tiff"]) > 0
        for row in roi_rows
        if row.get("reference_channel") == channel
    }
    alleles = sorted(set(old) | set(new))
    figure, axes = plt.subplots(1, max(len(alleles), 1), figsize=(5 * max(len(alleles), 1), 5), squeeze=False)
    for axis, allele in zip(axes.flat, alleles):
        axis.imshow(background, cmap="gray", origin="upper")
        if allele in roi_by_allele:
            axis.contour(roi_by_allele[allele], [0.5], colors=["#E66101"], linewidths=1.3)
        common_p95 = np.nan
        if allele in old:
            old_track = track(Path(old[allele]["baseline_csv"]), pixel_nm)
            axis.plot(old_track[1], old_track[2], "o--", color="#0072B2", linewidth=1.2,
                      markersize=2.5, label=f"v5.1 ({len(old_track[0])})")
        if allele in new:
            new_track = track(Path(new[allele]["baseline_csv"]), pixel_nm)
            axis.plot(new_track[1], new_track[2], "o-", color="#E66101", linewidth=1.6,
                      markersize=2.8, label=f"v5.2 ({len(new_track[0])})")
        if allele in old and allele in new:
            old_by_frame = {f: (x, y) for f, x, y in zip(*old_track)}
            new_by_frame = {f: (x, y) for f, x, y in zip(*new_track)}
            common = sorted(set(old_by_frame) & set(new_by_frame))
            if common:
                distances = [
                    np.hypot(old_by_frame[f][0] - new_by_frame[f][0],
                             old_by_frame[f][1] - new_by_frame[f][1])
                    for f in common
                ]
                common_p95 = float(np.percentile(distances, 95))
        p95_text = f"; common-frame p95={common_p95:.1f}px" if np.isfinite(common_p95) else ""
        axis.set_title(f"Allele {allele} | {args.channel}{p95_text}", fontsize=10)
        axis.set_xlim(0, background.shape[1] - 1)
        axis.set_ylim(background.shape[0] - 1, 0)
        axis.set_xticks([])
        axis.set_yticks([])
        axis.legend(loc="best", fontsize=8)
    figure.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=240, facecolor="white")
    plt.close(figure)


if __name__ == "__main__":
    main()
