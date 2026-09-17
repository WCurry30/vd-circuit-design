import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import spice_contract
from runtime_experts.bjt_amplifier_expert import BjtAmplifierExpert


class EngineTests(unittest.TestCase):
    def test_same_request_for_cleanup_ablation_and_scoped_names(self):
        deck = ("* scope fixture\nV1 IN 0 5\nR1 IN OUT 1k\nX1 OUT 0 CELL\n"
                ".subckt CELL A B\nR1 A B 1k\n.ends CELL\n.end\n")
        requests = []

        def create(**request):
            requests.append(request)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=deck))],
                usage={}, model="offline-fixture")

        fake = types.ModuleType("openai")
        fake.OpenAI = lambda **kwargs: types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        core = types.ModuleType("core")
        with patch.dict(sys.modules, {"openai": fake, "core": core,
                                     "core.spice_contract": spice_contract}):
            spec = importlib.util.spec_from_file_location("fixture_engine", Path(__file__).with_name("netlist_engine.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            engine = module.NetlistEngine()
            plan = {"elaborated_requirement": "Common-emitter amplifier with gain 10",
                    "components": [{"uid": "PART3", "search_query": "Resistor"}]}
            expert = BjtAmplifierExpert()
            expert.set_targets({"metric": "max_gain_db", "value": 20})
            with patch.object(expert, 'clean_spice_code', wraps=expert.clean_spice_code) as cleanup:
                cleaned = engine.generate_spice(plan, expert)
                enabled_calls = cleanup.call_count
                self.assertGreater(enabled_calls, 0)
                engine.cleanup_enabled = False
                raw = engine.generate_spice(plan, expert)
                self.assertEqual(cleanup.call_count, enabled_calls)
            with patch.object(engine.client.chat.completions, 'create', side_effect=ValueError('invalid response')):
                with self.assertRaises(ValueError):
                    engine.generate_spice(plan, expert)
            self.assertIsNone(engine.last_response)
            self.assertEqual(engine.last_usage, {})
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(raw, deck.strip())
        self.assertIn("R1 IN OUT 1k", cleaned)
        self.assertIn("R1 A B 1k", cleaned)
        self.assertNotIn("_DUP", cleaned)
        self.assertEqual(engine.last_component_bindings[0]["spice_reference"], "R_PART3")
        self.assertIn("R_PART3", requests[0]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
