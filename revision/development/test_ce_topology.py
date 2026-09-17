from pathlib import Path
import unittest

from benchmark_structure import topology_checks


ROOT = Path(__file__).resolve().parents[1] / 'benchmark/references'


class CeTopologyTests(unittest.TestCase):
    def test_bias_and_collector_feed_are_required(self):
        deck = (ROOT / 'eda_203.cir').read_text()
        for line in ('RBIAS1 VCC B 47k', 'RBIAS2 B 0 4.7k', 'RC VCC C 3.3k'):
            with self.subTest(line=line):
                self.assertFalse(all(topology_checks(deck.replace(line, ''), 'degenerated_ce').values()))

    def test_split_emitter_return_is_valid(self):
        deck = (ROOT / 'eda_203.cir').read_text().replace('RE E 0 360', 'RE1 E MID 180\nRE2 MID 0 180')
        self.assertTrue(all(topology_checks(deck, 'degenerated_ce').values()))
        for bypass in ('CB MID 0 100u', 'CB E VCC 100u', 'CB1 E FLOAT 100u\nCB2 FLOAT 0 100u', 'CB E MID 100u'):
            with self.subTest(bypass=bypass):
                candidate = deck.replace('.end', bypass + '\n.end')
                self.assertFalse(all(topology_checks(candidate, 'degenerated_ce').values()))
                self.assertTrue(all(topology_checks(candidate, 'ce').values()))

    def test_two_stages_require_both_bias_networks(self):
        deck = (ROOT / 'eda_204.cir').read_text()
        self.assertTrue(all(topology_checks(deck, 'two_ce').values()))
        self.assertFalse(all(topology_checks(deck.replace('RB22 B2 0 6.8k', ''), 'two_ce').values()))


if __name__ == '__main__':
    unittest.main()
