#!/usr/bin/env bash
# Build a read-only, sidecar-grounded map from the 16-cell DSB smoke to Drive FOVs.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
DSB_RUN="$PROJECT/work/v5_dev1_real_smoke_20260729T183313Z"
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PROJECT/manifests/dsb_smoke_drive_mapping_$TAG"

test -d "$DSB_RUN"
mkdir -p "$OUT"

LATEST_INVENTORY="$(
    find "$PROJECT/manifests" -maxdepth 1 -type d \
        -name 'drive_migration_inventory_*' -printf '%T@\t%p\n' |
    sort -nr |
    head -n 1 |
    cut -f 2-
)"
test -n "$LATEST_INVENTORY"
test -f "$LATEST_INVENTORY/run_summary.tsv"
test -f "$LATEST_INVENTORY/run_manifests.tsv"
test -f "$LATEST_INVENTORY/symlinks.tsv"

rclone copyto \
    "$DRIVE_ROOT/manifests/SOURCE_ND2_MAP.tsv" \
    "$OUT/SOURCE_ND2_MAP.tsv"

module purge >/dev/null 2>&1 || true
module load system >/dev/null 2>&1 || true
module load python/3.12.1 >/dev/null 2>&1 || true
PYTHON="$PROJECT/env/py312_torch251_cu124_ml217/bin/python"
test -x "$PYTHON"

"$PYTHON" - "$DSB_RUN" "$OUT" <<'PY'
import csv
import json
from collections import defaultdict
from pathlib import Path
import re
import sys

run_root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()

with (out / "SOURCE_ND2_MAP.tsv").open(newline="", encoding="utf-8-sig") as handle:
    source_map = list(csv.DictReader(handle, delimiter="\t"))

by_name = defaultdict(list)
for row in source_map:
    by_name[row.get("nd2_filename", "").casefold()].append(row)

def normalized_parts(value: str):
    return [part for part in value.replace("\\", "/").split("/") if part]

def safe_slug(value: str):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("_") or "unknown"

def version_slug(version: str):
    normalized = version.strip()
    if normalized.casefold().startswith("v"):
        normalized = normalized[1:]
    if normalized.startswith("5.0.0-dev1"):
        return "v5_dev1"
    if normalized.startswith("4.2.2"):
        return "v422"
    return safe_slug(version)

fields = [
    "pair_key", "version_slug", "pipeline_version", "run_status",
    "manifest_path", "source_task_dir", "source_task_files", "source_task_bytes",
    "crop_tiff", "crop_exists", "crop_bytes", "sidecar_path", "sidecar_status",
    "source_nd2_raw", "source_nd2_name", "crop_stem", "crop_index",
    "literal_fov", "source_drive_relative_path", "mapping_evidence",
    "mapping_status", "target_drive_relative_dir",
]

rows = []
for manifest in sorted(run_root.rglob("run_manifest.json")):
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        rows.append({
            "manifest_path": str(manifest),
            "sidecar_status": f"MANIFEST_UNREADABLE:{type(exc).__name__}",
            "mapping_status": "UNRESOLVED",
        })
        continue

    crop = Path(str(data.get("crop_tiff", "")))
    sidecar = crop.with_name(crop.stem + "_metadata.json") if crop.name else Path("")
    sidecar_status = "PRESENT"
    sidecar_data = {}
    if not crop.name or not sidecar.is_file():
        sidecar_status = "MISSING"
    else:
        try:
            sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception as exc:
            sidecar_status = f"UNREADABLE:{type(exc).__name__}"

    source_nd2 = str(sidecar_data.get("source_nd2", ""))
    parts = normalized_parts(source_nd2)
    nd2_name = parts[-1] if parts else ""
    candidates = list(by_name.get(nd2_name.casefold(), []))
    exact_fov = [
        row for row in candidates
        if row.get("fov_literal", "").casefold() in {part.casefold() for part in parts}
    ]

    selected = None
    evidence = ""
    if len(exact_fov) == 1:
        selected = exact_fov[0]
        evidence = "sidecar_source_nd2_exact_fov_and_filename"
    elif len(candidates) == 1:
        selected = candidates[0]
        evidence = "sidecar_source_nd2_unique_filename"

    mapping_status = "MAPPED" if selected is not None else "UNRESOLVED"
    literal_fov = selected.get("fov_literal", "") if selected else ""
    source_drive = selected.get("source_drive_relative_path", "") if selected else ""
    stem = str(sidecar_data.get("stem", crop.stem))
    crop_index = str(sidecar_data.get("crop_index", ""))
    pair_key = f"{literal_fov}|{stem}|{crop_index}" if selected else ""
    version = str(data.get("version", ""))
    vslug = version_slug(version)
    task_dir = crop.parent if crop.name else manifest.parent

    task_files = 0
    task_bytes = 0
    if task_dir.is_dir():
        for path in task_dir.rglob("*"):
            if path.is_file():
                task_files += 1
                task_bytes += path.stat().st_size

    target = ""
    if selected:
        target = (
            f"dsb_v5_results/a/{literal_fov}/"
            f"validation_smoke_20260729/{vslug}/{task_dir.name}"
        )

    rows.append({
        "pair_key": pair_key,
        "version_slug": vslug,
        "pipeline_version": version,
        "run_status": data.get("status", ""),
        "manifest_path": str(manifest),
        "source_task_dir": str(task_dir),
        "source_task_files": task_files,
        "source_task_bytes": task_bytes,
        "crop_tiff": str(crop),
        "crop_exists": str(crop.is_file()),
        "crop_bytes": crop.stat().st_size if crop.is_file() else 0,
        "sidecar_path": str(sidecar),
        "sidecar_status": sidecar_status,
        "source_nd2_raw": source_nd2,
        "source_nd2_name": nd2_name,
        "crop_stem": stem,
        "crop_index": crop_index,
        "literal_fov": literal_fov,
        "source_drive_relative_path": source_drive,
        "mapping_evidence": evidence,
        "mapping_status": mapping_status,
        "target_drive_relative_dir": target,
    })

