#!/usr/bin/env bash
# Upload only the six audited v4.2.2/v5 task directories for fov7_testforZH.
# This is a non-destructive pilot for timing and Drive-layout review.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
RUN_ROOT="$PROJECT/work/v5_dev1_real_smoke_20260729T183313Z"
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
LITERAL_FOV='fov7_testforZH'
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PROJECT/work/rclone_uploads/dsb_smoke_fov7_test_$TAG"
REPORT_REMOTE="$DRIVE_ROOT/sherlock_handoff/transfers/dsb_smoke_fov7_test_$TAG"

MAPPING="$(
    find "$PROJECT/manifests" -maxdepth 1 -type d \
        -name 'dsb_smoke_drive_mapping_*' -printf '%T@\t%p\n' |
    sort -nr |
    while IFS=$'\t' read -r _ path
    do
        if test -f "$path/gate.txt" && \
            test "$(tr -d '\r\n' < "$path/gate.txt")" = 'PASS'
        then
            printf '%s\n' "$path"
            break
        fi
    done
)"

test -d "$RUN_ROOT"
test -n "$MAPPING"
test -f "$MAPPING/DSB_SMOKE_TO_DRIVE_MAP.tsv"
test "$(tr -d '\r\n' < "$MAPPING/gate.txt")" = 'PASS'
command -v rclone >/dev/null
mkdir -p "$OUT"

module purge >/dev/null 2>&1 || true
module load system >/dev/null 2>&1 || true
module load python/3.12.1 >/dev/null 2>&1 || true
hash -r
PYTHON="$PROJECT/env/py312_torch251_cu124_ml217/bin/python"
test -x "$PYTHON"

echo '========== FOV7 PILOT CONFIG =========='
echo "RUN_ROOT=$RUN_ROOT"
echo "MAPPING=$MAPPING"
echo "LITERAL_FOV=$LITERAL_FOV"
echo "OUT=$OUT"
echo "REPORT_REMOTE=$REPORT_REMOTE"

set +e
"$PYTHON" - \
    "$RUN_ROOT" "$MAPPING" "$DRIVE_ROOT" "$LITERAL_FOV" "$OUT" <<'PY'
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

run_root = Path(sys.argv[1]).resolve()
mapping_dir = Path(sys.argv[2]).resolve()
drive_root = sys.argv[3].rstrip("/")
literal_fov = sys.argv[4]
out = Path(sys.argv[5]).resolve()
logs = out / "logs"
logs.mkdir(parents=True, exist_ok=True)

mapping_file = mapping_dir / "DSB_SMOKE_TO_DRIVE_MAP.tsv"
with mapping_file.open(newline="", encoding="utf-8-sig") as handle:
    all_rows = list(csv.DictReader(handle, delimiter="\t"))

rows = [row for row in all_rows if row["literal_fov"] == literal_fov]
rows.sort(key=lambda row: (row["crop_index"], row["version_slug"]))

if len(rows) != 6:
    raise SystemExit(f"Expected 6 fov7 rows, found {len(rows)}")
if len({row["pair_key"] for row in rows}) != 3:
    raise SystemExit("Expected 3 unique fov7 pairs")
if {row["version_slug"] for row in rows} != {"v422", "v5_dev1"}:
    raise SystemExit("Expected both v422 and v5_dev1")
if len({row["source_task_dir"] for row in rows}) != 6:
    raise SystemExit("Source task directories are not unique")
if len({row["target_drive_relative_dir"] for row in rows}) != 6:
    raise SystemExit("Drive target directories are not unique")

selected_fields = list(rows[0])
with (out / "selected_mapping.tsv").open(
    "w", newline="", encoding="utf-8"
) as handle:
    writer = csv.DictWriter(handle, fieldnames=selected_fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)

total_files = 0
total_bytes = 0
for row in rows:
    source = Path(row["source_task_dir"]).resolve()
    if not source.is_dir():
        raise SystemExit(f"Missing source task directory: {source}")
    files = 0
    size = 0
    nd2 = 0
    for root, dirs, names in os.walk(source, followlinks=False):
        dirs.sort()
        names.sort()
        for name in names:
            path = Path(root) / name
            if not path.is_file():
                continue
            files += 1
            size += path.stat().st_size
            if name.lower().endswith(".nd2"):
                nd2 += 1
    if files != int(row["source_task_files"]):
        raise SystemExit(f"File-count mismatch for {source}: {files}")
    if size != int(row["source_task_bytes"]):
        raise SystemExit(f"Byte-count mismatch for {source}: {size}")
    if nd2 != 0:
        raise SystemExit(f"Unexpected ND2 file under {source}")
    total_files += files
    total_bytes += size

preflight = {
    "literal_fov": literal_fov,
    "task_rows": len(rows),
    "unique_pairs": len({row["pair_key"] for row in rows}),
    "versions": sorted({row["version_slug"] for row in rows}),
    "source_files": total_files,
    "source_bytes": total_bytes,
    "source_gib": round(total_bytes / (1024 ** 3), 3),
}
(out / "preflight.json").write_text(
    json.dumps(preflight, indent=2), encoding="utf-8"
)
print("========== FOV7 PREFLIGHT ==========", flush=True)
print(json.dumps(preflight, indent=2), flush=True)

def run_command(command, log_path):
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("COMMAND=" + json.dumps(command) + "\n")
        handle.flush()
        completed = subprocess.run(
            command, stdout=handle, stderr=subprocess.STDOUT
        )
    return completed.returncode, time.monotonic() - started

