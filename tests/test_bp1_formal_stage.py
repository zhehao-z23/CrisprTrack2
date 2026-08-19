import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import tifffile

from trajectory_extraction.pipeline.bp1_locus_metrics import (
    BP1SegmentationParameters,
    segment_focus_stack,
)
from trajectory_extraction import run_batch_pipeline_v4


REPO = Path(__file__).resolve().parents[1]
EXPORTER = REPO / "trajectory_extraction" / "pipeline" / "export_bp1_locus_metrics.py"
FULL_RUNNER = REPO / "trajectory_extraction" / "run_full_pipeline_v4.py"


class BP1SegmentationTests(unittest.TestCase):
    def test_adjacent_component_keeps_lineage_without_gap_closing(self):
        stack = np.full((3, 32, 32), 10, dtype=np.uint16)
        stack[0, 14:18, 14:18] = 40
        stack[1, 14:18, 15:19] = 40
        stack[2, 14:18, 16:20] = 40
        labels, frames, objects = segment_focus_stack(
            stack,
            np.ones_like(stack, dtype=bool),
            100.0,
            BP1SegmentationParameters(minimum_component_area_px=3),
        )
        self.assertEqual(labels.shape, stack.shape)
        self.assertEqual(len(frames), 3)
        tracks = {int(row["focus_track_id"]) for row in objects}
        self.assertEqual(len(tracks), 1)
        self.assertEqual({int(row["focus_track_length_frames"]) for row in objects}, {3})


class BP1FormalExporterTests(unittest.TestCase):
    def _write_channel(self, path: Path, data: np.ndarray) -> None:
        tifffile.imwrite(
            path,
            data,
            imagej=True,
            resolution=(10, 10),
            metadata={"axes": "TYX", "unit": "um", "finterval": 1.0},
        )

    def test_p_only_crop_writes_dense_metrics_without_modifying_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis = root / "cell"
            analysis.mkdir()
            green = np.full((3, 64, 64), 10, dtype=np.uint16)
            green[:, 29:34, 29:34] = 40
            for channel, data in (
                ("green", green),
                ("red", np.full_like(green, 10)),
                ("purple", np.full_like(green, 10)),
            ):
                self._write_channel(analysis / f"sample_{channel}.tif", data)
            mask = root / "mask.tif"
            tifffile.imwrite(mask, np.ones((64, 64), dtype=np.uint8))
            p_track = root / "allele_001_site2.csv"
            p_track.write_text(
                "frame,x_nm,y_nm\n1,3100,3100\n3,3100,3100\n",
                encoding="utf-8",
            )
            baseline = root / "baseline_manifest.csv"
            with baseline.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["allele_index", "channel", "baseline_csv"]
                )
                writer.writeheader()
                writer.writerow(
                    {"allele_index": 1, "channel": "P", "baseline_csv": p_track}
                )
            output = root / "bp1"
            subprocess.run(
                [
                    sys.executable,
                    str(EXPORTER),
                    str(analysis),
                    "--aligned-nucleus-mask", str(mask),
                    "--baseline-manifest", str(baseline),
                    "--output-dir", str(output),
                ],
                cwd=REPO,
                check=True,
                capture_output=True,
                text=True,
            )
            metrics = pd.read_csv(output / "bp1_allele_frame_metrics.csv")
            self.assertEqual(len(metrics), 3)
            self.assertEqual(int(metrics.site2_valid.sum()), 2)
            self.assertEqual(int(metrics.site1_valid.sum()), 0)
            self.assertEqual(metrics.loc[1, "assignment_status"], "DNA_ANCHOR_MISSING")
            self.assertTrue((metrics.loc[[0, 2], "site2_bp1_distance_score"] == 1.0).all())
            self.assertEqual(p_track.read_text(encoding="utf-8"), "frame,x_nm,y_nm\n1,3100,3100\n3,3100,3100\n")
            manifest = json.loads((output / "bp1_analysis_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["measurement_only"])
            self.assertEqual(manifest["counts"]["site2_alleles"], 1)
            self.assertTrue((output / "bp1_focus_labels.tif").is_file())

    def test_formal_runner_calls_bp1_only_for_dsb_after_spt(self):
        source = FULL_RUNNER.read_text(encoding="utf-8")
        self.assertIn('VERSION = "v5.2.1"', source)
        self.assertIn('if is_dsb:', source)
        self.assertIn('str(BP1_METRICS)', source)
        self.assertLess(source.index("run(spt_command)"), source.index("run(bp1_command)"))
        self.assertLess(source.index("run(bp1_command)"), source.index("str(PYTHON_QC)"))

    def test_batch_summary_reads_bp1_sidecar_status(self):
        with tempfile.TemporaryDirectory() as directory:
            analysis = Path(directory)
            args = SimpleNamespace(
                experiment_profile="dsb_53bp1_site1_site2",
                target_reference_mode="p_gated_r_autonomous",
                roi_geometry="validated_segment_convex_hull",
            )
            result = analysis / (
                "anchor_roi_v4_dsb_53bp1_site1_site2_"
                "p_gated_r_autonomous_validated_segment_convex_hull"
            )
            metrics = result / "53bp1_metrics"
            metrics.mkdir(parents=True)
            manifest = metrics / "bp1_analysis_manifest.json"
            manifest.write_text('{"status":"COMPLETE"}\n', encoding="utf-8")
            status, path = run_batch_pipeline_v4.bp1_output_info(analysis, args)
            self.assertEqual(status, "complete")
            self.assertEqual(Path(path), manifest)

    def test_batch_result_suffix_separates_independent_red_outputs(self):
        args = SimpleNamespace(
            target_reference_mode="independent_r_autonomous",
            roi_geometry="validated_segment_convex_hull",
        )
        self.assertEqual(
            run_batch_pipeline_v4.result_suffix(args),
            "_independent_r_autonomous_validated_segment_convex_hull",
        )


if __name__ == "__main__":
    unittest.main()
