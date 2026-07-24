import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "nucleus_segmentation" / "save_crops.py"


if "nd2" not in sys.modules:
    nd2_stub = types.ModuleType("nd2")
    nd2_stub.ND2File = object
    sys.modules["nd2"] = nd2_stub

spec = importlib.util.spec_from_file_location("save_crops_time_test", MODULE_PATH)
save_crops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(save_crops)


@dataclass
class FakeTime:
    relativeTimeMs: float


@dataclass
class FakeChannel:
    time: FakeTime


@dataclass
class FakeFrameMetadata:
    channels: list


class FakeND2:
    loop_indices = (
        {"T": 0, "Z": 0},
        {"T": 0, "Z": 1},
        {"T": 1, "Z": 0},
        {"T": 1, "Z": 1},
        {"T": 2, "Z": 0},
        {"T": 2, "Z": 1},
    )

    _timestamps = (1010.0, 1000.0, 4510.0, 4500.0, 8500.0, 8510.0)

    def frame_metadata(self, index):
        timestamp = self._timestamps[index]
        return FakeFrameMetadata(
            channels=[
                FakeChannel(FakeTime(timestamp + 2.0)),
                FakeChannel(FakeTime(timestamp)),
            ]
        )


class TestND2TimeMetadata(unittest.TestCase):
    def test_multiz_frame_times_use_earliest_timestamp_per_t(self):
        self.assertEqual(
            save_crops._extract_frame_times(FakeND2(), 3),
            [0.0, 3.5, 7.5],
        )

    def test_ne_time_loop_periods_are_milliseconds(self):
        period_diff = types.SimpleNamespace(avg=500.0)
        period = types.SimpleNamespace(
            periodDiff=period_diff,
            periodMs=1.0,
        )
        loop = types.SimpleNamespace(
            type="NETimeLoop",
            parameters=types.SimpleNamespace(periods=[period]),
        )
        interval, source = save_crops._experiment_interval_s([loop])
        self.assertEqual(interval, 0.5)
        self.assertEqual(source, "experiment.periodDiff.avg")

    def test_period_ms_is_always_converted_from_ms(self):
        period = types.SimpleNamespace(
            periodDiff=types.SimpleNamespace(avg=0.0),
            periodMs=500.0,
        )
        loop = types.SimpleNamespace(
            type="TimeLoop",
            parameters=period,
        )
        interval, source = save_crops._experiment_interval_s([loop])
        self.assertEqual(interval, 0.5)
        self.assertEqual(source, "experiment.periodMs")


if __name__ == "__main__":
    unittest.main()
