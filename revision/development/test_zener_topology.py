import unittest

from benchmark_structure import topology_checks, topology_diagnostics


class ZenerTopologyTests(unittest.TestCase):
    def test_reversed_zener_feedback_reports_actual_polarity(self):
        deck = '* reversed\nR1 VCC OUT 220\nD1 OUT 0 1N4733A\n'
        before = topology_checks(deck, 'zener')
        feedback = ' '.join(topology_diagnostics(deck, 'zener'))
        self.assertIn('anode=OUT, cathode=0', feedback)
        self.assertIn('requires reverse bias', feedback)
        self.assertEqual(before, topology_checks(deck, 'zener'))
        self.assertEqual(topology_diagnostics(deck.replace('D1 OUT 0', 'D1 0 OUT'), 'zener'), [])

    def test_reference_supports_direct_or_unity_buffer_output(self):
        direct = '* direct\nR1 VCC OUT 470\nD1 0 OUT 1N4733A\n'
        buffered = ('* buffered\nR1 VCC REF 470\nD1 0 REF 1N4733A\n'
                    'X1 REF OUT VCC 0 OUT LM2904\n')
        for deck in (direct, buffered):
            self.assertTrue(all(topology_checks(deck, 'zener').values()))
        for deck in (buffered.replace('D1 0 REF', 'D1 REF 0'),
                     buffered.replace('X1 REF OUT', 'X1 OUT REF'),
                     buffered.replace('X1 REF OUT', 'X1 FLOAT OUT'),
                     buffered.replace('R1 VCC REF', 'R1 VCC FLOAT'),
                     buffered.replace('X1 REF OUT', 'X1 REF 0')):
            with self.subTest(deck=deck):
                self.assertFalse(all(topology_checks(deck, 'zener').values()))

    def test_explicit_loaded_shunt_still_requires_direct_path(self):
        buffered = ('* buffered\nR1 VCC REF 470\nD1 0 REF 1N4733A\n'
                    'X1 REF OUT VCC 0 OUT LM2904\nRLOAD OUT 0 1k\n')
        self.assertFalse(all(topology_checks(buffered, 'loaded_zener').values()))


if __name__ == '__main__':
    unittest.main()
