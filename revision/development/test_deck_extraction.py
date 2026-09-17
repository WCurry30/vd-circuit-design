import json
from pathlib import Path
import unittest

from spice_contract import extract_spice_deck


class ExtractionTests(unittest.TestCase):
    def test_bare_and_fenced_decks_preserve_content(self):
        deck = '* circuit\nV1 IN 0 5\nR1 IN 0 1k\n.end'
        self.assertEqual(extract_spice_deck(deck), deck)
        for tag in ('', 'spice', 'SPICE', 'cir'):
            self.assertEqual(extract_spice_deck('Explanation\n```' + tag + '\n' + deck + '\n```\nNotes'), deck)

    def test_ambiguous_and_incomplete_fences_fail(self):
        for text in ('```\nR1 A B 1k', '```\nR1 A B 1k\n```\n```\nR2 A B 2k\n```',
                     '```python\nprint(1)\n```', '```\n```', ''):
            with self.subTest(text=text), self.assertRaises(ValueError):
                extract_spice_deck(text)

    def test_archived_zener_prose_is_excluded(self):
        root = Path(__file__).resolve().parents[1]
        source = root / 'evidence/pilot-v4/units/v4/eda_016/1/full/calls/call_02/response.json'
        if not source.exists():
            self.skipTest('archived development response is not installed')
        response = json.loads(source.read_text())['choices'][0]['message']['content']
        deck = extract_spice_deck(response)
        self.assertTrue(deck.startswith('* 5.1V'))
        self.assertTrue(deck.endswith('RLOAD BUFFER_OUT 0 1k'))
        self.assertIn('D1 0 OUT 1N4733A', deck)


if __name__ == '__main__':
    unittest.main()
