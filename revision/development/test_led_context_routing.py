import unittest
from runtime_experts.led_constant_current_expert import LedConstantCurrentExpert
from unified_benchmark import MODEL_CONTRACT


class LedContextRoutingTests(unittest.TestCase):
    def prompt(self, requirement, planner=''):
        expert = LedConstantCurrentExpert()
        text = 'Original user requirement:\n' + requirement
        if planner:
            text += '\nPlanner elaboration:\n' + planner
        text += '\nShared public interface:\n' + MODEL_CONTRACT
        return expert.get_netlist_prompts(text, 'Q1(2N2222)', 2, 'Q1 C B E 2N2222', 'failed current')

    def test_catalog_and_planner_do_not_choose_mosfet_for_bjt(self):
        req = 'Use two NPN transistors in a feedback LED current sink.'
        plain, _ = self.prompt(req)
        polluted, user = self.prompt(req, 'Use an op-amp with NMOS instead.')
        self.assertEqual(plain, polluted)
        self.assertNotIn('Use the requested MOSFET topology', plain)
        self.assertIn('device count', plain)
        self.assertIn('Q1 C B E 2N2222', user)
        self.assertIn('failed current', user)

    def test_explicit_mosfet_keeps_specialized_guidance(self):
        system, user = self.prompt('Use an op-amp and N-channel MOSFET for an LED current sink.')
        self.assertIn('Use the requested MOSFET topology', system)
        self.assertIn('failed current', user)

    def test_unspecified_device_uses_generic_public_contract(self):
        system, _ = self.prompt('Design an LED current driver at the specified current.')
        self.assertNotIn('Use the requested MOSFET topology', system)
        self.assertNotIn('R3=', system)


if __name__ == '__main__':
    unittest.main()
