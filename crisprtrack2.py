#!/usr/bin/env python3
"""Run the frozen v5.2.1 extraction stages from a portable JSON configuration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STAGES = ("segment", "export", "track")


def options(values: dict, *, reserved: set[str] = frozenset()) -> list[str]:
    result = []
    for key, value in values.items():
        if key.startswith("-") or key in reserved:
            raise ValueError(f"Invalid or workflow-owned option: {key}")
        if value is None:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if key in {"resume", "preserve_all_candidates"}:
                result.append(flag if value else "--no-" + flag[2:])
            elif value:
                result.append(flag)
        else:
            result.extend([flag, str(value)])
    return result


def commands(config: dict, source: Path, runroot: Path, stage: str) -> list[list[str]]:
    unknown = set(config) - {"segmentation", "tracking"}
    if unknown:
        raise ValueError(f"Unknown configuration sections: {sorted(unknown)}")
    segmented = runroot / "segmented"
    candidates = runroot / "all_usam_candidates"
    py = sys.executable
    stage_commands = {
        "segment": [py, str(ROOT / "nucleus_segmentation/crop_nuclei_sam.py"), str(source),
                    "--output-root", str(segmented), "--candidate-output-root", str(candidates)]
                   + options(config.get("segmentation", {}), reserved={"input", "output_root", "candidate_output_root"}),
        "export": [py, str(ROOT / "nucleus_segmentation/save_crops.py"), str(segmented), "--no-include-sibling-candidates"],
        "track": [py, str(ROOT / "trajectory_extraction/run_batch_pipeline_v4.py"), str(segmented),
                  "--crop-glob", "**/*.tif"]
                 + options(config.get("tracking", {}), reserved={"crop_dir", "crop_glob"}),
    }
    return [stage_commands[s] for s in (STAGES if stage == "all" else [stage])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="JSON containing segmentation and tracking options")
    parser.add_argument("--input", type=Path, required=True, help="ND2 file or directory; only read by the segment stage")
    parser.add_argument("--run-root", type=Path, required=True, help="Dedicated output root; segment/all require a new directory")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--plan", action="store_true", help="Print commands without running applications or writing output")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    source, runroot = args.input.resolve(), args.run_root.resolve()
    if runroot == source or source in runroot.parents or runroot in source.parents:
        parser.error("Input and run-root must be separate, non-overlapping paths")
    try:
        planned = commands(config, source, runroot, args.stage)
    except ValueError as exc:
        parser.error(str(exc))
    if args.plan:
        for command in planned:
            print(json.dumps(command, ensure_ascii=False))
        return
    if args.stage in {"all", "segment"}:
        if not source.exists():
            parser.error(f"ND2 input does not exist: {source}")
        if runroot.exists():
            parser.error("segment/all require a new run-root; resume with --stage export or --stage track")
        runroot.mkdir(parents=True)
    elif not (runroot / "segmented").is_dir():
        parser.error(f"Missing segmentation output: {runroot / 'segmented'}")
    (runroot / "workflow_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (runroot / "workflow_commands.json").write_text(json.dumps(planned, indent=2), encoding="utf-8")
    for command in planned:
        subprocess.run(command, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
