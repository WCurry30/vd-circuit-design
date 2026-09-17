import tempfile
import unittest
from pathlib import Path

from shared_spice_evaluator import evaluate_conditions


class ConditionTests(unittest.TestCase):
    def run_checks(self, deck, checks):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "submitted.cir"
            source.write_text(deck)
            return evaluate_conditions(source, checks, Path(directory) / "evaluation")

    def test_supply_and_load_conditions_all_run(self):
        deck = "* divider\nVDD IN 0 10\nR1 IN OUT 1k\nRLOAD OUT 0 1k\n.end\n"
        checks = [{"nodes": {"input": "IN", "output": "OUT"},
                   "target": {"metric": "dc_voltage_v", "value": target, "tolerance": .001},
                   "condition": {"dc_sources": {"VDD": supply}, "resistances": {"RLOAD": load}}}
                  for supply, load, target in [(10, 1000, 5), (12, 2000, 8)]]
        result = self.run_checks(deck, checks)
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["checks"]), 2)
        self.assertAlmostEqual(result["checks"][1]["result"]["measured"], 8)
        checks[1]["target"]["value"] = 5
        result = self.run_checks(deck, checks)
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks"][0]["result"]["passed"])

    def test_missing_load_is_rejected(self):
        result = self.run_checks("* no load\nVDD IN 0 10\nR1 IN OUT 1k\n.end\n", [{
            "nodes": {"input": "IN", "output": "OUT"},
            "target": {"metric": "dc_voltage_v", "value": 10, "tolerance": .1},
            "condition": {"resistances": {"RLOAD": 1000}}}])
        self.assertFalse(result["passed"])
        self.assertIn("required testbench element absent", result["checks"][0]["result"]["detail"])

    def test_differential_and_common_mode(self):
        deck = ("* four resistor difference amplifier\n"
                "VIP INP 0 DC 0 AC .5\nVIN INN 0 DC 0 AC .5 180\n"
                "VCC VCC 0 12\nVEE VEE 0 -12\n"
                "R1 INN NM 10k\nR2 OUT NM 50k\nR3 INP NP 10k\nR4 NP 0 50k\n"
                "X1 NP NM VCC VEE OUT OPAMP\nRLOAD OUT 0 20k\n.end\n")
        nodes = {"input": "INP", "input_negative": "INN", "output": "OUT"}
        checks = [
            {"nodes": nodes, "target": {"metric": "gain_real_v_per_v", "value": 5, "tolerance": .01},
             "condition": {"frequency_hz": 1000, "ac_sources": {"VIP": [.5, 0], "VIN": [.5, 180]}}},
            {"nodes": nodes, "target": {"metric": "output_ac_magnitude_v", "value": 0,
                                         "tolerance": .01, "minimum": 0, "maximum": .01},
             "condition": {"ac_sources": {"VIP": [1, 0], "VIN": [1, 0]}}},
        ]
        result = self.run_checks(deck, checks)
        self.assertTrue(result["passed"], result)
        negative = self.run_checks(deck.replace("R4 NP 0 50k", "R4 NP 0 100k"), checks)
        self.assertFalse(negative["passed"])
        self.assertFalse(negative["checks"][1]["result"]["passed"])


if __name__ == "__main__":
    unittest.main()
