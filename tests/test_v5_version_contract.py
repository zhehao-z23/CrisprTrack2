from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNERS = (
    ROOT / "trajectory_extraction" / "run_full_pipeline_v4.py",
    ROOT / "trajectory_extraction" / "run_batch_pipeline_v4.py",
    ROOT / "trajectory_extraction" / "pipeline" / "run_anchor_roi_spt.py",
)


class V5VersionContractTests(unittest.TestCase):
    def test_runtime_manifests_use_repository_version(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "5.0.0-dev1-trackmem-global-gap")
        expected = f'VERSION = "v{version}"'
        for runner in RUNNERS:
            with self.subTest(runner=runner.relative_to(ROOT)):
                source = runner.read_text(encoding="utf-8")
                ast.parse(source, filename=str(runner))
                self.assertIn(expected, source)
                self.assertNotIn(
                    'VERSION = "v4.2.2-convex-hull-roi"',
                    source,
                )


if __name__ == "__main__":
    unittest.main()
