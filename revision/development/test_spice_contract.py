import tempfile
import unittest
from pathlib import Path

from spice_contract import component_bindings, clean_preserving_definitions
from shared_spice_evaluator import NodeManifest, evaluate_deck
from runtime_experts.bjt_amplifier_expert import BjtAmplifierExpert
from runtime_experts.led_constant_current_expert import LedConstantCurrentExpert


class ContractTests(unittest.TestCase):
    def test_physical_identifiers_and_device_types(self):
        components = [
            {"uid": "PART3", "search_query": "Resistor"},
            {"uid": "U1", "search_query": "LM358"},
            {"uid": "Q1", "search_query": "2N7000"},
            {"uid": "LED1", "search_query": "LED"},
            {"uid": "J1", "search_query": "Connector"},
        ]
        bindings = component_bindings(components, {"PART3": {"lib_id": "Device:R"}})
        self.assertEqual([b["spice_reference"] for b in bindings],
                         ["R_PART3", "X_U1", "M_Q1", "D_LED1", None])
        self.assertEqual(bindings[0]["physical_uid"], "PART3")
        self.assertEqual(components[0]["uid"], "PART3")

    def test_case_insensitive_collision(self):
        bindings = component_bindings([
            {"uid": "r1", "search_query": "Resistor"},
            {"uid": "R1", "search_query": "Resistor"}], {})
        self.assertEqual([b["spice_reference"] for b in bindings], ["r1", "R1_2"])

    def test_led_requirement_overrides_retrieved_bjt(self):
        expert = LedConstantCurrentExpert()
        prompts = expert.get_netlist_prompts(
            "Use an op-amp and N-channel MOSFET to drive an LED at 20mA.",
            "X1(LM358)、Q1(2N3904)", 2, "previous deck", "missing model")
        self.assertIn("requested MOSFET topology", prompts[0])
        self.assertIn("missing model", prompts[1])
        self.assertNotIn("2N3904", prompts[0])

    def test_real_cleaner_keeps_model_and_subcircuit(self):
        code = ("* diode circuit\nV1 IN 0 5\nR1 IN OUT 1k\nX1 OUT 0 DIODE_CELL\n"
                ".model TEST_D D(IS=1e-14\n+ N=1)\n"
                ".subckt DIODE_CELL A K\nD1 A K TEST_D\n.ends DIODE_CELL\n.end\n")
        cleaned = clean_preserving_definitions(code, BjtAmplifierExpert().clean_spice_code)
        self.assertIn(".model TEST_D D(IS=1e-14\n+ N=1)", cleaned)
        self.assertIn(".subckt DIODE_CELL A K\nD1 A K TEST_D\n.ends DIODE_CELL", cleaned)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "submitted.cir"
            source.write_text(cleaned)
            result = evaluate_deck(source, NodeManifest("IN", "OUT"),
                                   {"metric": "dc_voltage_v", "value": 0.7,
                                    "tolerance": 0.3}, root / "evaluation")
            self.assertEqual(result.status, "success", result.detail)
            self.assertTrue(result.passed, result.detail)

    def test_unclosed_subcircuit_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "unterminated"):
            clean_preserving_definitions(".subckt TEST A B\nR1 A B 1k\n", lambda s: s)


if __name__ == "__main__":
    unittest.main()
