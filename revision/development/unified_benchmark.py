"""One model library, public interface and joint acceptance for every method."""

import hashlib
import json
import re
from pathlib import Path

from benchmark_structure import topology_checks, topology_diagnostics, testbench_connections, supply_diagnostics
from shared_spice_evaluator import EvaluationResult, evaluate_conditions, _sanitize_deck
from operating_point_feedback import bjt_operating_point, opamp_operating_point


ROOT = Path(__file__).resolve().parents[1] / 'benchmark'
MODEL_CONTRACT = (
    'The shared simulator provides fixed LM2904, 2N2222, LED, 1N4733A and EDA_NMOS models. '
    'Do not include, redefine or invent model/subcircuit definitions. '
    'Use Xname IN+ IN- V+ V- OUT LM2904 for each op-amp; '
    'Qname C B E 2N2222 for NPN transistors; Mname D G S B EDA_NMOS W=10u L=1u for NMOS. '
    'EDA_NMOS is a generic Level-1 device (VTO=1, KP=0.1, LAMBDA=0.01). '
    'Use Dname ANODE CATHODE LED or 1N4733A for the corresponding diode. '
    'Top-level circuit elements may be R, C, L, D, Q, M, X, V and I; '
    'behavioral and dependent sources are confined to the supplied models. '
    'Library symbol names are physical-component hints; the simulator model names above govern execution.'
)


def fixed_model_deck(text):
    sanitized = _sanitize_deck(text)
    for line in sanitized.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(('*', '+')):
            continue
        name = stripped.split()[0]
        if name.lower() in {'.model', '.subckt', '.ends'}:
            raise ValueError('use the fixed model catalog without local model/subcircuit definitions')
        if not name.startswith('.') and name[0].upper() not in 'RCLDQMXVI':
            raise ValueError(f'unsupported top-level circuit element: {name}')
    models = '\n'.join((ROOT / 'models' / name).read_text() for name in ('LM2904.lib', 'discrete.lib'))
    return '* unified fixed-model evaluation\n' + sanitized + models + '\n.end\n'


def evaluate_candidate(deck, case, output, *, ngspice='ngspice'):
    deck, output = Path(deck).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(deck.read_bytes()).hexdigest()
    target = case['checks'][0]['target']
    artifacts = {'submitted_deck': str(deck)}
    prepared_hash = None
    try:
        text = deck.read_text()
        prepared = output / 'fixed_models.cir'
        prepared.write_text(fixed_model_deck(text))
        prepared_hash = hashlib.sha256(prepared.read_bytes()).hexdigest()
        artifacts['fixed_model_deck'] = str(prepared)
        structure = topology_checks(text, case['topology'],
                                    reference_divider=case.get('reference_divider_required', False))
        structure.update(testbench_connections(text, case['checks']))
        numerical = evaluate_conditions(prepared, case['checks'], output / 'conditions', ngspice=ngspice)
        passed = numerical['passed'] and all(structure.values())
        primary = numerical['checks'][0]['result']
        failures = [name + ': required topology not found' for name, value in structure.items() if not value]
        failures.extend(f"condition {index}: " + (row['result']['detail'] or row['result']['failure_stage'] or 'acceptance failed')
                        for index, row in enumerate(numerical['checks'], 1) if not row['result']['passed'])
        diagnostics = topology_diagnostics(text, case['topology'])
        if not passed:
            diagnostics = supply_diagnostics(text) + diagnostics
            if re.search(r'^\s*X\S+\s+.*\bLM2904\b', text, re.I | re.M):
                for index, row in enumerate(numerical['checks'], 1):
                    if row['result']['passed'] and all(structure.values()):
                        continue
                    opamp_bias = opamp_operating_point(prepared, row['check'],
                                                      output / f'opamp_bias_{index:02d}', ngspice=ngspice)
                    artifacts[f'opamp_bias_{index:02d}'] = str(output / f'opamp_bias_{index:02d}' / 'report.json')
                    diagnostics.extend(f'condition {index}: {message}' for message in opamp_bias['diagnostics'])
        bias_required = case.get('operating_point_requirement')
        if bias_required not in {None, 'npn_forward_active_v1'}:
            raise ValueError('unsupported operating-point acceptance requirement')
        bias_results = []
        if (not passed or bias_required) and case['topology'] in {'ce', 'degenerated_ce', 'two_ce'}:
            for index, row in enumerate(numerical['checks'], 1):
                if row['result']['passed'] and not bias_required:
                    continue
                bias = bjt_operating_point(prepared, row['check'], output / f'bias_{index:02d}', ngspice=ngspice)
                artifacts[f'bias_{index:02d}'] = str(output / f'bias_{index:02d}' / 'report.json')
                diagnostics.extend(f'condition {index}: {message}' for message in bias['diagnostics'])
                if bias_required:
                    valid = bias['status'] == 'measured' and bool(bias.get('devices')) and all(
                        d['vc'] > d['vb'] > d['ve'] for d in bias.get('devices', []))
                    bias_results.append({'condition': index, 'passed': valid, 'report': bias})
                    passed = passed and valid
                    if not valid:
                        failures.append(f'condition {index}: forward-active OP requires reliable Vc > Vb > Ve for every NPN.')
        failures.extend(diagnostics)
        failed_execution = next((row['result'] for row in numerical['checks'] if row['result']['status'] != 'success'), None)
        joint = {'passed': passed, 'structure': structure, 'numerical': numerical,
                 'operating_point': bias_results,
                 'topology_diagnostics': diagnostics,
                 'submitted_deck_sha256': source_hash, 'fixed_model_deck_sha256': prepared_hash}
        joint_path = output / 'joint_evaluation.json'
        joint_path.write_text(json.dumps(joint, indent=2) + '\n')
        artifacts['joint_evaluation'] = str(joint_path)
        return EvaluationResult(
            'failed' if failed_execution else 'success',
            failed_execution['failure_stage'] if failed_execution else None if passed else 'specification',
            target['metric'], target['value'], target['tolerance'], primary['measured'], passed,
            source_hash, prepared_hash, artifacts, '\n'.join(failures)[:3000] or None)
    except (ValueError, OSError, KeyError, IndexError) as error:
        return EvaluationResult('failed', 'parse', target['metric'], target['value'], target['tolerance'],
                                None, False, source_hash, prepared_hash, artifacts, str(error))
