from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "trajectory_extraction" / "pipeline"
sys.path.insert(0, str(PIPELINE))

import align_microsam_mask
import experiment_profiles
import max_step_model
import run_anchor_roi_spt

_AUTO_ROI_PATH = PIPELINE / "auto_roi_for_published_v2.13.py"
_AUTO_ROI_SPEC = importlib.util.spec_from_file_location("auto_roi_v213", _AUTO_ROI_PATH)
auto_roi_v213 = importlib.util.module_from_spec(_AUTO_ROI_SPEC)
assert _AUTO_ROI_SPEC.loader is not None
_AUTO_ROI_SPEC.loader.exec_module(auto_roi_v213)


class MatlabSptTrackRegressionTests(unittest.TestCase):
    def test_legacy_track_returns_empty_before_first_row_access(self):
        source = (
            PIPELINE / "matlab_deps" / "track.m"
        ).read_text(encoding="utf-8")
        guard_comment = "% No retained tracks is a valid result"
        guard_start = source.index(guard_comment)
        first_row_access = source.index("ndat=length(res(1,:));")
        self.assertLess(guard_start, first_row_access)
        guard = source[guard_start:first_row_access]
        self.assertIn("if isempty(res)", guard)
        self.assertIn("tracks = res;", guard)
        self.assertIn("return", guard)

    def test_legacy_single_track_boundary_uses_final_row(self):
        source = (
            PIPELINE / "matlab_deps" / "track.m"
        ).read_text(encoding="utf-8")
        self.assertIn("u = length(newtracks(:,ndat));", source)
        self.assertNotIn("u = length(newtracks(:,ndat)) -1;", source)

    def test_empty_track_guard_covers_both_tracking_branches(self):
        source = (
            PIPELINE / "matlab_deps" / "spt_track.m"
        ).read_text(encoding="utf-8")
        guard_comment = "% track.m can legitimately return no retained trajectories"
        guard_start = source.index(guard_comment)
        struct_start = source.index("n_traj = max(trajlist(:,4));")
        self.assertLess(guard_start, struct_start)
        guard = source[guard_start:struct_start]
        self.assertIn("if isempty(trajlist)", guard)
        self.assertIn("traj = struct([]);", guard)
        self.assertIn("return", guard)

    def test_matlab_runtime_regression_script_is_versioned(self):
        script = ROOT / "tests" / "test_spt_track_no_trajectory.m"
        source = script.read_text(encoding="utf-8")
        self.assertIn("SPT_EMPTY_TRAJECTORY_REGRESSION_OK", source)
        self.assertIn("[10, 10, 1; 100, 100, 2]", source)


