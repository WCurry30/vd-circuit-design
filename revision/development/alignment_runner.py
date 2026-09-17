"""Run a fixed synthesis matrix with response-level replay and trial checkpoints."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time

from alignment_config import MODELS, digest, matrix, provider_blocks

HERE = Path(__file__).resolve().parent


class ProviderInterruption(BaseException):
    """Stop legacy repair loops immediately after an infrastructure failure."""


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


class ResponseLedger:
    """Replay returned responses; stop on ambiguous interrupted requests."""

    def __init__(self, expected_model=None, disable_qwen_thinking=False):
        self.root = None
        self.index = 0
        self.error = None
        self.expected_model = expected_model
        self.disable_qwen_thinking = disable_qwen_thinking

    def validate_response(self, response):
        if self.expected_model and response.model != self.expected_model:
            self.error = 'returned model differs from frozen provider configuration'
            raise ProviderInterruption(self.error)
        return response

    @contextlib.contextmanager
    def scope(self, root):
        self.root, self.index, self.error = root, 0, None
        root.mkdir(parents=True, exist_ok=True)
        try:
            yield
            if self.error:
                raise ProviderInterruption(self.error)
        finally:
            self.root = None

    def install(self):
        import openai
        from openai.types.chat import ChatCompletion
        original = openai.OpenAI
        ledger = self

        def factory(*args, **kwargs):
            kwargs['max_retries'] = 0
            kwargs['timeout'] = 90
            client = original(*args, **kwargs)
            create = client.chat.completions.create

            def cached(**request):
                if ledger.disable_qwen_thinking:
                    extra = dict(request.get('extra_body') or {})
                    extra.pop('thinking', None)
                    request['extra_body'] = {**extra, 'enable_thinking': False}
                if ledger.root is None:
                    raise RuntimeError('model call outside an audited ledger scope')
                ledger.index += 1
                root = ledger.root / f'call_{ledger.index:02d}'
                requested = root / 'request.json'
                completed = root / 'response.json'
                error_path = root / 'error.json'
                transport_path = root / 'transport_attempts.json'
                failures = json.loads(transport_path.read_text()) if transport_path.exists() else []
                if not failures and error_path.exists():
                    failures = [json.loads(error_path.read_text())]
                if requested.exists():
                    if json.loads(requested.read_text()) != request:
                        ledger.error = 'request differs from interrupted trial'
                        raise ProviderInterruption(ledger.error)
                    if completed.exists():
                        return ledger.validate_response(ChatCompletion.model_validate(json.loads(completed.read_text())))
                    if not failures:
                        ledger.error = 'unresolved previous API call requires audit'
                        raise ProviderInterruption(ledger.error)
                else:
                    save(requested, request)
                transient = {'APIConnectionError', 'APITimeoutError', 'InternalServerError'}
                if failures and (failures[-1]['type'] not in transient or len(failures) >= 3):
                    ledger.error = 'provider recovery budget exhausted; checkpoint retained'
                    raise ProviderInterruption(ledger.error) from None
                while True:
                    try:
                        response = create(**request)
                        break
                    except Exception as error:
                        failures.append({'type': type(error).__name__})
                        save(transport_path, failures)
                        if type(error).__name__ not in transient or len(failures) >= 3:
                            ledger.error = 'provider call failed: ' + type(error).__name__
                            raise ProviderInterruption(ledger.error) from None
                        time.sleep(len(failures))
                save(completed, response.model_dump(mode='json'))
                return ledger.validate_response(response)

            client.chat.completions.create = cached
            return client

        openai.OpenAI = factory


def source_hashes(project):
    paths = list(HERE.rglob('*.py'))
    hashes = {'source/' + str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(paths)}
    for folder in ('framework', 'baselines/pipeline_methods'):
        for path in sorted((project / folder).rglob('*.py')):
            hashes['runtime/' + str(path.relative_to(project))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def freeze(args, provider):
    from revision_spec import build_cases
    cases = build_cases(args.cases)
    protocol = {
        'version': 'alignment-repair-development-v1', 'cases': cases, 'matrix': matrix(cases),
        'temperature': 0.3, 'synthesis_cap': 3, 'repeats': [1, 2, 3],
        'models': MODELS, 'thinking_disabled': {'v4': True, 'v32': False,
                                              'qwen36': True, 'gpt4o': False},
        'source_hashes': source_hashes(args.project),
        'baseline_template_hashes': {
            'analogcoder': hashlib.sha256((args.analogcoder / 'prompt_template.txt').read_bytes()).hexdigest(),
            'spicepilot': hashlib.sha256((args.spicepilot / 'Pilot_prompt.md').read_bytes()).hexdigest(),
        },
        'preparation': 'independent per model/task/repeat; paired across arms',
        'embedding_device': 'cpu',
        'selection': 'first scalar acceptance; separate selected-deck specification audit',
        'transfer_scope': 'five previously evaluated numerical variants, not new topologies',
        'transport_recovery': 'at most three sends per logical call after explicit transport errors; unknown completion stops',
        'pilot': args.pilot,
    }
    frozen = args.output / 'protocol.json'
    if frozen.exists() and json.loads(frozen.read_text()) != protocol:
        previous = json.loads(frozen.read_text())
        if not args.pilot or not previous.get('pilot'):
            raise ValueError('frozen protocol differs; use a new experiment directory')
        save(args.output / 'engineering_protocol_history' / (digest(previous) + '.json'), previous)
    save(frozen, protocol)
    config = {'requested_model': provider['MODEL'],
              'expected_response_model': args.expected_response,
              'endpoint_sha256': hashlib.sha256(provider['URL'].encode()).hexdigest(),
              'thinking_disabled': protocol['thinking_disabled'][args.model]}
    config_path = args.output / 'models' / (args.model + '.json')
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        previous = json.loads(config_path.read_text())
        if not args.pilot:
            raise ValueError('provider configuration differs from frozen run')
        save(args.output / 'engineering_protocol_history' / (digest(previous) + '.json'), previous)
    save(config_path, config)
    return protocol


def api_usage(root):
    rows = []
    for path in sorted(root.glob('call_*/response.json')):
        response = json.loads(path.read_text())
        rows.append({**(response.get('usage') or {}),
                     'response_model_id': response.get('model', '')})
    return rows


def configure_expert(legacy, plan, arm):
    expert = legacy.orchestrator_module.ExpertFactory.get_expert(plan['circuit_type'])
    expert.set_targets(plan['_benchmark_targets'])
    if arm == 'no_family_prompts':
        generic = legacy.orchestrator_module.ExpertFactory.get_expert('generic_circuit')
        expert.get_netlist_prompts = generic.get_netlist_prompts
    engine = (legacy._raw_engine_class()() if arm == 'no_cleanup'
              else legacy.netlist_module.NetlistEngine())
    return expert, engine


def run(args):
    provider = provider_blocks(args.env)[MODELS[args.model]]
    os.environ.update(EDA_API_KEY=provider['KEY'], OPENAI_API_KEY=provider['KEY'],
                      EDA_BASE_URL=provider['URL'], OPENAI_BASE_URL=provider['URL'],
                      EDA_MODEL_NAME=provider['MODEL'], EDA_API_MAX_RETRIES='0',
                      EDA_DISABLE_THINKING='1' if args.model in {'v4', 'qwen36'} else '0')
    os.environ.update(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    ledger = ResponseLedger(args.expected_response, disable_qwen_thinking=args.model == 'qwen36')
    ledger.install()
    from tcad_supplement.legacy import LegacyEDALastAdapter, _normalize_circuit_type
    from revision_preparation import install_contract
    from revision_spec import evaluate_spec
    from main_comparison_runner import _evaluation_callback, _with_shared_interface
    from generation_adapters import (OpenAICompatibleClient, DirectSpiceBaseline,
                                     AnalogCoderSharedAdapter, SpicePilotPromptAdapter)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.protocol.lock').open('a') as protocol_lock:
        fcntl.flock(protocol_lock, fcntl.LOCK_EX)
        protocol = freeze(args, provider)
    case = next(c for c in protocol['cases'] if c['id'] == args.task)
    unit = args.output / 'units' / args.model / args.task / str(args.repeat)
    unit.mkdir(parents=True, exist_ok=True)
    lock = (unit / '.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    arms = [r['arm'] for r in protocol['matrix'] if r['model'] == args.model
            and r['task_id'] == args.task and r['repeat'] == args.repeat]
    if not arms:
        raise ValueError('unit is outside the frozen matrix')
    seed = 91000 + int(args.task.split('_')[-1]) * 10 + args.repeat
    legacy = LegacyEDALastAdapter(args.project)
    install_contract(legacy)
    prep_file = unit / 'preparation.json'
    if not prep_file.exists():
        with ledger.scope(unit / 'planning_calls'):
            try:
                plan, retrieved = legacy.prepare(case['user_requirement'], seed=seed)
                if set(retrieved) != {c['uid'] for c in plan['components']}:
                    raise ValueError('incomplete retrieval binding')
                preparation = {'plan': plan, 'retrieved': retrieved, 'error': None}
            except Exception as error:
                if ledger.error:
                    raise RuntimeError(ledger.error) from None
                preparation = {'plan': None, 'retrieved': None, 'error': type(error).__name__}
        preparation['usage'] = api_usage(unit / 'planning_calls')
        save(prep_file, preparation)
    preparation = json.loads(prep_file.read_text())
    client = OpenAICompatibleClient(provider['MODEL'], provider['KEY'], provider['URL'],
                                   thinking_disabled=args.model in {'v4', 'qwen36'})
    kwargs = {'temperature': 0.3, 'max_calls': 3, 'ngspice': 'ngspice', 'timeout_seconds': 90}
    adapters = {'direct': DirectSpiceBaseline(client, **kwargs),
                'analogcoder': AnalogCoderSharedAdapter(client, analogcoder_root=args.analogcoder, **kwargs)}
    if 'spicepilot' in arms:
        adapters['spicepilot'] = SpicePilotPromptAdapter(client, spicepilot_root=args.spicepilot, **kwargs)
    order = [arm for arm in arms if arm != 'equal_call']
    random.Random(seed).shuffle(order)
    if 'equal_call' in arms:
        order.append('equal_call')
    for arm in order:
        workspace = unit / arm
        record_file = workspace / 'record.json'
        if record_file.exists():
            continue
        workspace.mkdir(exist_ok=True)
        record = {'model': args.model, 'requested_model': provider['MODEL'],
                  'task_id': case['id'], 'split': case['split'], 'repeat': args.repeat,
                  'arm': arm, 'seed': seed, 'passed': False, 'attempts': [],
                  'preparation_sha256': digest(preparation),
                  'provider_config_sha256': digest(json.loads((args.output / 'models' / (args.model + '.json')).read_text())),
                  'protocol_sha256': digest(protocol), 'preparation_error': None}
        uses_preparation = arm not in adapters and arm != 'no_preparation'
        record['planning_usage'] = preparation['usage'] if uses_preparation else []
        with ledger.scope(workspace / 'calls'):
            if arm in adapters:
                candidates = adapters[arm].run(case, workspace, seed=seed)
                for candidate in candidates:
                    record['attempts'].append({
                        'attempt': candidate.attempt,
                        'deck': str(Path(candidate.submitted_deck).relative_to(workspace)) if candidate.submitted_deck else None,
                        'evaluation': candidate.evaluation.as_dict() if candidate.evaluation else None,
                        'failure_stage': candidate.failure_stage,
                    })
            elif preparation['error'] and uses_preparation:
                record['preparation_error'] = preparation['error']
            else:
                route = _normalize_circuit_type(case['user_requirement'], 'amplifier')
                plan = (legacy.direct_plan(case['user_requirement'], circuit_type=route)
                        if arm == 'no_preparation' else preparation['plan'])
                plan = _with_shared_interface(plan)
                retrieved = {} if arm in {'no_preparation', 'no_grounding'} else preparation['retrieved']
                save(workspace / 'retrieved.json', retrieved)
                expert, engine = configure_expert(legacy, plan, arm)
                cap = 3
                if arm == 'equal_call':
                    paired = json.loads((unit / 'full' / 'record.json').read_text())
                    cap = paired['generation_calls']
                evaluate = _evaluation_callback(case, workspace, 'ngspice', 90)
                previous = feedback = None
                for attempt in range(1, cap + 1):
                    try:
                        code = engine.generate_spice(plan, expert, iteration=attempt,
                            previous_spice=previous, feedback=feedback,
                            retrieved_path=str(workspace / 'retrieved.json'),
                            temperature=0.3, seed=seed + attempt - 1)
                        save(workspace / 'component_bindings.json',
                             engine.last_component_bindings)
                    except (TypeError, ValueError, AttributeError) as error:
                        if ledger.error:
                            raise RuntimeError(ledger.error) from None
                        record['attempts'].append({'attempt': attempt, 'deck': None,
                            'evaluation': None, 'failure_stage': 'generation_parsing',
                            'error': type(error).__name__})
                        save(workspace / 'checkpoint.json', record)
                        continue
                    passed, message, measured = evaluate(code, attempt)
                    evaluation = json.loads((workspace / f'attempt_{attempt}' / 'common_evaluation.json').read_text())
                    record['attempts'].append({'attempt': attempt,
                        'deck': f'attempt_{attempt}/submitted.cir', 'evaluation': evaluation})
                    save(workspace / 'checkpoint.json', record)
                    if arm != 'equal_call':
                        if passed:
                            break
                        previous, feedback = code, message
        record['generation_usage'] = api_usage(workspace / 'calls')
        record['generation_calls'] = len(record['generation_usage'])
        successful = [a for a in record['attempts'] if (a['evaluation'] or {}).get('passed')]
        record['passed'] = bool(successful)
        selected = successful[0] if successful else next(
            (a for a in reversed(record['attempts']) if a.get('deck')), None)
        record['selected_attempt'] = selected['attempt'] if selected else None
        if selected:
            shutil.copyfile(workspace / selected['deck'], workspace / 'selected.cir')
            record['specification_audit'] = evaluate_spec(workspace / 'selected.cir', case,
                                                        workspace / 'specification_audit')
        save(record_file, record)
        print(json.dumps({key: record[key] for key in ('model', 'task_id', 'repeat', 'arm', 'passed')}), flush=True)
    lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('env', 'project', 'cases', 'output', 'analogcoder', 'spicepilot'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--model', choices=MODELS, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--repeat', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--expected-response')
    args = parser.parse_args()
    if not args.pilot:
        parser.error('development repair runtime requires --pilot until benchmark qualification')
    if not args.pilot and not args.expected_response:
        parser.error('formal runs require a pilot-verified --expected-response identity')
    args.project, args.output = args.project.resolve(), args.output.resolve()
    run(args)


if __name__ == '__main__':
    main()
