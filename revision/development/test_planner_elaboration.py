import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
import unittest


class PlannerElaborationTests(unittest.TestCase):
    def invoke(self, finish, content):
        path = Path(__file__).with_name('circuit_planner_v.py')
        tree = ast.parse(path.read_text())
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                        and n.name == '_elaborate_requirement')
        namespace = {'Optional': Optional, 'MODEL_NAME': 'fixture', '_thinking_kwargs': lambda: {}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
        requests = []
        response = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish, message=SimpleNamespace(content=content))])
        def create(**request):
            requests.append(request)
            return response
        recorded = []
        planner = SimpleNamespace(client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create))), _record_usage=recorded.append)
        result = namespace['_elaborate_requirement'](planner, 'Original CE requirement', seed=7)
        self.assertEqual(len(requests), 1)
        self.assertEqual(recorded, [response])
        self.assertEqual(requests[0]['max_tokens'], 800)
        return result

    def test_truncated_or_empty_summary_falls_back_to_original(self):
        for finish, content in [('length', 'Partial false plan'), ('stop', None)]:
            self.assertEqual(self.invoke(finish, content), 'Original CE requirement')

    def test_complete_summary_is_used(self):
        self.assertEqual(self.invoke('stop', '  Roles only  '), 'Roles only')


if __name__ == '__main__':
    unittest.main()