class ExperimentProfileTests(unittest.TestCase):
    @staticmethod
    def _sidecar(path: Path, channel_names: list[str]) -> None:
        path.with_name(path.stem + "_metadata.json").write_text(
            json.dumps(
                {
                    "source_nd2": str(path.with_suffix(".nd2")),
                    "stem": path.stem,
                    "crop_shape": {"C": len(channel_names)},
                    "channels": [
                        {"index": index, "name": name}
                        for index, name in enumerate(channel_names)
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_profiles_lock_biological_anchor_and_raw_index(self):
        chr3 = experiment_profiles.get_profile("chr3_sites_2_3_4")
        dsb = experiment_profiles.get_profile("dsb_53bp1_site1_site2")
        self.assertEqual(chr3.anchor_channel, "green")
        self.assertEqual(chr3.anchor.raw_index, 2)
        self.assertEqual(chr3.anchor.site_id, "site2")
        self.assertEqual(dsb.anchor_channel, "purple")
        self.assertEqual(dsb.anchor.raw_index, 2)
        self.assertEqual(dsb.anchor.site_id, "site2")

    def test_profiles_reject_each_others_channel_contract(self):
        chr3 = experiment_profiles.get_profile("chr3_sites_2_3_4")
        dsb = experiment_profiles.get_profile("dsb_53bp1_site1_site2")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chr3_crop = root / (
                "U2OS_chr3_195M-488+195.7M-565+198M-647_cell1.tif"
            )
            dsb_crop = root / "LiveFISH_DSB014_cell1.tif"
            tifffile.imwrite(
                chr3_crop,
                np.zeros((2, 4, 4, 4), dtype=np.uint16),
                imagej=True,
                metadata={"axes": "TCYX"},
            )
            tifffile.imwrite(
                dsb_crop,
                np.zeros((2, 3, 4, 4), dtype=np.uint16),
                imagej=True,
                metadata={"axes": "TCYX"},
            )
            self._sidecar(
                chr3_crop,
                ["SDC 405 BP1 MH", "SDC 640 LP1 MH", "SDC 488 BP1 MH", "SDC 561 BP1 MH"],
            )
            self._sidecar(
                dsb_crop,
                ["CF GFP SINGLE1_YZ", "CF RFP SINGLE1_yz", "CF Cy5 SINGLE_YZ"],
            )
            self.assertEqual(chr3.validate_crop(chr3_crop)["channel_count"], 4)
            self.assertEqual(dsb.validate_crop(dsb_crop)["channel_count"], 3)
            with self.assertRaises(ValueError):
                chr3.validate_crop(dsb_crop)
            with self.assertRaises(ValueError):
                dsb.validate_crop(chr3_crop)

    def test_chr3_profile_rejects_wrong_raw_channel_order(self):
        profile = experiment_profiles.get_profile("chr3_sites_2_3_4")
        with tempfile.TemporaryDirectory() as directory:
            crop = Path(directory) / "U2OS_chr3_195M-488+195.7M-565+198M-647_cell1.tif"
            tifffile.imwrite(
                crop,
                np.zeros((2, 4, 4, 4), dtype=np.uint16),
                imagej=True,
                metadata={"axes": "TCYX"},
            )
            self._sidecar(
                crop,
                ["SDC 405 BP1 MH", "SDC 488 BP1 MH", "SDC 640 LP1 MH", "SDC 561 BP1 MH"],
            )
            with self.assertRaisesRegex(ValueError, "raw C1"):
                profile.validate_crop(crop)


class MaxStepModelTests(unittest.TestCase):
    def test_escaped_unicode_spatial_unit_is_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "escaped_unit.tif"
            tifffile.imwrite(
                path,
                np.zeros((2, 4, 4), dtype=np.uint16),
                imagej=True,
                resolution=(10, 10),
                metadata={
                    "axes": "TYX",
                    "unit": r"\u00b5m",
                    "finterval": 1.0,
                },
            )
            metadata = max_step_model.read_tracking_metadata(path)
            self.assertEqual(metadata["spatial_unit"], "um")
            self.assertEqual(metadata["frame_count"], 2)

    def test_literal_micro_sign_spatial_units_are_normalized(self):
        for unit in ("\u00b5m", "\u03bcm"):
            with self.subTest(unit=unit):
                self.assertEqual(max_step_model.normalize_spatial_unit(unit), "um")

    def test_50_frame_movie_uses_whole_trajectory_coverage(self):
        metadata = {
            "frame_interval_s": 1.0715574026107788,
            "pixel_size_x_um_per_px": 0.10833333604166673,
            "frame_count": 50,
        }
        result = max_step_model.derive_from_metadata(metadata)
        self.assertTrue(
            math.isclose(
                result["calculation"]["theoretical_radius_px"],
                3.2950548844669045,
                rel_tol=1e-12,
            )
        )
        self.assertAlmostEqual(result["modeled_max_step_px"], 3.30)
        self.assertEqual(
            result["operational_source"],
            "locked prior + movie timing + trajectory coverage + upward rounding",
        )
        self.assertAlmostEqual(
            result["coverage_policy"]["one_sided_at_least_one_exceedance_probability"],
            0.025,
        )
        self.assertFalse(result["tracker_implementation"]["gap_scaled_radius_implemented"])

    def test_explicit_override_is_audited(self):
        metadata = {
            "frame_interval_s": 1.0,
            "pixel_size_x_um_per_px": 0.1,
            "frame_count": 50,
        }
        result = max_step_model.derive_from_metadata(metadata, explicit_max_step_px=3.0)
        self.assertEqual(result["operational_max_step_px"], 3.0)
        self.assertEqual(result["operational_source"], "explicit CLI override")


class StaticRoiTests(unittest.TestCase):
    def test_complete_anchor_path_becomes_one_static_mask(self):
        support = np.ones((40, 40), dtype=bool)
        anchor = [(1, 10.0, 10.0), (2, 12.0, 12.0), (3, 15.0, 12.0)]
        roi = run_anchor_roi_spt.static_anchor_union(anchor, support, 5)
        self.assertTrue(roi[10, 10])
        self.assertTrue(roi[12, 15])
        self.assertEqual(run_anchor_roi_spt.ndimage.label(roi)[1], 1)

    def test_dilation_smaller_than_gaussian_support_is_rejected(self):
        with self.assertRaises(ValueError):
            run_anchor_roi_spt.static_anchor_union(
                [(1, 5.0, 5.0)], np.ones((10, 10), dtype=bool), 4
            )

    def test_convex_hull_fills_anchor_path_concavity(self):
        support = np.ones((50, 50), dtype=bool)
        anchor = [
            (1, 10.0, 10.0),
            (2, 10.0, 30.0),
            (3, 30.0, 30.0),
        ]
        tube = run_anchor_roi_spt.static_anchor_roi(
            anchor, support, 5, "tube"
        )
        hull = run_anchor_roi_spt.static_anchor_roi(
            anchor, support, 5, "convex_hull"
        )
        self.assertTrue(np.all(hull[tube]))
        self.assertFalse(tube[24, 20])
        self.assertTrue(hull[24, 20])
        self.assertGreater(int(hull.sum()), int(tube.sum()))

    def test_both_geometries_are_clipped_to_microsam_support(self):
        support = np.zeros((40, 40), dtype=bool)
        support[5:30, 5:30] = True
        anchor = [(1, 8.0, 8.0), (2, 28.0, 8.0), (3, 28.0, 28.0)]
        for geometry in ("tube", "convex_hull"):
            roi = run_anchor_roi_spt.static_anchor_roi(
                anchor, support, 5, geometry
            )
            self.assertFalse(np.any(roi & ~support))

    def test_validated_hulls_do_not_bridge_gap_or_excessive_step(self):
        support = np.ones((70, 70), dtype=bool)
        anchor = [
            (1, 10.0, 10.0),
            (2, 12.0, 10.0),
            (4, 35.0, 35.0),  # frame gap: must start a new segment
            (5, 55.0, 55.0),  # adjacent but excessive step: another segment
        ]
        roi = run_anchor_roi_spt.static_anchor_roi(
            anchor,
            support,
            5,
            "validated_segment_convex_hull",
            maximum_reference_step_px=3.0,
        )
        self.assertTrue(roi[10, 10])
        self.assertTrue(roi[35, 35])
        self.assertTrue(roi[55, 55])
        self.assertFalse(roi[24, 24])
        self.assertFalse(roi[45, 45])
        self.assertEqual(run_anchor_roi_spt.ndimage.label(roi)[1], 3)


class PGatedRedReferenceTests(unittest.TestCase):
    def test_red_continuity_never_falls_back_to_p_position(self):
        rng = np.random.default_rng(7)
        stack = rng.normal(100.0, 1.0, size=(3, 48, 48)).astype(np.float32)
        stack[0, 9:12, 9:13] += 100.0
        stack[1, 9:12, 10:14] += 100.0
        stack[2, 29:32, 29:33] += 100.0
        p_reference = {
            1: [(0, 10.0, 10.0), (1, 10.0, 11.0), (2, 30.0, 30.0)]
        }
        tracks, _audit = auto_roi_v213.build_p_gated_red_candidates(
            stack,
            p_reference,
            [np.ones((48, 48), dtype=bool) for _ in range(3)],
            k=0.5,
            harvest_radius_px=5.0,
            inter_frame_max_px=3.0,
            minimum_points=1,
            maximum_missing_frames=3,
        )
        self.assertEqual(sorted(len(track) for track in tracks), [1, 2])
        self.assertFalse(any(len(track) == 3 for track in tracks))

    def test_red_short_gap_uses_red_endpoints_without_interpolation(self):
        rng = np.random.default_rng(11)
        stack = rng.normal(100.0, 1.0, size=(3, 48, 48)).astype(np.float32)
        stack[0, 9:12, 9:13] += 100.0
        stack[2, 10:13, 11:15] += 100.0
        p_reference = {
            1: [(0, 10.0, 10.0), (1, 10.0, 11.0), (2, 11.0, 12.0)]
        }
        tracks, _audit = auto_roi_v213.build_p_gated_red_candidates(
            stack,
            p_reference,
            [np.ones((48, 48), dtype=bool) for _ in range(3)],
            k=0.5,
            harvest_radius_px=5.0,
            inter_frame_max_px=3.0,
            minimum_points=1,
            maximum_missing_frames=1,
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual([point[0] for point in tracks[0]], [0, 2])

    def test_pairing_uses_common_frame_median_and_rejects_ambiguity(self):
        p = {
            1: [(frame, 10.0, 10.0) for frame in range(5)],
            2: [(frame, 30.0, 30.0) for frame in range(5)],
        }
        red = [
            [(frame, 10.0, 11.0) for frame in range(5)],
            [(frame, 30.0, 31.0) for frame in range(5)],
        ]
        assignments, rows, _frames = auto_roi_v213.pair_red_candidates_to_purple(
            red,
            p,
            maximum_median_distance_px=25.0,
            minimum_shared_frames=5,
            movie_frame_count=5,
            minimum_movie_coverage_fraction=0.25,
            uniqueness_margin_px=1.0,
        )
        self.assertEqual(sorted(assignments), [1, 2])
        self.assertTrue(all(row["decision"] == "ACCEPT_UNIQUE" for row in rows))
        self.assertTrue(all(row["median_distance_px"] == 1.0 for row in rows))

    def test_pairing_rejects_shorter_than_movie_coverage_floor(self):
        p = {1: [(frame, 10.0, 10.0) for frame in range(20)]}
        red = [
            [(frame, 10.0, 10.5) for frame in range(4)],
            [(frame, 10.0, 12.0) for frame in range(10)],
        ]
        assignments, rows, _frames = auto_roi_v213.pair_red_candidates_to_purple(
            red,
            p,
            maximum_median_distance_px=25.0,
            minimum_shared_frames=5,
            movie_frame_count=20,
            minimum_movie_coverage_fraction=0.25,
            uniqueness_margin_px=1.0,
        )
        self.assertEqual(len(assignments[1]), 10)
        self.assertEqual(rows[0]["minimum_required_common_frames"], 5)


class MaskAssociationTests(unittest.TestCase):
    def test_sidecar_resolves_exact_relative_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crop = root / "fov_1.tif"
            mask = root / "fov_mask_1.tif"
            crop.touch()
            mask.touch()
            crop.with_name("fov_1_metadata.json").write_text(
                json.dumps({"microsam_mask": {"relative_path": mask.name}}),
                encoding="utf-8",
            )
            self.assertEqual(align_microsam_mask.discover_microsam_mask(crop), mask.resolve())


class BaselineSelectionTests(unittest.TestCase):
    @staticmethod
    def _candidate(path: Path, allele: int, locus: int, channel: str, number: int, points: int, span: int, first: int) -> dict:
        profile = experiment_profiles.get_profile("dsb_53bp1_site1_site2")
        spec = profile.channel_from_prefix(channel)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["frame", "x_nm", "y_nm"])
            writer.writerow([first, 1.0, 2.0])
        return {
            "allele_index": allele,
            "anchor_locus": locus,
            "channel": channel,
            "experiment_profile": profile.name,
            "corrected_channel": spec.corrected_channel,
            "raw_channel_index": spec.raw_index,
            "marker": spec.marker,
            "marker_slug": spec.marker_slug,
            "site_id": spec.site_id,
            "genomic_locus": spec.genomic_locus,
            "fluorophore": spec.fluorophore,
            "candidate_number": number,
            "candidate_csv": str(path),
            "points": points,
            "first_frame": first,
            "last_frame": first + span - 1,
            "frame_span": span,
            "temporal_coverage_fraction": points / span,
            "maximum_missing_frames_between_points": 0,
            "median_step_px": 0.0,
            "p95_step_px": 0.0,
            "inside_static_roi_fraction": 1.0,
        }

    def test_longest_rule_and_no_candidate_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                self._candidate(root / "p1.csv", 1, 2, "P", 1, 10, 12, 2),
                self._candidate(root / "p2.csv", 1, 2, "P", 2, 10, 13, 3),
                self._candidate(root / "p3.csv", 1, 2, "P", 3, 9, 20, 1),
            ]
            selected, audit = run_anchor_roi_spt.select_longest_baselines(
                rows,
                root / "baseline",
                [(1, 2), (2, 5)],
                experiment_profiles.get_profile("dsb_53bp1_site1_site2"),
            )
            self.assertEqual(len(selected), 1)
            self.assertTrue(selected[0]["candidate_csv"].endswith("p2.csv"))
            self.assertTrue(selected[0]["baseline_csv"].endswith("_cleaned.csv"))
            self.assertEqual(len(audit), 6)
            allele2 = [row for row in audit if row["allele_index"] == 2]
            self.assertEqual(len(allele2), 3)
            self.assertTrue(all(row["candidate_count"] == 0 for row in allele2))


if __name__ == "__main__":
    unittest.main()
