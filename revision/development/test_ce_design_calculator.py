import tempfile
from pathlib import Path
import unittest

from ce_design_calculator import size_ce
from unified_benchmark import fixed_model_deck
from shared_spice_evaluator import NodeManifest, evaluate_deck
from operating_point_feedback import bjt_operating_point


class CeCalculatorTests(unittest.TestCase):
    def test_invalid_and_infeasible_inputs_rejected(self):
        for gain in (0, float('nan'), 0.1, 10000):
            with self.subTest(gain=gain), self.assertRaises(ValueError):
                size_ce(supply_v=12, gain_magnitude=gain, load_ohms=10000, collector_current_a=.001)

    def test_independent_sizing_points_in_real_spice(self):
        for supply, gain, load in ((9, 7, 8200), (15, 12, 22000), (6, 4, 6800)):
            with self.subTest(supply=supply, gain=gain):
                design = size_ce(supply_v=supply, gain_magnitude=gain, load_ohms=load,
                                 collector_current_a=.001)
                r = design['resistors_ohms']
                deck = (f'* calculator qualification only\nVDD VCC 0 {supply}\nVIN IN 0 DC 0 AC 1\n'
                        f'RB1 VCC B {r["bias_upper"]}\nRB2 B 0 {r["bias_lower"]}\n'
                        f'RC VCC C {r["collector"]}\nRE E 0 {r["emitter"]}\n'
                        f'Q1 C B E 2N2222\nCIN IN B 100u\nCOUT C OUT 100u\nRLOAD OUT 0 {load}\n')
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    source = root / 'candidate.cir'
                    source.write_text(fixed_model_deck(deck))
                    result = evaluate_deck(source, NodeManifest('IN', 'OUT'),
                                           {'metric': 'gain_real_v_per_v', 'value': -gain, 'tolerance': .15},
                                           root / 'evaluation')
                    self.assertTrue(result.passed, result.detail)
                    bias = bjt_operating_point(source, {}, root / 'bias')
                    self.assertEqual(bias['status'], 'measured', bias)
                    self.assertTrue(all(d['vc'] > d['vb'] > d['ve'] for d in bias['devices']))


if __name__ == '__main__':
    unittest.main()
