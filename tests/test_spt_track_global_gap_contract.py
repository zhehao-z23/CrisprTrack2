from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPT_TRACK = (
    ROOT
    / "trajectory_extraction"
    / "pipeline"
    / "matlab_deps"
    / "spt_track.m"
)


class GlobalGapContractTests(unittest.TestCase):
    def test_global_gap_boundary_uses_track_memory(self) -> None:
        source = SPT_TRACK.read_text(encoding="utf-8")
        self.assertIn("jump = find(t_posnew > param.mem);", source)
        self.assertNotIn("jump = find(t_posnew);", source)

    def test_fix_does_not_introduce_gap_scaled_radius(self) -> None:
        source = SPT_TRACK.read_text(encoding="utf-8")
        boundary = source.index("jump = find(t_posnew > param.mem);")
        call = source.index("track(t_pos,max_disp,param)")
        self.assertLess(boundary, call)
        self.assertNotIn("sqrt(", source[boundary:call])
        self.assertNotIn("max_disp *", source[boundary:call])

    def test_matlab_runtime_regression_is_versioned(self) -> None:
        script = ROOT / "tests" / "test_spt_track_global_gap_memory.m"
        source = script.read_text(encoding="utf-8")
        self.assertIn("SPT_GLOBAL_GAP_MEMORY_REGRESSION_OK", source)
        self.assertIn("sptpara.trackMem = 0;", source)
        self.assertIn("sptpara.trackMem = 1;", source)
        self.assertIn("sptpara.trackMem = 2;", source)
        self.assertIn("sptpara.trackMem = 3;", source)
        self.assertIn("competition =", source)
        self.assertIn("mixed_gaps =", source)

    def test_matlab_batch_integration_is_versioned(self) -> None:
        script = ROOT / "tests" / "test_spt_batch_global_gap_integration.m"
        source = script.read_text(encoding="utf-8")
        self.assertIn("SPT_BATCH_GLOBAL_GAP_INTEGRATION_OK", source)
        self.assertIn("detection_frames = [1, 2, 3, 5, 6, 7];", source)
        self.assertIn("spt_batch(", source)
        self.assertIn("result.im.planeAttr(4).nparticle == 0", source)

    def test_v42_v5_batch_control_is_versioned(self) -> None:
        script = ROOT / "tests" / "test_v42_v5_spt_batch_gap_control.m"
        source = script.read_text(encoding="utf-8")
        self.assertIn("V42_V5_SPT_BATCH_GAP_CONTROL_OK", source)
        self.assertIn("OligoLiveFish-ML-ZZH-v4.2-candidate-qc", source)
        self.assertIn("assert(isempty(v42_result.traj));", source)
        self.assertIn("assert(numel(v5_result.traj) == 1);", source)


if __name__ == "__main__":
    unittest.main()
