from pathlib import Path
import argparse
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("batch_resume", ROOT / "trajectory_extraction/run_batch_pipeline_v4.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class ResumeParametersTests(unittest.TestCase):
    def test_changed_red_support_or_gap_cannot_reuse_old_completion(self):
        config = json.loads((ROOT / "configs/dsb_v521.json").read_text())["tracking"]
        args = argparse.Namespace(**config)
        args.target_reference_mode = "independent_r_autonomous"
        args.roi_geometry = "validated_segment_convex_hull"
        with tempfile.TemporaryDirectory() as temp:
            analysis = Path(temp)
            result = analysis / f"anchor_roi_v4_{args.experiment_profile}{batch.result_suffix(args)}"
            result.mkdir()
            manifest = {"version": "v5.2.1", "status": "complete", "options": batch.scientific_options(args)}
            (result / "run_manifest.json").write_text(json.dumps(manifest))
            self.assertTrue(batch.completion_matches(analysis, args))
            for key, changed in [("red_min_movie_coverage_fraction", 0.5), ("red_max_missing_frames", 3)]:
                original = getattr(args, key)
                setattr(args, key, changed)
                self.assertFalse(batch.completion_matches(analysis, args), key)
                setattr(args, key, original)


if __name__ == "__main__":
    unittest.main()
