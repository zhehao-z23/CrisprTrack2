#!/usr/bin/env bash
# Read-only source scan plus a new inventory directory. It never edits run roots.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
PUBLISHED_RUN="$PROJECT/work/published_exact219_v422_v5_20260729T205411Z"
DSB_SMOKE="$PROJECT/work/v5_dev1_real_smoke_20260729T183313Z"
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PROJECT/manifests/drive_migration_inventory_$TAG"

mkdir -p "$OUT"

for required in "$PUBLISHED_RUN" "$DSB_SMOKE"
do
    test -d "$required" || {
        printf 'ERROR_MISSING_RUN=%s\n' "$required" >&2
        exit 1
    }
done

printf 'run_kind\trun_root\tfiles\tbytes\ttif_files\ttif_bytes\tcsv_files\tjson_files\tpng_files\tsvg_files\tmat_files\n' \
    > "$OUT/run_summary.tsv"

summarize_run() {
    local kind="$1"
    local root="$2"
    local list="$OUT/${kind}_files.tsv"

    printf 'relative_path\tbytes\tmtime_source_timezone\n' > "$list"
    find "$root" -type f -printf '%P\t%s\t%TY-%Tm-%TdT%TH:%TM:%TS%Tz\n' \
        | LC_ALL=C sort >> "$list"

    awk -F '\t' -v kind="$kind" -v root="$root" '
        NR == 1 { next }
        {
            n += 1; bytes += $2;
            name = tolower($1)
            if (name ~ /\.(tif|tiff)$/) { tif += 1; tifbytes += $2 }
            if (name ~ /\.csv$/) csv += 1
            if (name ~ /\.json$/) json += 1
            if (name ~ /\.png$/) png += 1
            if (name ~ /\.svg$/) svg += 1
            if (name ~ /\.mat$/) mat += 1
        }
        END {
            printf "%s\t%s\t%d\t%.0f\t%d\t%.0f\t%d\t%d\t%d\t%d\t%d\n", \
                kind, root, n, bytes, tif, tifbytes, csv, json, png, svg, mat
        }
    ' "$list" >> "$OUT/run_summary.tsv"
}

summarize_run published_exact219 "$PUBLISHED_RUN"
summarize_run dsb_smoke "$DSB_SMOKE"

printf 'run_kind\trelative_link\ttarget\n' > "$OUT/symlinks.tsv"
for pair in "published_exact219|$PUBLISHED_RUN" "dsb_smoke|$DSB_SMOKE"
do
    kind="${pair%%|*}"
    root="${pair#*|}"
    while IFS= read -r -d '' link
    do
        relative="${link#"$root"/}"
        target="$(readlink "$link" || true)"
        printf '%s\t%s\t%s\n' "$kind" "$relative" "$target" >> "$OUT/symlinks.tsv"
    done < <(find "$root" -type l -print0)
done

# Collect manifest paths and selected provenance fields without requiring third-party packages.
module purge >/dev/null 2>&1 || true
module load system >/dev/null 2>&1 || true
module load python/3.12.1 >/dev/null 2>&1 || true

PYTHON="$PROJECT/env/py312_torch251_cu124_ml217/bin/python"
test -x "$PYTHON"

"$PYTHON" - "$OUT" "$PUBLISHED_RUN" "$DSB_SMOKE" <<'PY'
import csv
import json
from pathlib import Path
import sys

out = Path(sys.argv[1])
runs = {
    "published_exact219": Path(sys.argv[2]),
    "dsb_smoke": Path(sys.argv[3]),
}

fields = [
    "run_kind", "manifest_path", "version", "status", "crop_tiff",
    "analysis_dir", "results_dir", "experiment_profile", "source_nd2",
]
with (out / "run_manifests.tsv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for kind, root in runs.items():
        for path in sorted(root.rglob("run_manifest.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                writer.writerow({
                    "run_kind": kind,
                    "manifest_path": str(path),
                    "status": f"UNREADABLE:{type(exc).__name__}",
                })
                continue
            profile = data.get("experiment_profile", "")
            source_nd2 = data.get("source_nd2", "")
            if not source_nd2:
                validation = data.get("profile_validation") or {}
                source_nd2 = validation.get("source_nd2", "")
            writer.writerow({
                "run_kind": kind,
                "manifest_path": str(path),
                "version": data.get("version", ""),
                "status": data.get("status", ""),
                "crop_tiff": data.get("crop_tiff", ""),
                "analysis_dir": data.get("analysis_dir", ""),
                "results_dir": data.get("results_dir", ""),
                "experiment_profile": profile,
                "source_nd2": source_nd2,
            })
PY

cp -p "$PROJECT/incoming_20260720/manuscript_reference/published_to_original_bundle_mapping.csv" \
    "$OUT/" 2>/dev/null || true

{
    printf 'CREATED_UTC=%s\n' "$TAG"
    printf 'PROJECT=%s\n' "$PROJECT"
    printf 'PUBLISHED_RUN=%s\n' "$PUBLISHED_RUN"
    printf 'DSB_SMOKE=%s\n' "$DSB_SMOKE"
    printf 'INVENTORY_DIR=%s\n' "$OUT"
    printf 'RUN_MANIFEST_ROWS=%s\n' "$(( $(wc -l < "$OUT/run_manifests.tsv") - 1 ))"
} > "$OUT/inventory.env"

echo '========== RUN SUMMARY =========='
column -t -s $'\t' "$OUT/run_summary.tsv" 2>/dev/null || cat "$OUT/run_summary.tsv"
echo
echo '========== MANIFEST COUNTS =========='
awk -F '\t' 'NR > 1 { count[$1] += 1 } END { for (k in count) print k, count[k] }' \
    "$OUT/run_manifests.tsv" | sort
echo
echo '========== FIRST 20 MANIFEST ROWS =========='
sed -n '1,21p' "$OUT/run_manifests.tsv"
echo
echo '========== SYMLINK COUNTS =========='
awk -F '\t' 'NR > 1 { count[$1] += 1 } END { for (k in count) print k, count[k] }' \
    "$OUT/symlinks.tsv" | sort
echo
echo '========== FIRST 30 SYMLINKS =========='
sed -n '1,31p' "$OUT/symlinks.tsv"
echo
printf 'INVENTORY_DIR=%s\n' "$OUT"
echo 'V5_RESULT_INVENTORY_OK'