def transfer_one(index_row):
    index, row = index_row
    source = Path(row["source_task_dir"]).resolve()
    destination = f"{drive_root}/{row['target_drive_relative_dir']}"
    label = f"{index:02d}_{row['version_slug']}_{source.name}"
    print(
        f"START TASK={index:02d} VERSION={row['version_slug']} "
        f"CROP_INDEX={row['crop_index']}",
        flush=True,
    )
    copy_command = [
        "rclone", "copy", str(source), destination,
        "--exclude", "*.nd2", "--exclude", "*.ND2",
        "--transfers", "16", "--checkers", "32", "--fast-list",
        "--stats", "60s",
    ]
    copy_status, copy_seconds = run_command(
        copy_command, logs / f"{label}_copy.log"
    )
    check_status = "SKIPPED"
    check_seconds = 0.0
    if copy_status == 0:
        check_command = [
            "rclone", "check", str(source), destination,
            "--exclude", "*.nd2", "--exclude", "*.ND2",
            "--checkers", "32",
        ]
        check_status, check_seconds = run_command(
            check_command, logs / f"{label}_check.log"
        )
    result = dict(row)
    result.update({
        "destination": destination,
        "copy_status": str(copy_status),
        "check_status": str(check_status),
        "copy_seconds": f"{copy_seconds:.1f}",
        "check_seconds": f"{check_seconds:.1f}",
    })
    print(
        f"FINISH TASK={index:02d} VERSION={row['version_slug']} "
        f"CROP_INDEX={row['crop_index']} COPY={copy_status} "
        f"CHECK={check_status} COPY_SECONDS={copy_seconds:.1f}",
        flush=True,
    )
    return result

wall_started = time.monotonic()
results = []
for pair in enumerate(rows, start=1):
    results.append(transfer_one(pair))
wall_seconds = time.monotonic() - wall_started

results.sort(
    key=lambda row: (row["crop_index"], row["version_slug"])
)
report_fields = selected_fields + [
    "destination", "copy_status", "check_status",
    "copy_seconds", "check_seconds",
]
with (out / "task_transfer_report.tsv").open(
    "w", newline="", encoding="utf-8"
) as handle:
    writer = csv.DictWriter(handle, fieldnames=report_fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(results)

copy_failures = sum(row["copy_status"] != "0" for row in results)
check_failures = sum(row["check_status"] != "0" for row in results)
full_dsb_files = 2719
full_dsb_bytes = 5476080872

def clock(seconds):
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

byte_projection = (
    wall_seconds * full_dsb_bytes / total_bytes if total_bytes else 0
)
file_projection = (
    wall_seconds * full_dsb_files / total_files if total_files else 0
)
summary = {
    **preflight,
    "parallel_task_workers": 1,
    "rclone_transfers_per_task": 16,
    "copy_failures": copy_failures,
    "check_failures": check_failures,
    "wall_seconds_including_checks": round(wall_seconds, 1),
    "wall_hhmmss": clock(wall_seconds),
    "effective_mib_per_second": round(
        total_bytes / wall_seconds / (1024 ** 2), 3
    ) if wall_seconds else 0,
    "rough_full_dsb_projection_by_bytes": clock(byte_projection),
    "rough_full_dsb_projection_by_file_count": clock(file_projection),
    "projection_warning": (
        "Rough DSB-only estimates; Google Drive API throttling and file-size "
        "distribution can change full-run time."
    ),
}
summary["final_gate"] = (
    "PASS" if copy_failures == 0 and check_failures == 0 else "RETRY_REQUIRED"
)
(out / "transfer_summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
(out / "gate.txt").write_text(summary["final_gate"] + "\n", encoding="utf-8")
print("========== FOV7 TRANSFER SUMMARY ==========", flush=True)
print(json.dumps(summary, indent=2), flush=True)
raise SystemExit(0 if summary["final_gate"] == "PASS" else 1)
PY
PYTHON_STATUS=$?
set -e

REPORT_COPY_STATUS=0
rclone copy "$OUT" "$REPORT_REMOTE" \
    --transfers 4 \
    --checkers 8 || REPORT_COPY_STATUS=$?

REPORT_CHECK_STATUS='SKIPPED'
if test "$REPORT_COPY_STATUS" -eq 0
then
    REPORT_CHECK_STATUS=0
    rclone check "$OUT" "$REPORT_REMOTE" \
        --checkers 8 || REPORT_CHECK_STATUS=$?
fi

echo '========== FOV7 PILOT FINAL =========='
if test -f "$OUT/transfer_summary.json"
then
    cat "$OUT/transfer_summary.json"
fi
echo "LOCAL_REPORT=$OUT"
echo "DRIVE_REPORT=$REPORT_REMOTE"
echo "PYTHON_STATUS=$PYTHON_STATUS"
echo "REPORT_COPY_STATUS=$REPORT_COPY_STATUS"
echo "REPORT_CHECK_STATUS=$REPORT_CHECK_STATUS"

test "$PYTHON_STATUS" -eq 0
test "$REPORT_COPY_STATUS" -eq 0
test "$REPORT_CHECK_STATUS" = 0
test "$(tr -d '\r\n' < "$OUT/gate.txt")" = 'PASS'
echo 'DSB_SMOKE_FOV7_DRIVE_TEST_OK'
