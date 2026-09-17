"""Fail-closed allocation and input checks for the preregistered formal matrix."""

from alignment_config import digest

MAIN_ARMS = ['full', 'direct', 'analogcoder', 'spicepilot']
ABLATION_ARMS = ['no_preparation', 'no_grounding', 'no_family_prompts', 'no_cleanup']


def validate_allocation(manifest, model, task, repeat, arms):
    if manifest.get('version') == 'unified20-routing-fix-v1':
        expected = ['full', 'no_preparation', 'no_grounding', 'no_family_prompts', 'no_cleanup', 'equal_call']
        if (manifest.get('status') != 'frozen' or model != 'v4' or model not in manifest['models']
                or task not in manifest['tasks'] or repeat not in [1, 2, 3]
                or len(arms) != len(set(arms)) or set(arms) != set(expected)):
            raise ValueError('unit differs from frozen routing-fix allocation')
        return
    if manifest.get('status') != 'frozen' or manifest.get('version') != 'unified20-formal-v1':
        raise ValueError('a frozen formal-v1 manifest is required')
    if model not in manifest['models'] or task not in manifest['tasks'] or repeat not in [1, 2, 3]:
        raise ValueError('unit outside the frozen matrix')
    expected = MAIN_ARMS + (ABLATION_ARMS + ['equal_call']
                            if model == manifest['ablation_backbone'] else [])
    if len(arms) != len(set(arms)) or set(arms) != set(expected):
        raise ValueError('unit arms differ from the frozen allocation')


def validate_inputs(manifest, dataset, hashes, *, config_model, expected_model, model,
                    endpoint_sha256, templates):
    if digest(dataset) != manifest['dataset_sha256']:
        raise ValueError('dataset changed after freeze')
    if hashes != manifest['source_hashes']:
        raise ValueError('development or framework source changed after freeze')
    provider = manifest['models'][model]
    if (config_model, expected_model) != (provider['requested_model'], provider['expected_response_model']):
        raise ValueError('provider model differs from the frozen configuration')
    if endpoint_sha256 != provider['endpoint_sha256'] or templates != manifest['baseline_template_hashes']:
        raise ValueError('endpoint or baseline prompt differs from the frozen configuration')


def generic_prompts(requirement, uid_hint, iteration=1, previous_spice=None, feedback=None):
    """Remove family guidance while retaining the shared execution contract."""
    system = ('You are a circuit designer. Generate one complete Ngspice circuit. '
              'Return only one fenced ```spice``` block. Follow the shared public '
              'interface and model catalog; do not define local device models or subcircuits.')
    user = f'Requirement:\n{requirement}\n\nComponent hints:\n{uid_hint or "(none)"}'
    if previous_spice and feedback:
        user += f'\n\nPrevious candidate:\n{previous_spice}\nFeedback:\n{feedback}\nReturn a complete corrected deck.'
    return system, user
