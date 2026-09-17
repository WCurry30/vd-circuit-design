from pathlib import Path
import unittest

from benchmark_structure import topology_checks


ROOT = Path(__file__).resolve().parents[1] / 'benchmark/references'


class AmplifierPathTests(unittest.TestCase):
    def test_microphone_bias_rail_is_not_signal_bypass(self):
        from revision_spec import structural_checks
        deck = ('* biased AC coupling\nVCC VCC 0 12\nVIN IN 0 DC 0 AC 1\n'
                'RB VCC IN 4.7k\nCIN IN NP 10u\nRBIAS NP MID 100k\n'
                'RUP VCC MID 100k\nRDOWN MID 0 100k\n'
                'X1 NP NM VCC 0 OUT LM2904\n')
        self.assertTrue(structural_checks(deck, {'input_coupling': True})['input_coupling'])
        self.assertFalse(structural_checks(deck + 'RBYP IN NP 1k\n',
                                          {'input_coupling': True})['input_coupling'])

    def test_inverter_dual_supply_allows_chosen_voltage_and_polarity(self):
        deck = (ROOT / 'eda_005.cir').read_text()
        self.assertTrue(all(topology_checks(deck, 'inverter').values()))
        # The task prescribes dual rails, not a particular voltage magnitude.
        alternate = deck.replace('VCC VCC 0 12', 'VCC VCC 0 9').replace(
            'VEE VEE 0 -12', 'VEE 0 VEE 9')
        self.assertTrue(all(topology_checks(alternate, 'inverter').values()))
        for bad in (deck.replace('VEE VEE 0 -12', ''),
                    deck.replace('VEE VEE 0 -12', 'VEE VEE 0 0'),
                    deck.replace('VCC VEE OUT LM2904', 'VCC 0 OUT LM2904')):
            with self.subTest(deck=bad):
                self.assertFalse(all(topology_checks(bad, 'inverter').values()))

    def test_led_reference_divider_belongs_to_control_amplifier(self):
        deck = (ROOT / 'eda_209.cir').read_text()
        def accepted(text):
            return all(topology_checks(text, 'opamp_nmos_led', reference_divider=True).values())
        self.assertTrue(accepted(deck))
        self.assertTrue(accepted(deck.replace('XU1 REF', 'RISO REF REF_IN 1k\nXU1 REF_IN')))
        for bad in (deck.replace('RREF1 VCC REF 49k', ''),
                    deck.replace('RREF2 REF 0 1k', ''),
                    deck.replace('XU1 REF', 'XU1 FLOATING'),
                    deck.replace('XU1 REF', 'CISO REF REF_IN 1u\nXU1 REF_IN')):
            with self.subTest(deck=bad):
                self.assertFalse(accepted(bad))

    def test_active_filter_requires_exactly_one_opamp(self):
        deck = (ROOT / 'eda_027.cir').read_text()
        self.assertTrue(all(topology_checks(deck, 'active_rc').values()))
        for extra in ('XEXTRA 0 AUX VCC VEE AUX LM2904',
                      'XEXTRA OUT AUX VCC VEE AUX LM2904'):
            with self.subTest(extra=extra):
                changed = deck.replace('.end', extra + '\n.end')
                checks = topology_checks(changed, 'active_rc')
                self.assertTrue(checks['active_rc_feedback'])
                self.assertFalse(checks['single_opamp'])

    def test_feedback_on_detached_amplifier_is_insufficient(self):
        deck = (ROOT / 'eda_006.cir').read_text()
        self.assertTrue(all(topology_checks(deck, 'noninverting_ac').values()))
        detached = deck.replace('RF OUT NM', 'RF DETACHED NM').replace(
            'VCC VEE OUT LM2904', 'VCC VEE DETACHED LM2904')
        self.assertFalse(all(topology_checks(detached, 'noninverting_ac').values()))

    def test_audio_requires_connected_virtual_ground_divider(self):
        deck = (ROOT / 'eda_024.cir').read_text()
        self.assertTrue(all(topology_checks(deck, 'single_supply_audio').values()))
        for bad in (deck.replace('RVM1 VCC VBIAS 47k', ''),
                    deck.replace('RVM2 VBIAS 0 47k', ''),
                    deck.replace('RBIAS NP VBIAS', 'RBIAS NP 0'),
                    deck.replace('COUT AOUT OUT', 'COUT DETACHED OUT')):
            with self.subTest(deck=bad):
                self.assertFalse(all(topology_checks(bad, 'single_supply_audio').values()))


if __name__ == '__main__':
    unittest.main()
