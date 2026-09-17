import unittest

from alignment_config import digest
from formal_protocol import (MAIN_ARMS, ABLATION_ARMS, generic_prompts,
                             validate_allocation, validate_inputs)


class FormalProtocolTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'status': 'frozen', 'version': 'unified20-formal-v1',
                         'models': {'v4': {'requested_model': 'request',
                                           'expected_response_model': 'response',
                                           'endpoint_sha256': 'endpoint'}, 'gpt4o': {}},
                         'tasks': ['eda_005', 'eda_201'], 'ablation_backbone': 'v4',
                         'dataset_sha256': digest({'cases': []}), 'source_hashes': {'file': 'hash'},
                         'baseline_template_hashes': {'adapter': 'template'}}

    def test_rejects_missing_arms_and_out_of_matrix_units(self):
        validate_allocation(self.manifest, 'v4', 'eda_201', 3,
                            MAIN_ARMS + ABLATION_ARMS + ['equal_call'])
        validate_allocation(self.manifest, 'gpt4o', 'eda_005', 1, MAIN_ARMS)
        for model, task, repeat, arms in [('v4', 'eda_201', 1, MAIN_ARMS),
                                         ('gpt4o', 'eda_999', 1, MAIN_ARMS),
                                         ('gpt4o', 'eda_005', 4, MAIN_ARMS),
                                         ('gpt4o', 'eda_005', 1, MAIN_ARMS + ['full'])]:
            with self.assertRaises(ValueError):
                validate_allocation(self.manifest, model, task, repeat, arms)

    def test_changed_inputs_are_rejected_before_requests(self):
        args = dict(config_model='request', expected_model='response', model='v4',
                    endpoint_sha256='endpoint', templates={'adapter': 'template'})
        validate_inputs(self.manifest, {'cases': []}, {'file': 'hash'}, **args)
        for field, value in [('config_model', 'different'), ('expected_model', 'different'),
                             ('endpoint_sha256', 'different'), ('templates', {})]:
            with self.assertRaises(ValueError):
                validate_inputs(self.manifest, {'cases': []}, {'file': 'hash'}, **{**args, field: value})
        with self.assertRaises(ValueError):
            validate_inputs(self.manifest, {'cases': [1]}, {'file': 'hash'}, **args)
        with self.assertRaises(ValueError):
            validate_inputs(self.manifest, {'cases': []}, {'file': 'changed'}, **args)

    def test_generic_retains_feedback_and_fixed_model_contract(self):
        system, user = generic_prompts('visible requirement', 'R1', 2, '* previous', 'failed gain')
        self.assertIn('do not define local device models', system)
        self.assertIn('visible requirement', user)
        self.assertIn('R1', user)
        self.assertIn('* previous', user)
        self.assertIn('failed gain', user)


if __name__ == '__main__':
    unittest.main()
