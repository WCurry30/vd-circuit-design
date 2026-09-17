import json
import unittest

from sizing_tool import SizingTool


class SizingToolTests(unittest.TestCase):
    def arguments(self):
        return {'supply_v': 9, 'gain_magnitude': 7, 'load_ohms': 8200, 'collector_current_a': .001}

    def test_explicit_call_records_result_without_hidden_invocations(self):
        tool = SizingTool()
        reply = tool.execute(name='size_ce', arguments=json.dumps(self.arguments()), call_id='call1')
        self.assertEqual(reply['tool_call_id'], 'call1')
        self.assertEqual(json.loads(reply['content'])['status'], 'success')
        self.assertEqual(tool.events[0]['api_calls'], 0)
        self.assertEqual(tool.events[0]['simulator_calls'], 0)
        with self.assertRaises(ValueError):
            tool.execute(name='size_ce', arguments=json.dumps(self.arguments()), call_id='call2')

    def test_invalid_arguments_are_recorded_and_consume_tool_budget(self):
        invalid = [dict(self.arguments(), supply_v=True), dict(self.arguments(), task_id='eda_007'),
                   dict(self.arguments(), load_ohms=float('inf'))]
        for args in invalid:
            tool = SizingTool()
            result = tool.execute(name='size_ce', arguments=json.dumps(args), call_id='bad')
            self.assertEqual(json.loads(result['content'])['status'], 'error')
            self.assertEqual(len(tool.events), 1)

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        args = json.dumps(self.arguments()).replace('"supply_v": 9', '"supply_v": 9, "supply_v": 12')
        tool = SizingTool()
        reply = tool.execute(name='size_ce', arguments=args, call_id='duplicate')
        self.assertIn('duplicate argument', json.loads(reply['content'])['error'])


if __name__ == '__main__':
    unittest.main()
