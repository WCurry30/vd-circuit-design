import tempfile
import unittest
from pathlib import Path

from shared_spice_evaluator import NodeManifest, evaluate_deck, _simulation_diagnostics


class FeedbackTests(unittest.TestCase):
    def evaluate(self, root, deck, target=5.0):
        source = root / "submitted.cir"
        source.write_text(deck)
        return evaluate_deck(source, NodeManifest("IN", "OUT"),
                             {"metric": "dc_voltage_v", "value": target,
                              "tolerance": 0.1}, root / "evaluation")

    def test_valid_and_out_of_tolerance(self):
        for target, passed in [(5.0, True), (10.0, False)]:
            with tempfile.TemporaryDirectory() as directory:
                result = self.evaluate(Path(directory),
                                       "* divider\nV1 IN 0 10\nR1 IN OUT 1k\nR2 OUT 0 1k\n.end\n",
                                       target)
                self.assertEqual(result.status, "success")
                self.assertEqual(result.passed, passed)
                self.assertAlmostEqual(result.measured, 5.0)
                if not passed:
                    self.assertIn("measured=5", result.detail)
                    self.assertIn("target=10", result.detail)

    def test_missing_model_has_actionable_context(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.evaluate(Path(directory),
                                   "* missing model\nV1 IN 0 10\nR1 IN OUT 1k\nD1 OUT 0 MISSING_DIODE\n.end\n")
            self.assertFalse(result.passed)
            self.assertIn("missing_diode", result.detail.lower())
            self.assertEqual(result.failure_stage, "simulation")

    def test_diagnostic_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            detail = _simulation_diagnostics(Path(directory) / "absent", "error " * 10000, "")
            self.assertLessEqual(len(detail), 2400)


if __name__ == "__main__":
    unittest.main()
