import json
from types import SimpleNamespace as S
import unittest

from sizing_conversation import generate_with_sizing


def response(tool=False):
    call = S(id='call1', function=S(name='size_ce', arguments=json.dumps({
        'supply_v': 9, 'gain_magnitude': 7, 'load_ohms': 8200, 'collector_current_a': .001})))
    return S(choices=[S(message=S(content=None if tool else '* deck', tool_calls=[call] if tool else None))])


class ConversationTests(unittest.TestCase):
    def test_replayed_tool_latency_does_not_change_repair_request(self):
        requests = []
        def create(**kwargs):
            requests.append(kwargs)
            return response()
        event = {'status': 'success', 'result': {'collector': 6000}, 'elapsed_seconds': .001}
        for latency in (.001, .9):
            event['elapsed_seconds'] = latency
            generate_with_sizing(create, {'messages': [{'role': 'user', 'content': 'repair'}]},
                                 remaining_calls=1, events=[event])
            self.assertEqual(event['elapsed_seconds'], latency)
        self.assertEqual(requests[0], requests[1])
        self.assertNotIn('elapsed_seconds', requests[0]['messages'][-1]['content'])

    def run_sequence(self, outputs, budget):
        requests, events = [], []
        def create(**kwargs):
            requests.append(kwargs)
            return outputs.pop(0)
        result = generate_with_sizing(create, {'model': 'fixture', 'messages': [
            {'role': 'user', 'content': 'public requirement'}]}, remaining_calls=budget, events=events)
        return result, requests, events

    def test_tool_and_deck_consume_two_calls(self):
        result, requests, events = self.run_sequence([response(True), response()], 2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]['tool_choice'], 'none')
        self.assertEqual(requests[1]['messages'][-2]['role'], 'tool')
        self.assertEqual(len(events), 1)
        self.assertEqual(result.choices[0].message.content, '* deck')

    def test_final_budget_call_does_not_offer_tool(self):
        _, requests, events = self.run_sequence([response()], 1)
        self.assertNotIn('tools', requests[0])
        self.assertEqual(events, [])

    def test_repeated_tool_request_is_rejected_without_third_call(self):
        with self.assertRaisesRegex(ValueError, 'repeated tool'):
            self.run_sequence([response(True), response(True)], 3)

    def test_unrequested_tool_at_last_call_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            self.run_sequence([response(True)], 1)

    def test_serialized_tool_call_is_not_a_deck(self):
        for after_tool in (False, True):
            with self.subTest(after_tool=after_tool):
                leaked = response()
                leaked.choices[0].message.content = (
                    'Let me refine these values:\n'
                    '<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>\n'
                    '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="size_ce">')
                outputs = [response(True), leaked] if after_tool else [leaked]
                with self.assertRaisesRegex(ValueError, 'serialized tool invocation'):
                    self.run_sequence(outputs, 3)

    def test_repair_retains_tool_result_without_extra_call(self):
        requests = []
        events = [{'status': 'success', 'result': {'resistors_ohms': {'collector': 6000}}}]
        original = {'model': 'fixture', 'messages': [{'role': 'user', 'content': 'repair'}]}
        def create(**kwargs):
            requests.append(kwargs)
            return response()
        generate_with_sizing(create, original, remaining_calls=1, events=events)
        self.assertEqual(len(requests), 1)
        self.assertNotIn('tools', requests[0])
        self.assertIn('6000', requests[0]['messages'][-1]['content'])
        self.assertEqual(len(original['messages']), 1)
        self.assertEqual(len(events), 1)


if __name__ == '__main__':
    unittest.main()
