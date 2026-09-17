"""Recompute the complete final study from preserved records, without API calls."""
import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def interval(values):
    rng = random.Random(20260904)
    samples = sorted(sum(rng.choices(values, k=len(values))) / len(values)
                     for _ in range(10000))
    return samples[249], samples[9749]


def analyze(package):
    index = list(csv.DictReader((package / 'trial_index.csv').open(encoding='utf-8')))
    cases = json.loads((ROOT / 'revision/benchmark/synthesis_20.json').read_text(encoding='utf-8'))['cases']
    task_ids = {c['id'] for c in cases}
    expected = {(m, t, str(r), a) for m in ['v4', 'v32', 'gpt4o', 'qwen36', 'gpt55', 'qwen38']
                for t in task_ids for r in [1, 2, 3]
                for a in (['full', 'direct', 'analogcoder', 'spicepilot'] +
                          (['no_preparation', 'no_grounding', 'no_family_prompts',
                            'no_cleanup', 'equal_call'] if m == 'v4' else []))}
    slots = [(r['model'], r['task'], r['repeat'], r['arm']) for r in index]
    if len(slots) != 1740 or len(set(slots)) != 1740 or set(slots) != expected:
        raise ValueError('Final allocation is incomplete or duplicated')
    trials, attempts, calls = [], [], []
    grouped = defaultdict(list)
    for row in index:
        path = package / row['record']
        data = json.loads(path.read_text(encoding='utf-8'))
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['record_sha256']:
            raise ValueError(f'Record differs from retained source: {path}')
        identity = dict(model=data['model'], task=data['task_id'], repeat=data['repeat'], arm=data['arm'])
        if tuple(str(identity[k]) for k in ['model', 'task', 'repeat', 'arm']) != (
                row['model'], row['task'], row['repeat'], row['arm']):
            raise ValueError(f'Record allocation mismatch: {path}')
        candidate_rows = data.get('attempts', [])
        selected = next((a for a in candidate_rows if a['attempt'] == data.get('selected_attempt')), None)
        terminal = selected or (candidate_rows[-1] if candidate_rows else {})
        evaluation = terminal.get('evaluation') or {}
        if bool(data['passed']) != any((a.get('evaluation') or {}).get('passed', False) for a in candidate_rows):
            raise ValueError(f'Attempt/record acceptance mismatch: {path}')
        for candidate in candidate_rows:
            ev = candidate.get('evaluation') or {}
            if candidate.get('deck') and not (path.parent / candidate['deck']).is_file():
                raise ValueError(f'Missing submitted deck: {path}')
            attempts.append({**identity, 'attempt': candidate['attempt'], 'passed': ev.get('passed', False),
                             'failure_stage': ev.get('failure_stage'), 'detail': ev.get('detail'),
                             'deck': candidate.get('deck'), 'record': row['record']})
        gen = data.get('generation_usage', [])
        plan = data.get('planning_usage', [])
        measured, target = evaluation.get('measured'), evaluation.get('target')
        finite = isinstance(measured, (int, float)) and math.isfinite(measured)
        deviation = abs(measured - target) / abs(target) if finite and target else None
        item = {**identity, 'passed': data['passed'], 'source': row['source'],
                'exposure': data.get('exposure'), 'generation_calls': data['generation_calls'],
                'generation_tokens_known': sum(u.get('total_tokens', 0) or 0 for u in gen),
                'preparation_calls_required': len(plan),
                'preparation_tokens_required': sum(u.get('total_tokens', 0) or 0 for u in plan),
                'attempts': len(candidate_rows), 'first_attempt_pass': bool(candidate_rows and
                    (candidate_rows[0].get('evaluation') or {}).get('passed', False)),
                'failure_stage': '' if data['passed'] else evaluation.get('failure_stage') or 'generation',
                'finite_measurement': finite, 'relative_deviation': deviation,
                'numerical_loss': min(deviation, 1) if deviation is not None else 1,
                'simulator_logs_retained': len(list(path.parent.rglob('*.log'))),
                'record': row['record']}
        trials.append(item)
        grouped[(data['model'], data['arm'])].append(item)
    # Physical call files include duplicated preparation contexts. IDs mark duplication,
    # not additional provider spending. Error files have no inferred token amount.
    seen = set()
    for request in sorted((package / 'records').rglob('request.json')):
        req = json.loads(request.read_text(encoding='utf-8'))
        response = request.with_name('response.json')
        rsp = json.loads(response.read_text(encoding='utf-8')) if response.exists() else {}
        usage = rsp.get('usage') or {}
        rid = rsp.get('id')
        duplicate = bool(rid and rid in seen)
        if rid:
            seen.add(rid)
        calls.append({'request': str(request.relative_to(package)),
                      'kind': 'preparation' if 'planning_calls' in request.parts else 'generation',
                      'requested_model': req.get('model'), 'response_model': rsp.get('model'),
                      'response_id': rid, 'provider_created': rsp.get('created'),
                      'has_response': response.exists(), 'duplicate_response_id': duplicate,
                      'tokens': usage.get('total_tokens'),
                      'recovery_sidecars': len(list(request.parent.glob('recovery*.json'))),
                      'error_files': len(list(request.parent.glob('*error*')))})
    summary, task_rows, pairs = [], [], []
    for (model, arm), rows in sorted(grouped.items()):
        by_task = defaultdict(list)
        for row in rows:
            by_task[row['task']].append(row)
        rates = []
        for task, rs in sorted(by_task.items()):
            rate = sum(x['passed'] for x in rs) / len(rs)
            rates.append(rate)
            task_rows.append({'model': model, 'arm': arm, 'task': task, 'passed': sum(x['passed'] for x in rs),
                              'trials': len(rs), 'rate': rate})
        low, high = interval(rates)
        summary.append({'model': model, 'arm': arm, 'passed': sum(x['passed'] for x in rows),
                        'trials': len(rows), 'rate': sum(rates) / len(rates),
                        'task_ci_low': low, 'task_ci_high': high,
                        'generation_calls': sum(x['generation_calls'] for x in rows),
                        'generation_tokens_known': sum(x['generation_tokens_known'] for x in rows),
                        'preparation_tokens_per_trial_sum': sum(x['preparation_tokens_required'] for x in rows),
                        'numerical_loss_mean': sum(x['numerical_loss'] for x in rows) / len(rows),
                        'failure_stages': dict(Counter(x['failure_stage'] for x in rows if not x['passed']))})
        if arm != 'full':
            full = {(x['task'], x['repeat']): x for x in grouped[(model, 'full')]}
            for row in rows:
                f = full[(row['task'], row['repeat'])]
                pairs.append({'model': model, 'control': arm, 'task': row['task'], 'repeat': row['repeat'],
                              'full_pass': f['passed'], 'control_pass': row['passed'],
                              'difference': int(f['passed']) - int(row['passed'])})
    return trials, attempts, calls, summary, task_rows, pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'experiment_results/final')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    trials, attempts, calls, summary, tasks, pairs = analyze(args.package)
    if not args.verify_only:
        out = args.package / 'statistics'
        out.mkdir(exist_ok=True)
        for name, rows in [('trials', trials), ('attempts', attempts), ('calls', calls),
                           ('task_results', tasks), ('paired_outcomes', pairs)]:
            write_csv(out / (name + '.csv'), rows)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        strata = []
        for model, arm, exposure in sorted({(x['model'], x['arm'], x['exposure']) for x in trials}):
            rs = [x for x in trials if (x['model'], x['arm'], x['exposure']) == (model, arm, exposure)]
            strata.append({'model': model, 'arm': arm, 'exposure': exposure,
                           'trials': len(rs), 'passed': sum(x['passed'] for x in rs)})
        write_csv(out / 'exposure_strata.csv', strata)
        resource = {
            'generation_by_origin': {
                origin: {'trials': len(rs), 'calls': sum(x['generation_calls'] for x in rs),
                         'known_tokens': sum(x['generation_tokens_known'] for x in rs)}
                for origin, rs in (
                    ('new_final_runs', [x for x in trials if x['source'].startswith('routing-fix')]),
                    ('reused_baselines', [x for x in trials if not x['source'].startswith('routing-fix')]))},
            'unique_preparation_responses': sum(x['kind'] == 'preparation' and x['has_response'] and
                                               not x['duplicate_response_id'] for x in calls),
            'known_unique_preparation_tokens': sum(x['tokens'] or 0 for x in calls
                if x['kind'] == 'preparation' and not x['duplicate_response_id']),
            'response_files_with_unknown_tokens': sum(x['has_response'] and x['tokens'] is None for x in calls),
            'requests_without_response': sum(not x['has_response'] for x in calls),
            'retained_error_files': sum(x['error_files'] for x in calls),
            'retained_recovery_sidecars': sum(x['recovery_sidecars'] for x in calls),
            'retained_simulator_logs': sum(x['simulator_logs_retained'] for x in trials),
            'transport_failure_tokens': None,
            'historical_total_simulator_invocations': None,
            'preparation_policy': 'Required context usage is distinct from provider spending; copied responses are deduplicated by ID.',
        }
        (out / 'resources.json').write_text(json.dumps(resource, indent=2) + '\n')
        lines = ['# Final shared-evaluator study', '',
                 'Complete denominator: 960 main-comparison trials, 240 ablation trials, and 60 Equal-call trials.',
                 '540 newly generated trials and 720 reused baseline trials retain separate protocol identities.', '',
                 '|Model|Method|Passes|Rate|95% task-cluster interval|Generation calls|Known generation tokens|',
                 '|---|---|---:|---:|---:|---:|---:|']
        for s in summary:
            lines.append(f"|{s['model']}|{s['arm']}|{s['passed']}/{s['trials']}|{s['rate']:.1%}|"
                         f"{s['task_ci_low']:.1%}–{s['task_ci_high']:.1%}|{s['generation_calls']}|{s['generation_tokens_known']}|")
        lines += ['', 'All failures remain in the denominator. Intervals resample 20 tasks with all three repeats, 10,000 times, seed 20260904.',
                  'Preparation usage in trials is the context required by that method, not new API spending. Shared preparation response IDs are counted once in physical usage accounting.',
                  'calls.csv preserves returned model IDs, timestamps, duplicated responses, missing usage and recovery sidecars. Unknown usage is not assigned zero tokens.',
                  'simulator_logs_retained counts retained .log files, not a reconstructed historical invocation total. Recovery can leave historical invocation counts unknown.',
                  'All 20 tasks were exposed before the final correction. V4 requested deepseek-v4-flash and returned deepseek-flash; supplier-side reconciliation remains unavailable.',
                  'Component studies use their separate historical datasets and protocols. They are not pooled into this denominator.']
        (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'trials': len(trials), 'attempts': len(attempts), 'request_files': len(calls),
                      'settings': len(summary), 'passed': sum(x['passed'] for x in trials)}))


if __name__ == '__main__':
    main()
