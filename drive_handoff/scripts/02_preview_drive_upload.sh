#!/usr/bin/env bash
# Preview only. This script does not copy; remove --dry-run only after mapping review.
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
PUBLISHED_RUN="$PROJECT/work/published_exact219_v422_v5_20260729T205411Z"
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
LOG_DIR="$PROJECT/work/rclone_uploads/published_exact219_preview_$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$LOG_DIR"
test -d "$PUBLISHED_RUN"
rclone lsf "$DRIVE_ROOT" >/dev/null

rclone copy "$PUBLISHED_RUN" \
    "$DRIVE_ROOT/published_validation/$(basename "$PUBLISHED_RUN")" \
    --dry-run \
    --exclude '**/*.nd2' \
    --exclude '**/.git/**' \
    --create-empty-src-dirs \
    --log-file "$LOG_DIR/rclone_dry_run.log" \
    --log-level INFO \
    --stats 30s

printf 'DRY_RUN_LOG=%s\n' "$LOG_DIR/rclone_dry_run.log"
echo 'PUBLISHED_UPLOAD_PREVIEW_OK'
