import unittest

import numpy as np

from trajectory_extraction.pipeline.bp1_locus_metrics import (
    BP1MetricParameters,
    associate_component,
    clipped_distance_score,
    measure_continuous_intensity,
)


class ContinuousIntensityTests(unittest.TestCase):
    def parameters(self) -> BP1MetricParameters:
        return BP1MetricParameters(
            intensity_radius_nm=200.0,
            background_inner_radius_nm=300.0,
            background_outer_radius_nm=500.0,
            association_boundary_cutoff_nm=1000.0,
            ambiguity_margin_nm=250.0,
            candidate_harvest_radius_nm=3000.0,
            core_minimum_valid_fraction=0.8,
            background_minimum_valid_fraction=0.5,
        )

    def test_positive_enrichment_is_continuous_without_a_call_threshold(self):
        image = np.full((31, 31), 10.0)
        yy, xx = np.ogrid[:31, :31]
        image[(xx - 15) ** 2 + (yy - 15) ** 2 <= 2**2] = 20.0
        result = measure_continuous_intensity(
            image,
            np.ones_like(image, dtype=bool),
            np.zeros_like(image, dtype=bool),
            15.0,
            15.0,
            100.0,
            self.parameters(),
        )
        self.assertTrue(result["intensity_metric_valid"])
        self.assertAlmostEqual(result["site2_bp1_continuous_intensity_score"], 1.0)
        self.assertAlmostEqual(result["site2_bp1_nonnegative_excess_mean_au"], 10.0)

    def test_negative_excess_is_preserved_in_audit_but_score_floors_at_zero(self):
        image = np.full((31, 31), 10.0)
        yy, xx = np.ogrid[:31, :31]
        image[(xx - 15) ** 2 + (yy - 15) ** 2 <= 2**2] = 5.0
        result = measure_continuous_intensity(
            image,
            np.ones_like(image, dtype=bool),
            np.zeros_like(image, dtype=bool),
            15.0,
            15.0,
            100.0,
            self.parameters(),
        )
        self.assertAlmostEqual(result["site2_bp1_local_excess_ratio"], -0.5)
        self.assertEqual(result["site2_bp1_continuous_intensity_score"], 0.0)
        self.assertEqual(result["site2_bp1_nonnegative_excess_sum_au"], 0.0)


class DistanceScoreTests(unittest.TestCase):
    def test_linear_score_is_zero_at_and_beyond_cutoff(self):
        self.assertEqual(clipped_distance_score(0.0, 1000.0, uniquely_assigned=True), 1.0)
        self.assertEqual(clipped_distance_score(500.0, 1000.0, uniquely_assigned=True), 0.5)
        self.assertEqual(clipped_distance_score(1000.0, 1000.0, uniquely_assigned=True), 0.0)
        self.assertEqual(clipped_distance_score(1200.0, 1000.0, uniquely_assigned=True), 0.0)
        self.assertEqual(clipped_distance_score(100.0, 1000.0, uniquely_assigned=False), 0.0)

    def test_missing_and_distant_components_fail_closed(self):
        params = BP1MetricParameters()
        labels = np.zeros((80, 80), dtype=np.uint16)
        labels[35:45, 35:45] = 1
        missing = associate_component(labels, [], 10.0, 10.0, 100.0, params)
        self.assertEqual(missing["assignment_status"], "NO_BP1_COMPONENT_IN_HARVEST_DOMAIN")
        self.assertEqual(missing["site2_bp1_distance_score"], 0.0)

        distant = associate_component(labels, [1], 20.0, 40.0, 100.0, params)
        self.assertEqual(distant["assignment_status"], "NO_ASSOCIATED_FOCUS")
        self.assertEqual(distant["site2_bp1_distance_score"], 0.0)

    def test_inside_component_has_maximum_score(self):
        params = BP1MetricParameters()
        labels = np.zeros((80, 80), dtype=np.uint16)
        labels[35:45, 35:45] = 1
        result = associate_component(labels, [1], 40.0, 40.0, 100.0, params)
        self.assertEqual(result["assignment_status"], "VALID")
        self.assertTrue(result["site2_inside_bp1"])
        self.assertEqual(result["site2_bp1_distance_score"], 1.0)
        self.assertLess(result["site2_to_bp1_signed_boundary_distance_nm"], 0.0)


if __name__ == "__main__":
    unittest.main()
