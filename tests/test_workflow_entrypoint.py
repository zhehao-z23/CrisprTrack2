from pathlib import Path
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("workflow", Path(__file__).resolve().parents[1] / "crisprtrack2.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class WorkflowTests(unittest.TestCase):
    def test_paths_with_spaces_are_separate_arguments(self):
        result = workflow.commands({"tracking": {"fiji_bin": "C:/Program Files/Fiji/ImageJ.exe"}}, Path("raw files"), Path("run files"), "all")
        self.assertEqual(len(result), 3)
        self.assertIn("C:/Program Files/Fiji/ImageJ.exe", result[-1])
        self.assertIn("**/*.tif", result[-1])

    def test_output_paths_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            workflow.commands({"segmentation": {"output_root": "raw"}}, Path("raw"), Path("run"), "all")

    def test_flags_and_null_preserve_source_semantics(self):
        self.assertEqual(workflow.options({"resume": False, "max_step_px": None, "matlab_save_filter_images": False}), ["--no-resume"])

    def test_unrecognized_config_section_fails(self):
        with self.assertRaises(ValueError):
            workflow.commands({"trackng": {}}, Path("raw"), Path("run"), "track")


if __name__ == "__main__":
    unittest.main()
