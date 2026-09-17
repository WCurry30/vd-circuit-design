import json
import unittest

from repair_history import repair_feedback


class RepairHistoryTests(unittest.TestCase):
    def test_first_failure_preserves_existing_feedback(self):
        self.assertIsNone(repair_feedback([]))
        self.assertEqual(repair_feedback([{'attempt': 1, 'deck': 'R1 A B 1k',
                                          'feedback': 'gain too high'}]), 'gain too high')

    def test_both_failed_designs_are_retained_in_order(self):
        rows = [{'attempt': 1, 'deck': 'R1 A B 1k', 'feedback': 'saturated'},
                {'attempt': 2, 'deck': 'R1 A B 2k', 'feedback': 'gain too high'}]
        data = json.loads(repair_feedback(rows).split('\n', 1)[1])
        self.assertEqual(data, rows)

    def test_history_is_bounded_and_parsing_failure_supported(self):
        rows = [{'attempt': i, 'deck': 'x' * 20000, 'feedback': 'y' * 5000} for i in range(4)]
        data = json.loads(repair_feedback(rows).split('\n', 1)[1])
        self.assertEqual([r['attempt'] for r in data], [2, 3])
        self.assertTrue(all(len(r['deck']) == 10000 and len(r['feedback']) == 3000 for r in data))


if __name__ == '__main__':
    unittest.main()
