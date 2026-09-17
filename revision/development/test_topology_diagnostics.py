import json
from pathlib import Path
import unittest

from benchmark_structure import topology_checks, topology_diagnostics, led_series_path
from revision_spec import statements


ROOT = Path(__file__).resolve().parents[1]


class TopologyDiagnosticTests(unittest.TestCase):
    def test_audio_output_diagnostic_uses_actual_terminals(self):
        deck = ('* wrong public output\nVCC VCC 0 12\n'
                'X1 NP NM VCC 0 OUT LM2904\nCOUT OUT LOAD 10u\nRLOAD LOAD 0 10k\n')
        checks = topology_checks(deck, 'single_supply_audio')
        text = ' '.join(topology_diagnostics(deck, 'single_supply_audio'))
        self.assertIn('positive_input=NP', text)
        self.assertIn('load side', text)
        self.assertEqual(checks, topology_checks(deck, 'single_supply_audio'))

    def test_references_have_no_topology_diagnostics(self):
        cases = json.loads((ROOT / 'benchmark/synthesis_20.json').read_text())['cases']
        for case in cases:
            with self.subTest(task=case['id']):
                deck = (ROOT / 'benchmark/references' / (case['id'] + '.cir')).read_text()
                self.assertEqual(topology_diagnostics(deck, case['topology']), [])

    def test_led_probe_to_ground_identifies_broken_supply_path(self):
        deck = ('* miswired LED\nVCC VCC 0 12\n'
                'X1 REF SENSE VCC 0 GATE LM2904\n'
                'M1 OUT GATE SENSE 0 EDA_NMOS W=10u L=1u\n'
                'R1 SENSE 0 1\nD1 VLOAD OUT LED\nVLOAD OUT 0 0\n')
        checks = topology_checks(deck, 'opamp_nmos_led')
        text = '\n'.join(topology_diagnostics(deck, 'opamp_nmos_led'))
        self.assertIn('positive=OUT, negative=0', text)
        self.assertIn('No unbranched forward LED chain', text)
        self.assertEqual(topology_checks(deck, 'opamp_nmos_led'), checks)
        self.assertFalse(all(checks.values()))

    def test_collector_named_out_identifies_output_interface_error(self):
        deck = ('* incorrect output interface\nQ1 OUT BASE EMITTER 2N2222\n'
                'R1 EMITTER 0 1k\nC1 IN BASE 1u\nC2 OUT LOAD 1u\n')
        text = '\n'.join(topology_diagnostics(deck, 'ce'))
        self.assertIn('OUT is directly the collector', text)

    def test_series_led_chain_rejects_reversal_disconnection_and_shunts(self):
        deck = '* chain\nD1 VCC A LED\nD2 A B LED\nD3 B K LED\nVLOAD K OUT 0\n'
        self.assertTrue(led_series_path(statements(deck), 'VCC', 'K'))
        for invalid in (deck.replace('D2 A B', 'D2 B A'),
                        deck.replace('D2 A B', 'D2 Z B'),
                        deck + 'R1 A 0 1k\n', deck + 'D4 A B LED\n'):
            with self.subTest(deck=invalid):
                self.assertFalse(led_series_path(statements(invalid), 'VCC', 'K'))


if __name__ == '__main__':
    unittest.main()