map_path = out / "DSB_SMOKE_TO_DRIVE_MAP.tsv"
with map_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)

groups = defaultdict(list)
for row in rows:
    groups[row["pair_key"]].append(row)

pair_fields = [
    "pair_key", "literal_fov", "source_nd2_name", "crop_stem", "crop_index",
    "versions", "row_count", "pair_status",
]
pair_rows = []
for key, items in sorted(groups.items()):
    versions = sorted(item["version_slug"] for item in items)
    complete = bool(key) and versions == ["v422", "v5_dev1"]
    pair_rows.append({
        "pair_key": key,
        "literal_fov": items[0]["literal_fov"],
        "source_nd2_name": items[0]["source_nd2_name"],
        "crop_stem": items[0]["crop_stem"],
        "crop_index": items[0]["crop_index"],
        "versions": ",".join(versions),
        "row_count": len(items),
        "pair_status": "COMPLETE_V422_V5" if complete else "REVIEW",
    })

with (out / "DSB_SMOKE_PAIRS.tsv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=pair_fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(pair_rows)

metrics = {
    "SOURCE_MAP_ROWS": len(source_map),
    "RUN_MANIFESTS": len(rows),
    "CROP_FILES_PRESENT": sum(row["crop_exists"] == "True" for row in rows),
    "SIDECARS_PRESENT": sum(row["sidecar_status"] == "PRESENT" for row in rows),
    "MAPPED_ROWS": sum(row["mapping_status"] == "MAPPED" for row in rows),
    "UNRESOLVED_ROWS": sum(row["mapping_status"] != "MAPPED" for row in rows),
    "UNIQUE_PAIRS": len(pair_rows),
    "COMPLETE_V422_V5_PAIRS": sum(
        row["pair_status"] == "COMPLETE_V422_V5" for row in pair_rows
    ),
    "REVIEW_PAIRS": sum(row["pair_status"] != "COMPLETE_V422_V5" for row in pair_rows),
    "UNIQUE_TARGET_DIRS": len({row["target_drive_relative_dir"] for row in rows if row["target_drive_relative_dir"]}),
    "TASK_FILES_SUM": sum(int(row["source_task_files"]) for row in rows),
    "TASK_BYTES_SUM": sum(int(row["source_task_bytes"]) for row in rows),
}

gate = (
    metrics["SOURCE_MAP_ROWS"] == 30
    and metrics["RUN_MANIFESTS"] == 32
    and metrics["CROP_FILES_PRESENT"] == 32
    and metrics["SIDECARS_PRESENT"] == 32
    and metrics["MAPPED_ROWS"] == 32
    and metrics["UNRESOLVED_ROWS"] == 0
    and metrics["UNIQUE_PAIRS"] == 16
    and metrics["COMPLETE_V422_V5_PAIRS"] == 16
    and metrics["REVIEW_PAIRS"] == 0
    and metrics["UNIQUE_TARGET_DIRS"] == 32
)
metrics["FINAL_GATE"] = "PASS" if gate else "REVIEW_REQUIRED"

with (out / "mapping_summary.txt").open("w", encoding="utf-8") as handle:
    for key, value in metrics.items():
        handle.write(f"{key}={value}\n")

(out / "gate.txt").write_text(metrics["FINAL_GATE"] + "\n", encoding="utf-8")
PY

INVENTORY_REMOTE="$DRIVE_ROOT/sherlock_handoff/inventories/$(basename "$LATEST_INVENTORY")"
MAPPING_REMOTE="$DRIVE_ROOT/sherlock_handoff/mappings/$(basename "$OUT")"

if rclone lsf "$INVENTORY_REMOTE" >/dev/null 2>&1
then
    rclone check "$LATEST_INVENTORY" "$INVENTORY_REMOTE"
else
    rclone copy "$LATEST_INVENTORY" "$INVENTORY_REMOTE" --transfers 4 --checkers 8
    rclone check "$LATEST_INVENTORY" "$INVENTORY_REMOTE"
fi

if rclone lsf "$MAPPING_REMOTE" >/dev/null 2>&1
then
    echo "ERROR: mapping remote already exists: $MAPPING_REMOTE" >&2
    exit 1
fi
rclone copy "$OUT" "$MAPPING_REMOTE" --transfers 4 --checkers 8
rclone check "$OUT" "$MAPPING_REMOTE"

echo '========== DSB SMOKE MAPPING SUMMARY =========='
cat "$OUT/mapping_summary.txt"
echo
echo '========== DSB SMOKE PAIRS =========='
column -t -s $'\t' "$OUT/DSB_SMOKE_PAIRS.tsv" 2>/dev/null || cat "$OUT/DSB_SMOKE_PAIRS.tsv"
echo
echo "LOCAL_MAPPING=$OUT"
echo "DRIVE_MAPPING=$MAPPING_REMOTE"
echo "DRIVE_INVENTORY=$INVENTORY_REMOTE"

test "$(tr -d '\r\n' < "$OUT/gate.txt")" = 'PASS'
echo 'DSB_SMOKE_DRIVE_MAPPING_OK'
