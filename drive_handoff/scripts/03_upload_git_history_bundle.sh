#!/usr/bin/env bash
set -euo pipefail

PROJECT="${SCRATCH:-/scratch/users/zhangzh}/oligolivefish_nd2_to_trajectory"
REPO="$PROJECT/code/OligoLiveFish-ML-ZZH-v4.2.2-833515e"
DRIVE_DIR='zhangzh:2-25-26-dsb_E/more/zhehao/code_snapshots/git_history'
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PROJECT/work/git_bundles/$TAG"
LOG_DIR="$PROJECT/work/rclone_uploads/git_bundle_$TAG"
BUNDLE="$OUT/OligoLiveFish-ML-ZZH_all_refs_$TAG.bundle"

module purge >/dev/null 2>&1 || true
module load system >/dev/null 2>&1 || true
module load git/2.45.1
hash -r

test -d "$REPO"
mkdir -p "$OUT"
mkdir -p "$LOG_DIR"
cd "$REPO"

EXPECTED='833515ee7a3da2ced4b34925c85107d54c006918'
ACTUAL="$(git rev-parse HEAD)"
test "$ACTUAL" = "$EXPECTED"

git bundle create "$BUNDLE" --all
git bundle verify "$BUNDLE" | tee "$OUT/bundle_verify.txt"
sha256sum "$BUNDLE" | tee "$BUNDLE.sha256"

{
    printf 'CREATED_UTC=%s\n' "$TAG"
    printf 'SOURCE_REPO=%s\n' "$REPO"
    printf 'SOURCE_HEAD=%s\n' "$ACTUAL"
    printf 'BUNDLE=%s\n' "$BUNDLE"
    printf 'NOTE=v5 uncommitted overlay is not represented by Git refs; use v5 snapshot plus overlay manifest.\n'
} > "$OUT/BUNDLE_METADATA.txt"

if rclone lsf "$DRIVE_DIR/$TAG" >/dev/null 2>&1
then
    echo "ERROR: remote target already exists: $DRIVE_DIR/$TAG" >&2
    exit 1
fi

rclone copy "$OUT" "$DRIVE_DIR/$TAG" \
    --transfers 4 \
    --checkers 8 \
    --log-file "$LOG_DIR/rclone_copy.log" \
    --log-level INFO \
    --stats 30s

rclone check "$OUT" "$DRIVE_DIR/$TAG" \
    --log-file "$LOG_DIR/rclone_check.log" \
    --log-level INFO

rclone copy "$LOG_DIR" "$DRIVE_DIR/$TAG/_transfer_logs" \
    --transfers 2 \
    --checkers 4

echo "REMOTE=$DRIVE_DIR/$TAG"
echo "LOCAL=$OUT"
echo "LOG_DIR=$LOG_DIR"
echo 'GIT_HISTORY_BUNDLE_UPLOAD_OK'
