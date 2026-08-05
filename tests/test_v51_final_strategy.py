from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "trajectory_extraction" / "pipeline"
sys.path.insert(0, str(PIPELINE))

import coordinate_system
import max_step_model


def load_stage1_module():
    path = PIPELINE / "auto_roi_for_published_v2.13.py"
    spec = importlib.util.spec_from_file_location("auto_roi_v213_final", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CoordinateContractTests(unittest.TestCase):
    def test_automatic_pixel_centres_are_shifted_by_exactly_one(self):
        pixel = 108.333333333333
        x = coordinate_system.automatic_nm_to_image_px([pixel, 2 * pixel], pixel)
        np.testing.assert_allclose(x, [0.0, 1.0], atol=1e-12)
        np.testing.assert_allclose(
            coordinate_system.image_px_to_automatic_nm(x, pixel),
            [pixel, 2 * pixel],
            atol=1e-12,
        )

    def test_thunderstorm_half_pixel_and_fiji_roi_edge_are_explicit(self):
        pixel = 100.0
        x = coordinate_system.thunderstorm_roi_nm_to_image_px(
            [50.0, 150.0], pixel, roi_edge_offset_px=17
        )
        np.testing.assert_allclose(x, [17.0, 18.0], atol=1e-12)

    def test_frames_are_one_based(self):
        np.testing.assert_array_equal(
            coordinate_system.csv_frame_to_array_index([1, 2, 50]),
            [0, 1, 49],
        )
        with self.assertRaises(ValueError):
            coordinate_system.csv_frame_to_array_index(0)


class MaxDispPolicyTests(unittest.TestCase):
    def test_exact_crop_sidecar_is_preferred_and_hashed(self):
        metadata = {
            "frame_count": 4,
            "frame_interval_s": 1.0,
            "pixel_size_x_um_per_px": 0.1,
        }
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "cell_metadata.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "source_nd2": "movie.nd2",
                        "time": {"frame_intervals_s": [0.9, 1.0, 1.1]},
                    }
                ),
                encoding="utf-8",
            )
            intervals, provenance = max_step_model.read_movie_intervals(
                metadata, sidecar
            )
        self.assertEqual(intervals, [0.9, 1.0, 1.1])
        self.assertEqual(provenance["source"], "exact_crop_sidecar")
        self.assertFalse(provenance["fallback_used"])
        self.assertEqual(len(provenance["sha256"]), 64)

    def test_trajectory_target_is_product_of_step_coverages(self):
        metadata = {
            "frame_count": 50,
            "frame_interval_s": 1.0715574026107788,
            "pixel_size_x_um_per_px": 0.10833333604166673,
        }
        result = max_step_model.derive_from_metadata(metadata)
        self.assertAlmostEqual(result["modeled_max_step_px"], 3.30)
        self.assertGreaterEqual(result["achieved_trajectory_coverage"], 0.975)
        self.assertTrue(
            math.isclose(
                result["coverage_policy"]["equivalent_uniform_per_step_coverage"],
                0.975 ** (1 / 49),
                rel_tol=1e-14,
            )
        )
        self.assertIn("no per-cell", result["physical_prior"]["D_star_policy"])


class ReferenceSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage1 = load_stage1_module()

    def test_global_regions_require_full_mask_containment_then_edge_filter(self):
        avg = np.ones((20, 20), dtype=float)
        nucleus = np.zeros((20, 20), dtype=bool)
        nucleus[2:18, 2:18] = True
        avg[8:11, 8:11] = 20.0       # accepted interior component
        avg[13:15, 8:10] = 12.0      # accepted interior, lower rank
        avg[1:4, 5:7] = 18.0         # crosses mask: reject containment
        avg[2:4, 13:15] = 17.0       # fully inside but in edge band

        clusters, audit = self.stage1.detect_signal_clusters(
            avg,
            k=0.0,
            min_px=2,
            n_max=5,
            nucleus_mask=nucleus,
            edge_width_px=2.0,
            maximum_edge_fraction=0.10,
        )
        self.assertEqual(len(clusters), 2)
        self.assertGreater(clusters[0]["intensity"], clusters[1]["intensity"])
        self.assertTrue(all(item["inside_fraction"] == 1.0 for item in clusters))
        decisions = {row["decision"] for row in audit["all_threshold_components"]}
        self.assertIn("REJECT_NOT_FULLY_CONTAINED", decisions)
        self.assertIn("REJECT_EDGE_BAND_FRACTION", decisions)
        self.assertEqual(audit["containment_fraction_required"], 1.0)

    def test_final_purple_thresholds_are_split(self):
        self.assertEqual(self.stage1.REFERENCE_SEED_K["purple"], 1.645)
        self.assertEqual(self.stage1.REFERENCE_TRACKING_K["purple"], 0.5)
        self.assertEqual(self.stage1.REFERENCE_EDGE_WIDTH_PX, 3.0)
        self.assertEqual(self.stage1.REFERENCE_MAX_EDGE_FRACTION, 0.10)


class RunnerDefaultContractTests(unittest.TestCase):
    def test_mask_zero_and_trajectory_coverage_are_the_only_new_defaults(self):
        for relative in (
            "trajectory_extraction/run_full_pipeline_v4.py",
            "trajectory_extraction/run_batch_pipeline_v4.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('"--mask-dilation-px"', source)
            self.assertIn("default=0", source)
            self.assertIn('"--trajectory-coverage-probability"', source)
            self.assertNotIn('"--coverage-probability"', source)
            self.assertNotIn('"--max-step-frame-gap"', source)


if __name__ == "__main__":
    unittest.main()
