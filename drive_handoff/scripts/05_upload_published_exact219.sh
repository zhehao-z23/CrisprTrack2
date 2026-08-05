#!/usr/bin/env bash
# Copy the complete published v4.2.2/v5 run tree to Drive; never delete or move.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
SOURCE="$PROJECT/work/published_exact219_v422_v5_20260729T205411Z"
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
DEST="$DRIVE_ROOT/published_validation/$(basename "$SOURCE")"
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="$PROJECT/work/rclone_uploads/published_exact219_$TAG"
REPORT_REMOTE="$DRIVE_ROOT/sherlock_handoff/transfers/published_exact219_$TAG"

EXPECTED_FILES=31519
EXPECTED_BYTES=23750223546
EXPECTED_TIFF_FILES=6388
EXPECTED_TIFF_BYTES=22820032322

test -d "$SOURCE"
mkdir -p "$REPORT_DIR"

read -r ACTUAL_FILES ACTUAL_BYTES ACTUAL_TIFF_FILES ACTUAL_TIFF_BYTES ND2_FILES SYMLINKS < <(
    find "$SOURCE" -type f -printf '%s\t%f\n' |
    awk -F '\t' '
        {
            files += 1; bytes += $1;
            name = tolower($2);
            if (name ~ /\.(tif|tiff)$/) { tifs += 1; tifbytes += $1 }
            if (name ~ /\.nd2$/) nd2 += 1
        }
        END { printf "%d %.0f %d %.0f %d ", files, bytes, tifs, tifbytes, nd2 }
    '
    find "$SOURCE" -type l | wc -l
)

{
    printf 'SOURCE=%s\n' "$SOURCE"
    printf 'DEST=%s\n' "$DEST"
    printf 'STARTED_UTC=%s\n' "$TAG"
    printf 'ACTUAL_FILES=%s\n' "$ACTUAL_FILES"
    printf 'ACTUAL_BYTES=%s\n' "$ACTUAL_BYTES"
    printf 'ACTUAL_TIFF_FILES=%s\n' "$ACTUAL_TIFF_FILES"
    printf 'ACTUAL_TIFF_BYTES=%s\n' "$ACTUAL_TIFF_BYTES"
    printf 'ND2_FILES=%s\n' "$ND2_FILES"
    printf 'SYMLINKS=%s\n' "$SYMLINKS"
    rclone version | sed -n '1,4p'
} > "$REPORT_DIR/preflight.txt"

test "$ACTUAL_FILES" -eq "$EXPECTED_FILES"
test "$ACTUAL_BYTES" -eq "$EXPECTED_BYTES"
test "$ACTUAL_TIFF_FILES" -eq "$EXPECTED_TIFF_FILES"
test "$ACTUAL_TIFF_BYTES" -eq "$EXPECTED_TIFF_BYTES"
test "$ND2_FILES" -eq 0
test "$SYMLINKS" -eq 0

echo '========== PUBLISHED UPLOAD PREFLIGHT =========='
cat "$REPORT_DIR/preflight.txt"

COPY_STATUS=0
rclone copy "$SOURCE" "$DEST" \
    --exclude '*.nd2' \
    --exclude '*.ND2' \
    --transfers 16 \
    --checkers 32 \
    --fast-list \
    --stats 60s \
    --log-file "$REPORT_DIR/rclone_copy.log" \
    --log-level INFO || COPY_STATUS=$?

CHECK_STATUS='SKIPPED'
if test "$COPY_STATUS" -eq 0
then
    CHECK_STATUS=0
    rclone check "$SOURCE" "$DEST" \
        --exclude '*.nd2' \
        --exclude '*.ND2' \
        --checkers 32 \
        --log-file "$REPORT_DIR/rclone_check.log" \
        --log-level INFO || CHECK_STATUS=$?
fi

{
    printf 'COPY_STATUS=%s\n' "$COPY_STATUS"
    printf 'CHECK_STATUS=%s\n' "$CHECK_STATUS"
    printf 'FINISHED_UTC=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)"
    if test "$COPY_STATUS" -eq 0 && test "$CHECK_STATUS" = 0
    then
        printf 'FINAL_GATE=PASS\n'
    else
        printf 'FINAL_GATE=RETRY_REQUIRED\n'
    fi
} > "$REPORT_DIR/transfer_summary.txt"

rclone copy "$REPORT_DIR" "$REPORT_REMOTE" --transfers 4 --checkers 8
rclone check "$REPORT_DIR" "$REPORT_REMOTE"

echo '========== PUBLISHED UPLOAD SUMMARY =========='
cat "$REPORT_DIR/transfer_summary.txt"
echo "RESULT_REMOTE=$DEST"
echo "REPORT_REMOTE=$REPORT_REMOTE"

test "$COPY_STATUS" -eq 0
test "$CHECK_STATUS" = 0
echo 'PUBLISHED_EXACT219_DRIVE_UPLOAD_OK'

