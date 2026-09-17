import ast
import json
from pathlib import Path
import re
import unittest


def load_cleaner(path):
    tree = ast.parse(path.read_text())
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == '_clean_and_repair_json')
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {'json': json, 're': re}
    exec(compile(module, str(path), 'exec'), namespace)
    return lambda text: namespace['_clean_and_repair_json'](None, text)


class PlannerJsonTests(unittest.TestCase):
    def setUp(self):
        self.clean = load_cleaner(Path(__file__).with_name('circuit_planner_v.py'))

    def test_valid_json_string_values_are_preserved(self):
        data = {'circuit_name': 'Reference: 5.1 V // nominal',
                'components': [{'id': 'D1', 'search_query': '1N4733A',
                                'description': 'Cathode: OUT; see https://example.org/model'}]}
        text = json.dumps(data)
        self.assertEqual(json.loads(self.clean(text)), data)

    def test_fenced_valid_json_is_parsed_before_repair(self):
        text = '{"components": [], "notes": "Power: 12V // DC"}'
        self.assertEqual(json.loads(self.clean('```json\n' + text + '\n```')), json.loads(text))

    def test_trailing_comma_fallback_remains_supported(self):
        self.assertEqual(json.loads(self.clean('{"components": [],}')), {'components': []})


if __name__ == '__main__':
    unittest.main()
