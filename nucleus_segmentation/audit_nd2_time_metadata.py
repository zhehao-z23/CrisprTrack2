#!/usr/bin/env python3
"""Audit ND2 channel contracts and exact time axes without loading pixel arrays."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from nd2 import ND2File

from save_crops import _experiment_interval_s, _extract_frame_times


FIELDS = (
    "relative_path",
    "size_bytes",
    "T",
    "Z",
    "C",
    "Y",
    "X",
    "channel_names",
    "channel_contract_ok",
    "loop_types",
    "timestamp_source",
    "timestamp_count",
    "dt_median_s",
    "dt_min_s",
    "dt_max_s",
    "dt_cv",
    "dt_max_to_median",
    "status",
)


def _finite_text(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.9g}"


def audit_file(
    path: Path,
    root: Path,
    expected_channel_tokens: tuple[str, ...],
    review_cv: float,
    review_max_ratio: float,
) -> dict[str, object]:
    with ND2File(path) as nd2_file:
        sizes = {str(key).upper(): int(value) for key, value in nd2_file.sizes.items()}
        n_timepoints = sizes.get("T", 1)
        channels = [
            str(channel.channel.name or "")
            for channel in nd2_file.metadata.channels
        ]
        channel_contract_ok = (
            not expected_channel_tokens
            or (
                len(channels) == len(expected_channel_tokens)
                and all(
                    token.casefold() in name.casefold()
                    for token, name in zip(expected_channel_tokens, channels)
                )
            )
        )
        loop_types = [
            str(getattr(loop, "type", type(loop).__name__))
            for loop in nd2_file.experiment
        ]

        frame_times_s = _extract_frame_times(nd2_file, n_timepoints)
        if frame_times_s is not None:
            timestamp_source = "frame_metadata.relativeTimeMs"
            intervals = np.diff(frame_times_s).astype(float)
        else:
            interval, timestamp_source = _experiment_interval_s(nd2_file.experiment)
            intervals = (
                np.full(n_timepoints - 1, interval, dtype=float)
                if interval is not None and n_timepoints > 1
                else np.array([], dtype=float)
            )
            timestamp_source = timestamp_source or ""

    median = float(np.median(intervals)) if intervals.size else None
    minimum = float(np.min(intervals)) if intervals.size else None
    maximum = float(np.max(intervals)) if intervals.size else None
    mean = float(np.mean(intervals)) if intervals.size else None
    cv = (
        float(np.std(intervals) / mean)
        if intervals.size and mean is not None and mean > 0
        else None
    )
    max_ratio = (
        maximum / median
        if maximum is not None and median is not None and median > 0
        else None
    )

    if not channel_contract_ok:
        status = "invalid_channel_contract"
    elif n_timepoints == 1:
        status = "segmentation_only_single_timepoint"
    elif frame_times_s is None:
        status = "review_no_exact_frame_timestamps"
    elif (
        (cv is not None and cv > review_cv)
        or (max_ratio is not None and max_ratio > review_max_ratio)
    ):
        status = "review_nonuniform_time"
    else:
        status = "spt_ready_time_axis"

    return {
        "relative_path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "T": sizes.get("T", 1),
        "Z": sizes.get("Z", 1),
        "C": sizes.get("C", 1),
        "Y": sizes.get("Y", 1),
        "X": sizes.get("X", 1),
        "channel_names": "|".join(channels),
        "channel_contract_ok": str(channel_contract_ok).lower(),
        "loop_types": "|".join(loop_types),
        "timestamp_source": timestamp_source,
        "timestamp_count": len(frame_times_s) if frame_times_s is not None else 0,
        "dt_median_s": _finite_text(median),
        "dt_min_s": _finite_text(minimum),
        "dt_max_s": _finite_text(maximum),
        "dt_cv": _finite_text(cv),
        "dt_max_to_median": _finite_text(max_ratio),
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--expected-channel-token",
        action="append",
        default=[],
        help="Required token for the corresponding zero-based raw channel.",
    )
    parser.add_argument("--review-cv", type=float, default=0.10)
    parser.add_argument("--review-max-ratio", type=float, default=1.25)
    args = parser.parse_args()

    root = args.input_root.resolve()
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".nd2"
    )
    if not paths:
        raise SystemExit(f"No ND2 files found under {root}")

    rows = [
        audit_file(
            path,
            root,
            tuple(args.expected_channel_token),
            args.review_cv,
            args.review_max_ratio,
        )
        for path in paths
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    statuses = Counter(str(row["status"]) for row in rows)
    summary = {
        "input_root": str(root),
        "nd2_count": len(rows),
        "total_bytes": sum(int(row["size_bytes"]) for row in rows),
        "review_cv": args.review_cv,
        "review_max_ratio": args.review_max_ratio,
        "status_counts": dict(sorted(statuses.items())),
        "audit_csv": str(args.output.resolve()),
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"ND2_METADATA_AUDIT_OK={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
