import unittest

from benchmark_structure import testbench_connections, supply_diagnostics
from shared_spice_evaluator import _spice_number


class TestbenchConnectionTests(unittest.TestCase):
    def test_spice_scale_and_trailing_unit_letters(self):
        for token, expected in [('15V', 15), ('-15V', -15), ('1kOhm', 1000),
                                ('2.2uF', 2.2e-6), ('1MEGOhm', 1e6),
                                ('1m', .001), ('1e-3V', .001), ('1mil', 25.4e-6)]:
            with self.subTest(token=token):
                self.assertAlmostEqual(_spice_number(token), expected)
        for token in ('NaN', 'inf', '12/3', '1k2', '{value}'):
            with self.assertRaises(ValueError):
                _spice_number(token)

    def test_dual_supply_must_power_actual_opamp_terminals(self):
        checks = [{'nodes': {'input': 'IN', 'output': 'OUT'},
                   'condition': {'dc_sources': {'VCC': 12, 'VEE': -12}}}]
        deck = ('* dual supply\nVCC VCC 0 12\nVEE VEE 0 -12\n'
                'XU1 IN NM VCC VEE OUT LM2904\n')
        self.assertTrue(all(testbench_connections(deck, checks).values()))
        for rails in ('FLOAT VEE', 'VCC FLOAT', 'VEE VCC', 'VCC 0'):
            with self.subTest(rails=rails):
                bad = deck.replace('NM VCC VEE OUT', 'NM ' + rails + ' OUT')
                self.assertFalse(all(testbench_connections(bad, checks).values()))
        extra = deck + 'XU2 IN NM FLOAT VEE EXTRA LM2904\n'
        self.assertFalse(all(testbench_connections(extra, checks).values()))

    def test_source_name_does_not_alias_its_terminal(self):
        deck = '* mistaken source node\nVCC 1 0 DC 12\nR1 VCC BASE 100k\n'
        self.assertIn('positive=1', ' '.join(supply_diagnostics(deck)))
        self.assertEqual(supply_diagnostics(deck.replace('VCC 1 0', 'VCC VCC 0')), [])

    def checks(self):
        return [{'nodes': {'input': 'IN', 'output': 'OUT'},
                 'condition': {'dc_sources': {'VDD': 12},
                               'resistances': {'RLOAD': 1000}}}]

    def test_public_supply_and_load_terminals(self):
        deck = '* valid\nVDD VCC 0 12\nRLOAD OUT 0 1k\n'
        self.assertTrue(all(testbench_connections(deck, self.checks()).values()))
        reversed_load = deck.replace('RLOAD OUT 0', 'RLOAD 0 OUT')
        self.assertTrue(all(testbench_connections(reversed_load, self.checks()).values()))

    def test_detached_dummy_load_and_supply_are_rejected(self):
        deck = '* valid\nVDD VCC 0 12\nRLOAD OUT 0 1k\n'
        for bad in (deck.replace('RLOAD OUT', 'RLOAD DUMMY'),
                    deck.replace('VDD VCC', 'VDD DUMMY'),
                    deck.replace('VDD VCC 0', 'VDD 0 VCC'),
                    deck + 'RLOAD OUT 0 2k\n'):
            with self.subTest(deck=bad):
                self.assertFalse(all(testbench_connections(bad, self.checks()).values()))

    def test_subcircuit_dummy_does_not_satisfy_top_level_load(self):
        deck = ('* nested\nVDD VCC 0 12\n.subckt CELL OUT\n'
                'RLOAD OUT 0 1k\n.ends CELL\n')
        self.assertFalse(all(testbench_connections(deck, self.checks()).values()))


if __name__ == '__main__':
    unittest.main()
