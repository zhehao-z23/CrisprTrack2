#!/usr/bin/env bash
# Copy all 32 DSB smoke task directories into their sidecar-audited literal FOVs.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
RUN_ROOT="$PROJECT/work/v5_dev1_real_smoke_20260729T183313Z"
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PROJECT/work/rclone_uploads/dsb_smoke_mapped_$TAG"
TRANSFER_REMOTE="$DRIVE_ROOT/sherlock_handoff/transfers/dsb_smoke_mapped_$TAG"
PROVENANCE_REMOTE="$DRIVE_ROOT/dsb_v5_results/run_provenance/$(basename "$RUN_ROOT")"

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
mkdir -p "$OUT"

module purge >/dev/null 2>&1 || true
module load system >/dev/null 2>&1 || true
module load python/3.12.1 >/dev/null 2>&1 || true
hash -r
test -x "$PROJECT/env/py312_torch251_cu124_ml217/bin/python"

set +e
"$PROJECT/env/py312_torch251_cu124_ml217/bin/python" - \
    "$RUN_ROOT" "$MAPPING" "$DRIVE_ROOT" "$PROVENANCE_REMOTE" "$OUT" <<'PY'
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

run_root = Path(sys.argv[1]).resolve()
mapping_dir = Path(sys.argv[2]).resolve()
drive_root = sys.argv[3]
provenance_remote = sys.argv[4]
out = Path(sys.argv[5]).resolve()
logs = out / "task_logs"
logs.mkdir(parents=True, exist_ok=True)

with (mapping_dir / "DSB_SMOKE_TO_DRIVE_MAP.tsv").open(
    newline="", encoding="utf-8-sig"
) as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

if len(rows) != 32:
    raise SystemExit(f"Expected 32 mapping rows, found {len(rows)}")
if any(row["mapping_status"] != "MAPPED" for row in rows):
    raise SystemExit("Mapping contains unresolved rows")
if len({row["source_task_dir"] for row in rows}) != 32:
    raise SystemExit("Source task directories are not unique")
if len({row["target_drive_relative_dir"] for row in rows}) != 32:
    raise SystemExit("Drive target directories are not unique")

def run_command(command, log_path):
    started = time.time()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("COMMAND=" + json.dumps(command) + "\n")
        handle.flush()
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    return completed.returncode, time.time() - started

def transfer_one(index_row):
    index, row = index_row
    source = Path(row["source_task_dir"]).resolve()
    if not source.is_dir():
        return {**row, "copy_status": "SOURCE_MISSING", "check_status": "SKIPPED"}
    destination = f"{drive_root}/{row['target_drive_relative_dir']}"
    label = f"{index:02d}_{row['version_slug']}_{source.name}"
    copy_cmd = [
        "rclone", "copy", str(source), destination,
        "--exclude", "*.nd2", "--exclude", "*.ND2",
        "--transfers", "16", "--checkers", "32", "--fast-list",
        "--stats", "60s",
    ]
    copy_status, copy_seconds = run_command(copy_cmd, logs / f"{label}_copy.log")
    check_status = "SKIPPED"
    check_seconds = 0.0
    if copy_status == 0:
        check_cmd = [
            "rclone", "check", str(source), destination,
            "--exclude", "*.nd2", "--exclude", "*.ND2",
            "--checkers", "32",
        ]
        check_status, check_seconds = run_command(
            check_cmd, logs / f"{label}_check.log"
        )
    result = dict(row)
    result.update({
        "destination": destination,
        "copy_status": str(copy_status),
        "check_status": str(check_status),
        "copy_seconds": f"{copy_seconds:.1f}",
        "check_seconds": f"{check_seconds:.1f}",
    })
    return result

results = []
for pair in enumerate(rows, start=1):
    index = pair[0]
    print(f"START TASK={index:02d}", flush=True)
    result = transfer_one(pair)
    results.append(result)
    print(
        f"FINISH TASK={index:02d} VERSION={result.get('version_slug')} "
        f"COPY={result.get('copy_status')} CHECK={result.get('check_status')}",
        flush=True,
    )

results.sort(key=lambda row: (row["literal_fov"], row["version_slug"], row["source_task_dir"]))
report_fields = list(rows[0]) + [
    "destination", "copy_status", "check_status", "copy_seconds", "check_seconds"
]
with (out / "task_transfer_report.tsv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=report_fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(results)

# Preserve the 76 small run-level files that are outside all 32 mapped task dirs.
task_dirs = [Path(row["source_task_dir"]).resolve() for row in rows]
non_task_root = out / "non_task_provenance"
non_task_files = 0
non_task_bytes = 0
for path in run_root.rglob("*"):
    if not path.is_file():
        continue
    resolved = path.resolve()
    if any(resolved == task or task in resolved.parents for task in task_dirs):
        continue
    relative = path.relative_to(run_root)
    target = non_task_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    non_task_files += 1
    non_task_bytes += path.stat().st_size

provenance_copy, provenance_copy_seconds = run_command(
    [
        "rclone", "copy", str(non_task_root), provenance_remote,
        "--exclude", "*.nd2", "--exclude", "*.ND2",
        "--transfers", "4", "--checkers", "8", "--fast-list",
    ],
    out / "run_provenance_copy.log",
)
provenance_check = "SKIPPED"
provenance_check_seconds = 0.0
if provenance_copy == 0:
    provenance_check, provenance_check_seconds = run_command(
        [
            "rclone", "check", str(non_task_root), provenance_remote,
            "--exclude", "*.nd2", "--exclude", "*.ND2",
            "--checkers", "8",
        ],
        out / "run_provenance_check.log",
    )

copy_failures = sum(row["copy_status"] != "0" for row in results)
check_failures = sum(row["check_status"] != "0" for row in results)
summary = {
    "mapping_dir": str(mapping_dir),
    "task_rows": len(results),
    "copy_failures": copy_failures,
    "check_failures": check_failures,
    "non_task_files": non_task_files,
    "non_task_bytes": non_task_bytes,
    "provenance_copy_status": str(provenance_copy),
    "provenance_check_status": str(provenance_check),
    "provenance_copy_seconds": round(provenance_copy_seconds, 1),
    "provenance_check_seconds": round(provenance_check_seconds, 1),
}
summary["final_gate"] = (
    "PASS"
    if copy_failures == 0
    and check_failures == 0
    and provenance_copy == 0
    and provenance_check == 0
    and non_task_files == 76
    and non_task_bytes == 79747
    else "RETRY_REQUIRED"
)
(out / "transfer_summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
(out / "gate.txt").write_text(summary["final_gate"] + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2), flush=True)
raise SystemExit(0 if summary["final_gate"] == "PASS" else 1)
PY
PYTHON_STATUS=$?
set -e

rclone copy "$OUT" "$TRANSFER_REMOTE" \
    --exclude 'non_task_provenance/**' \
    --transfers 4 \
    --checkers 8
rclone check "$OUT" "$TRANSFER_REMOTE" \
    --exclude 'non_task_provenance/**'

echo '========== DSB MAPPED UPLOAD SUMMARY =========='
cat "$OUT/transfer_summary.json"
echo "TRANSFER_REMOTE=$TRANSFER_REMOTE"
echo "PROVENANCE_REMOTE=$PROVENANCE_REMOTE"

test "$PYTHON_STATUS" -eq 0
test "$(tr -d '\r\n' < "$OUT/gate.txt")" = 'PASS'
echo 'DSB_SMOKE_MAPPED_DRIVE_UPLOAD_OK'
