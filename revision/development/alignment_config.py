"""Private provider selection and public, versioned experiment matrix."""

import hashlib
import json
from pathlib import Path


MODELS = {
    'v4': 'deepseek-v4-flash',
    'v32': 'Pro/deepseek-ai/DeepSeek-V3.2',
    'qwen36': 'Qwen/Qwen3.6-35B-A3B',
    'gpt4o': 'gpt-4o',
}
CORE_ARMS = ('full', 'direct', 'analogcoder')
V4_ARMS = ('equal_call', 'spicepilot', 'no_preparation', 'no_grounding',
           'no_family_prompts', 'no_cleanup')
TRANSFER_ARMS = ('full', 'direct', 'analogcoder', 'equal_call')


def provider_blocks(path):
    """Read repeated URL/KEY/MODEL triplets without shell evaluation."""
    blocks, current = {}, {}
    for number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or key not in {'URL', 'KEY', 'MODEL'}:
            raise ValueError(f'unsupported provider entry at line {number}')
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        if not value or key in current:
            raise ValueError(f'incomplete or repeated provider field at line {number}')
        current[key] = value
        if len(current) == 3:
            model = current['MODEL']
            if model in blocks:
                raise ValueError('duplicate model configuration')
            blocks[model] = current
            current = {}
    if current:
        raise ValueError('incomplete provider triplet')
    return blocks


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def matrix(cases):
    rows = []
    for model in MODELS:
        for case in cases:
            if case['split'] == 'transfer':
                arms = TRANSFER_ARMS if model == 'v4' else ()
            else:
                arms = CORE_ARMS + (V4_ARMS if model == 'v4' else ())
            for repeat in (1, 2, 3):
                for arm in arms:
                    rows.append({'model': model, 'task_id': case['id'],
                                 'repeat': repeat, 'arm': arm})
    return rows
