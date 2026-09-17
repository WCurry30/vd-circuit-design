import unittest
from shared_spice_evaluator import _sanitize_deck
from unified_benchmark import fixed_model_deck


class TitleTests(unittest.TestCase):
    def test_short_title_is_comment_but_first_element_survives(self):
        deck = 'V1 VCC 0 DC 12\nR1 VCC OUT 220\n.end'
        self.assertTrue(_sanitize_deck(deck).startswith('V1 VCC'))
        titled = 'Zener reference circuit\n' + deck
        self.assertTrue(_sanitize_deck(titled).startswith('* Zener reference circuit'))
        self.assertIn('V1 VCC 0 DC 12', fixed_model_deck(titled))

    def test_later_prose_is_not_silently_removed(self):
        for prefix in ('* actual title\n', 'V1 VCC 0 12\n'):
            with self.assertRaises(ValueError):
                fixed_model_deck(prefix + 'Zener reference circuit\n.end')


if __name__ == '__main__':
    unittest.main()
