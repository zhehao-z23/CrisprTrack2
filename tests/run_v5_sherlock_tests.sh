#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)

PROJECT=${PROJECT:-"$SCRATCH/oligolivefish_nd2_to_trajectory"}
PYTHON=${PYTHON:-"$PROJECT/env/py312_torch251_cu124_ml217/bin/python"}

test -x "$PYTHON" || {
  echo "ERROR: Python executable not found: $PYTHON" >&2
  exit 1
}
command -v matlab >/dev/null 2>&1 || {
  echo "ERROR: matlab is not on PATH; load matlab/R2022b first" >&2
  exit 1
}

cd "$REPO_ROOT"

"$PYTHON" -m unittest \
  discover -s tests -p 'test_*contract.py' -v

matlab -batch \
  "addpath('tests'); test_spt_track_no_trajectory; test_spt_track_global_gap_memory; test_spt_batch_global_gap_integration"

echo "V5_SHERLOCK_TESTS_OK"
