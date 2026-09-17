"""Audited pilot runner for the unified benchmark; no implicit formal promotion."""

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
from repair_history import repair_feedback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'project', 'env', 'output', 'analogcoder', 'spicepilot'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--model', choices=('v4', 'v32', 'qwen36', 'gpt4o'), required=True)
    parser.add_argument('--expected-response', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--sizing-tool', action='store_true')
    parser.add_argument('--formal-manifest', type=Path)
    parser.add_argument('--repeat', type=int, default=1, choices=(1, 2, 3))
    parser.add_argument('--arms', nargs='+', default=['full', 'direct', 'analogcoder', 'spicepilot'],
                        choices=('full', 'direct', 'analogcoder', 'spicepilot', 'equal_call',
                                 'no_preparation', 'no_grounding', 'no_family_prompts', 'no_cleanup', 'no_sizing_tool'))
    args = parser.parse_args()
    formal = None
    if args.formal_manifest:
        from formal_protocol import validate_allocation
        formal = json.loads(args.formal_manifest.read_text())
        validate_allocation(formal, args.model, args.task, args.repeat, args.arms)
        if args.sizing_tool:
            parser.error('the frozen formal protocol excludes sizing')
    if 'no_sizing_tool' in args.arms and not args.sizing_tool:
        parser.error('no_sizing_tool requires the paired sizing-tool protocol')
    sys.path.append(str(args.source.resolve()))
    from alignment_config import MODELS, provider_blocks, digest
    from alignment_runner import ResponseLedger, api_usage, save
    from unified_benchmark import ROOT, MODEL_CONTRACT, evaluate_candidate
    provider = provider_blocks(args.env)[MODELS[args.model]]
    os.environ.update(EDA_API_KEY=provider['KEY'], OPENAI_API_KEY=provider['KEY'],
                      EDA_BASE_URL=provider['URL'], OPENAI_BASE_URL=provider['URL'],
                      EDA_MODEL_NAME=provider['MODEL'], EDA_API_MAX_RETRIES='0',
                      EDA_DISABLE_THINKING='1' if args.model in {'v4', 'qwen36'} else '0',
                      CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    ledger = ResponseLedger(args.expected_response, disable_qwen_thinking=args.model == 'qwen36')
    ledger.install()
    from tcad_supplement.legacy import LegacyEDALastAdapter, _normalize_circuit_type
    from revision_preparation import install_contract
    from generation_adapters import (OpenAICompatibleClient, DirectSpiceBaseline,
                                     AnalogCoderSharedAdapter, SpicePilotPromptAdapter)
    dataset = json.loads((ROOT / 'synthesis_20.json').read_text())
    case = next(row for row in dataset['cases'] if row['id'] == args.task)
    if formal:
        case = {**case, 'interface': case['interface'] + '\nPublic topology acceptance scope:\n'
                + formal['public_topology_scope'][case['topology']]}
    if not formal and case['exposure'] != 'development':
        raise ValueError('development pilot excludes new-task model generation')
    if 'equal_call' in args.arms and 'full' not in args.arms:
        raise ValueError('equal-call requires its paired Full arm')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for prefix, root in [('development', Path(__file__).parent), ('runtime', args.project / 'framework')]:
        for path in sorted(root.rglob('*.py')):
            hashes[prefix + '/' + str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if formal:
        for path in sorted(args.source.rglob('*.py')):
            hashes['adapter/' + str(path.relative_to(args.source))] = hashlib.sha256(path.read_bytes()).hexdigest()
    protocol = {'version': 'unified20-pilot-v1', 'dataset_sha256': digest(dataset),
                'framework_feedback': 'two-attempt-history-v1; equal_call receives no repair feedback',
                'sizing_tool': args.sizing_tool, 'synthesis_budget_unit': 'API responses including tool requests',
                'source_hashes': hashes, 'temperature': .3, 'synthesis_cap': 3,
                'selection': 'first joint acceptance', 'status': 'development pilot',
                'arms': sorted(args.arms), 'model_contract': MODEL_CONTRACT,
                'baseline_template_hashes': {
                    'analogcoder': hashlib.sha256((args.analogcoder / 'prompt_template.txt').read_bytes()).hexdigest(),
                    'spicepilot': hashlib.sha256((args.spicepilot / 'Pilot_prompt.md').read_bytes()).hexdigest()}}
    if formal:
        from formal_protocol import validate_inputs
        validate_inputs(formal, dataset, hashes, config_model=provider['MODEL'],
                        expected_model=args.expected_response, model=args.model,
                        endpoint_sha256=hashlib.sha256(provider['URL'].encode()).hexdigest(),
                        templates=protocol['baseline_template_hashes'])
        protocol.update(version=formal['version'], status=formal.get('study_status', 'formal'),
                        arms=formal['all_arms'], formal_manifest_sha256=digest(formal),
                        allocation=formal['allocation'], preparation_policy=formal['preparation_policy'])
    with (output / '.protocol.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        frozen = output / 'protocol.json'
        if frozen.exists() and json.loads(frozen.read_text()) != protocol:
            raise ValueError('pilot protocol changed; use a new output directory')
        save(frozen, protocol)
    unit = output / 'units' / args.model / args.task / str(args.repeat)
    unit.mkdir(parents=True, exist_ok=True)
    lock = (unit / '.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = {'requested_model': provider['MODEL'], 'expected_response_model': args.expected_response,
              'endpoint_sha256': hashlib.sha256(provider['URL'].encode()).hexdigest(),
              'thinking_disabled': args.model in {'v4', 'qwen36'}}
    config_path = unit / 'provider.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError('provider changed within a pilot unit')
    save(config_path, config)
    seed = (formal['seed_base'] if formal else 92000) + int(args.task.split('_')[1]) * 10 + args.repeat
    target = case['targets']
    metric = target['metric']
    gain_metric = 'max_gain_db' if 'common-emitter' in case['user_requirement'].lower() else 'midband_gain_db'
    legacy_target = ({'metric': gain_metric, 'value': 20 * math.log10(abs(target['value']))}
                     if 'gain' in metric else {'metric': 'cutoff_freq_hz', 'value': target['value']}
                     if 'cutoff' in metric else {'metric': 'led_current_ma', 'value': target['value'] * 1000}
                     if 'current' in metric else {'metric': 'v_out_avg_v', 'value': target['value']})
    legacy = LegacyEDALastAdapter(args.project)
    install_contract(legacy)
    preparation_file = unit / 'preparation.json'
    if formal and formal.get('version') == 'unified20-routing-fix-v1':
        prep_key = f'{args.model}/{args.task}/{args.repeat}'
        expected_prep = formal['reused_preparation_sha256'][prep_key]
        if not preparation_file.exists() or hashlib.sha256(preparation_file.read_bytes()).hexdigest() != expected_prep:
            raise ValueError('routing-fix preparation differs from the frozen reused artifact')
    if not preparation_file.exists():
        with ledger.scope(unit / 'planning_calls'):
            try:
                plan, retrieved = legacy.prepare(case['user_requirement'], target=legacy_target, seed=seed)
                preparation = {'plan': plan, 'retrieved': retrieved, 'error': None}
            except Exception as error:
                preparation = {'plan': None, 'retrieved': None, 'error': type(error).__name__}
        preparation['usage'] = api_usage(unit / 'planning_calls')[:ledger.index]
        save(preparation_file, preparation)
    preparation = json.loads(preparation_file.read_text())
    client = OpenAICompatibleClient(provider['MODEL'], provider['KEY'], provider['URL'],
                                   thinking_disabled=args.model in {'v4', 'qwen36'})
    kwargs = {'temperature': .3, 'max_calls': 3, 'ngspice': 'ngspice', 'timeout_seconds': 90,
              'evaluator': lambda source, folder, **options: evaluate_candidate(source, case, folder, **options)}
    adapters = {'direct': DirectSpiceBaseline(client, **kwargs),
                'analogcoder': AnalogCoderSharedAdapter(client, analogcoder_root=args.analogcoder, **kwargs),
                'spicepilot': SpicePilotPromptAdapter(client, spicepilot_root=args.spicepilot, **kwargs)}
    arms = [arm for arm in args.arms if arm != 'equal_call']
    random.Random(seed).shuffle(arms)
    if 'equal_call' in args.arms:
        arms.append('equal_call')
    for arm in arms:
        workspace = unit / arm
        workspace.mkdir(exist_ok=True)
        record_path = workspace / 'record.json'
        if record_path.exists():
            continue
        uses_preparation = arm not in adapters and arm != 'no_preparation'
        record = {'model': args.model, 'task_id': args.task, 'repeat': args.repeat, 'arm': arm,
                  'pilot': not bool(formal), 'protocol_sha256': digest(protocol), 'provider_sha256': digest(config),
                  'preparation_sha256': digest(preparation), 'attempts': [], 'passed': False,
                  'planning_usage': preparation['usage'] if uses_preparation else []}
        if formal:
            record.update(formal_manifest_sha256=digest(formal), public_case_sha256=digest(case),
                          exposure=case['exposure'])
        with ledger.scope(workspace / 'calls'):
            if arm in adapters:
                for candidate in adapters[arm].run(case, workspace, seed=seed):
                    record['attempts'].append({'attempt': candidate.attempt,
                        'deck': str(Path(candidate.submitted_deck).relative_to(workspace)) if candidate.submitted_deck else None,
                        'evaluation': candidate.evaluation.as_dict() if candidate.evaluation else None,
                        'failure_stage': candidate.failure_stage, 'error': candidate.error})
            elif uses_preparation and preparation['error']:
                record['preparation_error'] = preparation['error']
            else:
                route = _normalize_circuit_type(case['user_requirement'], 'amplifier')
                plan = (legacy.direct_plan(case['user_requirement'], target=legacy_target, circuit_type=route)
                        if arm == 'no_preparation' else dict(preparation['plan']))
                plan['_benchmark_targets'] = legacy_target
                plan['elaborated_requirement'] += '\nShared public interface:\n' + case['interface']
                plan['model_contract'] = MODEL_CONTRACT
                expert = legacy.orchestrator_module.ExpertFactory.get_expert(plan['circuit_type'])
                expert.set_targets(legacy_target)
                if arm == 'no_family_prompts':
                    if formal:
                        from formal_protocol import generic_prompts
                        expert.get_netlist_prompts = generic_prompts
                    else:
                        generic = legacy.orchestrator_module.ExpertFactory.get_expert('generic_circuit')
                        expert.get_netlist_prompts = generic.get_netlist_prompts
                engine = legacy.netlist_module.NetlistEngine()
                engine.cleanup_enabled = arm != 'no_cleanup'
                engine.sizing_enabled = args.sizing_tool and arm not in {'no_sizing_tool', 'equal_call'}
                engine.sizing_events = []
                retrieved = {} if arm in {'no_preparation', 'no_grounding'} else preparation['retrieved']
                save(workspace / 'retrieved.json', retrieved)
                cap = 3 if arm != 'equal_call' else json.loads((unit / 'full/record.json').read_text())['generation_calls']
                previous = feedback = None
                history = []
                for attempt in range(1, cap + 1):
                    if ledger.index >= cap:
                        break
                    engine.remaining_calls = cap - ledger.index
                    root = workspace / f'attempt_{attempt}'
                    root.mkdir(exist_ok=True)
                    try:
                        code = engine.generate_spice(plan, expert, iteration=attempt, previous_spice=previous,
                            feedback=feedback, retrieved_path=str(workspace / 'retrieved.json'),
                            temperature=.3, seed=seed + attempt - 1)
                        save(workspace / 'component_bindings.json', engine.last_component_bindings)
                        deck = root / 'submitted.cir'
                        deck.write_text(code)
                        outcome = evaluate_candidate(deck, case, root / 'evaluation')
                        save(root / 'common_evaluation.json', outcome.as_dict())
                        record['attempts'].append({'attempt': attempt, 'deck': str(deck.relative_to(workspace)),
                                                   'evaluation': outcome.as_dict()})
                        save(workspace / 'checkpoint.json', record)
                        if arm != 'equal_call':
                            if outcome.passed:
                                break
                            history.append({'attempt': attempt, 'deck': code, 'feedback': outcome.detail})
                            previous, feedback = code, repair_feedback(history)
                    except (ValueError, TypeError, AttributeError) as error:
                        detail = (type(error).__name__ + ': ' + str(error))[:1000]
                        record['attempts'].append({'attempt': attempt, 'deck': None, 'evaluation': None,
                                                   'failure_stage': 'generation_parsing', 'error': type(error).__name__,
                                                   'detail': detail})
                        if arm != 'equal_call':
                            previous = engine.last_response
                            history.append({'attempt': attempt, 'deck': previous,
                                            'feedback': 'Previous generation did not return a usable deck: ' + detail})
                            feedback = repair_feedback(history)
                        save(workspace / 'checkpoint.json', record)
                    finally:
                        save(workspace / 'sizing_events.json', engine.sizing_events)
        record['generation_usage'] = api_usage(workspace / 'calls')[:ledger.index]
        record['generation_calls'] = len(record['generation_usage'])
        successes = [row for row in record['attempts'] if (row['evaluation'] or {}).get('passed')]
        record['passed'] = bool(successes)
        record['selected_attempt'] = successes[0]['attempt'] if successes else None
        save(record_path, record)
        print(json.dumps({key: record[key] for key in ('model', 'task_id', 'arm', 'passed', 'generation_calls')}), flush=True)


if __name__ == '__main__':
    main()
