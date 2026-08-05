#!/usr/bin/env python
"""Read DSB ND2 headers and join them to the audited smoke-run mapping."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re

import nd2


FIELDS = [
    "fov_literal",
    "nd2_filename",
    "biological_time_label",
    "filename_note",
    "bytes",
    "gib",
    "last_write_utc",
    "acquisition_datetime_text",
    "size_p",
    "size_t",
    "size_c",
    "size_z",
    "size_y",
    "size_x",
    "dtype",
    "pixel_size_x_um",
    "pixel_size_y_um",
    "z_calibration_um",
    "configured_period_ms",
    "observed_period_avg_ms",
    "observed_period_min_ms",
    "observed_period_max_ms",
    "channel_names",
    "exposure_ms",
    "objective",
    "camera",
    "smoke_unique_crops",
    "smoke_crop_indices",
    "v422_tasks",
    "v422_complete",
    "v422_failed_or_interrupted",
    "v5_tasks",
    "v5_complete",
    "v5_failed_or_interrupted",
    "drive_uploaded_crops",
    "drive_uploaded_tasks",
    "metadata_read_status",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def biological_time(fov: str) -> str:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)h", fov)
    return f"{match.group(1)}h" if match else ""


def filename_notes(fov: str) -> str:
    notes = []
    if "testforZH" in fov:
        notes.append("testforZH")
    elif "forZH" in fov:
        notes.append("forZH")
    if "samefovas26" in fov:
        notes.append("same FOV as 26")
    if "_1s" in fov:
        notes.append("filename says 1s")
    if "_5s" in fov:
        notes.append("filename says 5s")
    return "; ".join(notes)


def read_header(path: Path, row: dict[str, object]) -> None:
    with nd2.ND2File(path) as handle:
        sizes = dict(handle.sizes)
        for axis in "PTCZYX":
            row[f"size_{axis.lower()}"] = int(sizes.get(axis, 0))
        row["dtype"] = str(handle.dtype)
        voxel = handle.voxel_size()
        row["pixel_size_x_um"] = voxel.x
        row["pixel_size_y_um"] = voxel.y
        row["z_calibration_um"] = voxel.z

        info = handle.text_info or {}
        description = info.get("description", "") or ""
        row["acquisition_datetime_text"] = info.get("date", "") or ""
        row["objective"] = info.get("optics", "") or ""
        camera = re.search(r"Camera Name:\s*([^\r\n]+)", description)
        row["camera"] = camera.group(1).strip() if camera else ""
        planes = re.findall(
            r"Plane #\d+:\s*\r?\n\s*Name:\s*([^\r\n]+)", description
        )
        row["channel_names"] = " | ".join(item.strip() for item in planes)
        exposures = re.findall(r"Exposure:\s*([0-9.]+)\s*ms", description)
        row["exposure_ms"] = " | ".join(exposures[: len(planes) or None])

        for loop in handle.experiment:
            parameters = getattr(loop, "parameters", None)
            periods = getattr(parameters, "periods", []) if parameters else []
            if not periods:
                continue
            period = periods[0]
            row["configured_period_ms"] = getattr(period, "periodMs", "")
            difference = getattr(period, "periodDiff", None)
            if difference is not None:
                row["observed_period_avg_ms"] = getattr(difference, "avg", "")
                row["observed_period_min_ms"] = getattr(difference, "min", "")
                row["observed_period_max_ms"] = getattr(difference, "max", "")
            break


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--smoke-map", type=Path, required=True)
    parser.add_argument("--raw-base", type=Path, required=True)
    parser.add_argument("--drive-root", type=Path, required=True)
    parser.add_argument("--output-tsv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    sources = read_tsv(args.source_map)
    smoke = read_tsv(args.smoke_map)
    rows: list[dict[str, object]] = []

    for index, source in enumerate(sources, start=1):
        fov = source["fov_literal"]
        path = args.raw_base / fov / source["nd2_filename"]
        related = [item for item in smoke if item["literal_fov"] == fov]
        crop_indices = sorted({int(item["crop_index"]) for item in related})
        pair_keys = {item["pair_key"] for item in related}
        v422 = [item for item in related if item["version_slug"] == "v422"]
        v5 = [item for item in related if item["version_slug"] == "v5_dev1"]
        uploaded = [
            item
            for item in related
            if (args.drive_root / Path(item["target_drive_relative_dir"])).is_dir()
        ]
        uploaded_versions: dict[str, set[str]] = {}
        for item in uploaded:
            uploaded_versions.setdefault(item["pair_key"], set()).add(
                item["version_slug"]
            )

        row: dict[str, object] = {field: "" for field in FIELDS}
        row.update(
            {
                "fov_literal": fov,
                "nd2_filename": source["nd2_filename"],
                "biological_time_label": biological_time(fov),
                "filename_note": filename_notes(fov),
                "bytes": int(source["bytes"]),
                "gib": round(int(source["bytes"]) / (1024**3), 3),
                "last_write_utc": source["last_write_utc"],
                "smoke_unique_crops": len(pair_keys),
                "smoke_crop_indices": ",".join(map(str, crop_indices)),
                "v422_tasks": len(v422),
                "v422_complete": sum(
                    item["run_status"] == "complete" for item in v422
                ),
                "v422_failed_or_interrupted": sum(
                    item["run_status"] != "complete" for item in v422
                ),
                "v5_tasks": len(v5),
                "v5_complete": sum(
                    item["run_status"] == "complete" for item in v5
                ),
                "v5_failed_or_interrupted": sum(
                    item["run_status"] != "complete" for item in v5
                ),
                "drive_uploaded_crops": sum(
                    versions == {"v422", "v5_dev1"}
                    for versions in uploaded_versions.values()
                ),
                "drive_uploaded_tasks": len(uploaded),
            }
        )
        try:
            read_header(path, row)
            row["metadata_read_status"] = "OK"
        except Exception as error:  # preserve the row and report the exact failure
            row["metadata_read_status"] = (
                f"ERROR: {type(error).__name__}: {error}"
            )
        rows.append(row)
        print(
            f"READ {index:02d}/{len(sources)} {fov} "
            f"STATUS={row['metadata_read_status']}",
            flush=True,
        )

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "nd2_files": len(rows),
        "metadata_ok": sum(row["metadata_read_status"] == "OK" for row in rows),
        "metadata_error": sum(row["metadata_read_status"] != "OK" for row in rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "total_gib": round(sum(int(row["bytes"]) for row in rows) / (1024**3), 3),
        "smoke_fovs": sum(int(row["smoke_unique_crops"]) > 0 for row in rows),
        "smoke_unique_crops": sum(int(row["smoke_unique_crops"]) for row in rows),
        "v422_tasks": sum(int(row["v422_tasks"]) for row in rows),
        "v5_tasks": sum(int(row["v5_tasks"]) for row in rows),
        "drive_uploaded_fovs": sum(
            int(row["drive_uploaded_crops"]) > 0 for row in rows
        ),
        "drive_uploaded_crops": sum(
            int(row["drive_uploaded_crops"]) for row in rows
        ),
        "drive_uploaded_tasks": sum(
            int(row["drive_uploaded_tasks"]) for row in rows
        ),
    }
    args.output_json.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("SUMMARY=" + json.dumps(summary, ensure_ascii=False), flush=True)
    print(f"TSV={args.output_tsv}", flush=True)
    print(f"JSON={args.output_json}", flush=True)
    return 0 if summary["metadata_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

