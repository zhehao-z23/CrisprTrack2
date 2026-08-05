from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SherlockTestRunnerContractTests(unittest.TestCase):
    def test_runner_is_non_destructive_and_excludes_local_only_control(self) -> None:
        runner = ROOT / "tests" / "run_v5_sherlock_tests.sh"
        source = runner.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", source)
        self.assertIn("V5_SHERLOCK_TESTS_OK", source)
        self.assertIn("test_spt_track_global_gap_memory", source)
        self.assertIn("test_spt_batch_global_gap_integration", source)
        self.assertNotIn("test_v42_v5_spt_batch_gap_control", source)
        self.assertNotIn("rm -rf", source)
        self.assertNotIn("git reset", source)


if __name__ == "__main__":
    unittest.main()
