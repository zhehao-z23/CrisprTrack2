#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)
ARCHIVE=${1:-"$REPO_ROOT/deployment/v5_dev1_overlay_20260729.tar.gz"}
CHECKSUM=${2:-"${ARCHIVE}.sha256"}
MANIFEST="$REPO_ROOT/provenance/V5_DEV1_CHANGED_FILES.csv"
FILE_LIST="$REPO_ROOT/deployment/V5_DEV1_OVERLAY_FILES.txt"

test -f "$ARCHIVE"
test -f "$CHECKSUM"
test -f "$MANIFEST"
test -f "$FILE_LIST"

(
  cd "$(dirname "$ARCHIVE")"
  sha256sum -c "$(basename "$CHECKSUM")"
)

failures=0
rows=0
while IFS=, read -r relative_path expected_bytes expected_sha256; do
  rows=$((rows + 1))
  actual_bytes=$(tar -xOzf "$ARCHIVE" "$relative_path" | wc -c)
  actual_sha256=$(tar -xOzf "$ARCHIVE" "$relative_path" | sha256sum | cut -d' ' -f1)
  if [[ "$actual_bytes" != "$expected_bytes" ||
        "$actual_sha256" != "$expected_sha256" ]]; then
    echo "ARCHIVE_MISMATCH: $relative_path" >&2
    failures=$((failures + 1))
  fi
done < <(tail -n +2 "$MANIFEST" | tr -d '\r')

if ! diff -u \
  <(tr -d '\r' < "$FILE_LIST" | sed '/^[[:space:]]*$/d' | sort) \
  <(tar -tzf "$ARCHIVE" | sort); then
  echo "ARCHIVE_LIST_MISMATCH" >&2
  failures=$((failures + 1))
fi

echo "ARCHIVE_MANIFEST_ROWS=$rows FAILURES=$failures"
echo "ARCHIVE_FILES=$(tar -tzf "$ARCHIVE" | wc -l)"
test "$failures" -eq 0
echo "V5_OVERLAY_ARCHIVE_OK"
