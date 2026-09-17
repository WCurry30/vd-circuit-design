import json
from pathlib import Path
import tempfile
import unittest

from runtime_experts.zener_regulator_expert import ZenerRegulatorExpert
from spice_contract import clean_preserving_definitions
from unified_benchmark import ROOT, evaluate_candidate


class ZenerCleanupTests(unittest.TestCase):
    def test_buffer_transistor_and_bias_resistor_survive_cleanup(self):
        deck = '* buffer\nQ1 VCC BASE OUT 2N2222\nR_B VCC BASE 1k\n'
        cleaned = ZenerRegulatorExpert().clean_spice_code(deck)
        self.assertIn('Q1 VCC BASE OUT 2N2222', cleaned)
        self.assertIn('R_B VCC BASE 1k', cleaned)

    def test_buffered_reference_remains_electrically_valid(self):
        cases = json.loads((ROOT / 'synthesis_20.json').read_text())['cases']
        case = next(c for c in cases if c['topology'] == 'buffered_zener')
        source = (ROOT / 'references' / (case['id'] + '.cir')).read_text()
        cleaned = clean_preserving_definitions(source, ZenerRegulatorExpert().clean_spice_code)
        with tempfile.TemporaryDirectory() as folder:
            deck = Path(folder) / 'candidate.cir'
            deck.write_text(cleaned)
            result = evaluate_candidate(deck, case, Path(folder) / 'evaluation')
            self.assertTrue(result.passed, result.detail)


if __name__ == '__main__':
    unittest.main()
