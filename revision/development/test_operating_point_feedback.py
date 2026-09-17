import json
from pathlib import Path
import tempfile
import unittest

from operating_point_feedback import bjt_operating_point, opamp_operating_point
from unified_benchmark import ROOT, evaluate_candidate, fixed_model_deck


class OperatingPointTests(unittest.TestCase):
    def test_opamp_numeric_failure_reports_bias_without_changing_acceptance(self):
        case = next(c for c in json.loads((ROOT / 'synthesis_20.json').read_text())['cases'] if c['id'] == 'eda_005')
        deck = (ROOT / 'references/eda_005.cir').read_text()
        wrong_target = {**case, 'checks': [{**case['checks'][0],
                         'target': {**case['checks'][0]['target'], 'value': -1000}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.cir'
            source.write_text(deck)
            good = evaluate_candidate(source, case, root / 'good')
            self.assertTrue(good.passed)
            self.assertNotIn('opamp_bias_01', good.artifacts)
            bad = evaluate_candidate(source, wrong_target, root / 'bad')
            self.assertFalse(bad.passed)
            self.assertAlmostEqual(good.measured, bad.measured)
            report = json.loads(Path(bad.artifacts['opamp_bias_01']).read_text())
            self.assertEqual(report['status'], 'measured', report)
            self.assertIn('DC: positive input', bad.detail)
            self.assertAlmostEqual(report['devices'][0]['positive_supply'], 12)
            self.assertAlmostEqual(report['devices'][0]['negative_supply'], -12)

    def test_opamp_condition_and_invalid_terminal_diagnostic(self):
        deck = (ROOT / 'references/eda_005.cir').read_text().replace('NM', 'IN-')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.cir'
            source.write_text(fixed_model_deck(deck))
            report = opamp_operating_point(source, {'condition': {'dc_sources': {'VCC': 9}}}, root / 'valid')
            self.assertEqual(report['status'], 'measured', report)
            self.assertAlmostEqual(report['devices'][0]['positive_supply'], 9)
            source.write_text('* no opamp\nV1 A 0 1\nR1 A 0 1k\n.end\n')
            invalid = opamp_operating_point(source, {}, root / 'invalid')
            self.assertEqual(invalid['status'], 'unavailable')
            self.assertNotIn('devices', invalid)

    def test_numeric_pass_does_not_hide_saturation(self):
        case = next(c for c in json.loads((ROOT / 'synthesis_20.json').read_text())['cases'] if c['id'] == 'eda_007')
        deck = ('* archived saturated gain match\nQ1 C B E 2N2222\n'
                'R1 VCC B 180k\nR2 B 0 47k\nRC VCC C 10k\nRE E 0 1k\n'
                'CIN IN B 10u\nCOUT C OUT 10u\nCE E 0 100u\n'
                'CBYPASS VCC 0 0.1u\nVCC VCC 0 12\nVIN IN 0 DC 0 AC 1\n'
                'RLOAD OUT 0 100k\n.end\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.cir'
            source.write_text(deck)
            result = evaluate_candidate(source, case, root / 'evaluation')
            joint = json.loads(Path(result.artifacts['joint_evaluation']).read_text())
            self.assertTrue(joint['numerical']['passed'])
            self.assertTrue(all(joint['structure'].values()))
            self.assertFalse(joint['operating_point'][0]['passed'])
            self.assertFalse(result.passed)
            self.assertIn('forward-active OP requires', result.detail)

    def test_saturation_reaches_joint_feedback(self):
        case = next(c for c in json.loads((ROOT / 'synthesis_20.json').read_text())['cases'] if c['id'] == 'eda_007')
        deck = (ROOT / 'references/eda_007.cir').read_text().replace('RC VCC C 2.2k', 'RC VCC C 100k')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.cir'
            source.write_text(deck)
            result = evaluate_candidate(source, case, Path(directory) / 'evaluation')
            self.assertFalse(result.passed)
            self.assertIn('Collector is not above base', result.detail)
            self.assertIn('bias_01', result.artifacts)

    def test_condition_is_applied_and_solver_failure_is_not_bias(self):
        deck = (ROOT / 'references/eda_007.cir').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.cir'
            source.write_text(fixed_model_deck(deck))
            report = bjt_operating_point(source, {'condition': {'dc_sources': {'VDD': 9}}}, root / 'valid')
            self.assertEqual(report['status'], 'measured', report)
            self.assertIn('alter VDD dc = 9', (root / 'valid/operating_point.cir').read_text())
            source.write_text(fixed_model_deck(deck.replace('RLOAD OUT 0 10k', '')))
            invalid = bjt_operating_point(source, {}, root / 'invalid')
            self.assertEqual(invalid['status'], 'unavailable', invalid)
            self.assertNotIn('devices', invalid)


if __name__ == '__main__':
    unittest.main()
