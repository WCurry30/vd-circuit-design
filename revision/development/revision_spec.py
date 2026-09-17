"""Versioned, deliberately bounded specification checks for revision v2."""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

from shared_spice_evaluator import (
    NodeManifest, _numeric_rows, _relative_pass, _required_canonical_subcircuits,
    _sanitize_deck, _spice_number, evaluate_deck,
)


def statements(deck: str) -> list[list[str]]:
    """Read top-level SPICE statements, joining continuation lines."""
    lines: list[str] = []
    for raw in _sanitize_deck(deck).splitlines():
        line = raw.split(';', 1)[0].strip()
        if not line or line.startswith('*'):
            continue
        if line.startswith('+'):
            if not lines:
                raise ValueError('orphan continuation')
            lines[-1] += ' ' + line[1:]
        else:
            lines.append(line)
    rows = []
    depth = 0
    for line in lines:
        tokens = line.upper().split()
        if tokens[0] == '.SUBCKT':
            depth += 1
        elif tokens[0] == '.ENDS':
            depth -= 1
        elif depth == 0 and not tokens[0].startswith('.'):
            rows.append(tokens)
        if depth < 0:
            raise ValueError('unmatched .ends')
    if depth:
        raise ValueError('unclosed subcircuit')
    return rows


def _path(rows, start, end, *, capacitors):
    graph: dict[str, set[str]] = {}
    for row in rows:
        if len(row) < 4 or row[0][0] not in ('RCL' if capacitors else 'RL'):
            continue
        a, b = row[1:3]
        if '0' in (a, b):
            continue
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    seen = {start}
    todo = [start]
    while todo:
        node = todo.pop()
        if node == end:
            return True
        for other in graph.get(node, set()) - seen:
            seen.add(other)
            todo.append(other)
    return False


def structural_checks(deck: str, constraints: dict) -> dict[str, bool]:
    rows = statements(deck)
    opamps = [row for row in rows if row[0].startswith('X') and len(row) >= 7
              and row[6] in {'LM2904', 'LM358', 'LM324', 'OPAMP'}]
    checks: dict[str, bool] = {}
    for kind in constraints.get('devices', []):
        checks['device_' + kind] = bool(opamps) if kind == 'opamp' else any(
            row[0].startswith(kind) for row in rows)
    if constraints.get('passive_rc'):
        checks['passive_rc'] = all(row[0][0] in 'RCLVI' for row in rows)
        checks['series_R_shunt_C'] = any(
            row[0].startswith('R') and set(row[1:3]) == {'IN', 'OUT'} for row in rows
        ) and any(row[0].startswith('C') and set(row[1:3]) == {'OUT', '0'} for row in rows)
    if constraints.get('input_coupling'):
        ac_rails = {'0'}
        for row in rows:
            if row[0].startswith('V') and len(row) >= 4 and '0' in row[1:3] and 'AC' not in row:
                ac_rails.update(row[1:3])
        signal_rows = [row for row in rows if len(row) >= 3
                       and not (set(row[1:3]) & ac_rails)]
        inputs = [node for amp in opamps for node in amp[1:3]]
        inputs += [row[2] for row in rows if row[0].startswith('Q') and len(row) >= 5]
        checks['input_coupling'] = any(
            _path(signal_rows, 'IN', node, capacitors=True)
            and not _path(signal_rows, 'IN', node, capacitors=False) for node in inputs)
    if constraints.get('output_coupling'):
        outputs = [amp[5] for amp in opamps]
        outputs += [row[1] for row in rows if row[0].startswith('Q') and len(row) >= 5]
        checks['output_coupling'] = any(
            _path(rows, node, 'OUT', capacitors=True)
            and not _path(rows, node, 'OUT', capacitors=False) for node in outputs)
    if constraints.get('feedback_capacitor'):
        checks['feedback_capacitor'] = any(
            row[0].startswith('C') and set(row[1:3]) == {amp[2], amp[5]}
            for row in rows for amp in opamps)
    if constraints.get('buffer'):
        checks['buffer_feedback'] = any(amp[2] == amp[5] for amp in opamps)
    if constraints.get('supply'):
        rails = {'0': 0.0}
        for row in rows:
            if row[0].startswith('V') and len(row) >= 4 and '0' in row[1:3]:
                try:
                    value = _spice_number(row[4] if row[3] == 'DC' else row[3])
                except (ValueError, IndexError):
                    continue
                rails[row[1] if row[2] == '0' else row[2]] = value if row[2] == '0' else -value
        checks['supply'] = bool(opamps) and all(
            amp[3] in rails and amp[4] in rails and rails[amp[3]] > 0
            and (rails[amp[4]] == 0 if constraints['supply'] == 'single' else rails[amp[4]] < 0)
            for amp in opamps)
    return checks


def evaluate_spec(deck: Path, case: dict, output: Path, *, ngspice='ngspice') -> dict:
    output = output.resolve()
    manifest = NodeManifest('IN', 'OUT', '0', 'VLOAD' if case['targets']['metric'] == 'load_current_a' else None)
    scalar = evaluate_deck(deck.resolve(), manifest, case['targets'], output / 'scalar', ngspice=ngspice)
    checks = {}
    error = None
    measured = scalar.measured
    try:
        text = deck.read_text()
        checks = structural_checks(text, case['constraints'])
        checks['scalar_execution'] = scalar.status == 'success'
        checks['numerical'] = scalar.passed
        if case['targets']['metric'] == 'gain_magnitude_v_per_v':
            trace = output / 'transfer.txt'
            control = (
                '\n.control\nac lin 1 1000 1000\n'
                'let transfer = v(OUT)/v(IN)\n'
                f'wrdata {trace} real(transfer) imag(transfer)\n'
                'quit\n.endc\n.end\n'
            )
            evaluated = output / 'transfer.cir'
            sanitized = _sanitize_deck(text)
            evaluated.write_text('* revision v2 transfer at 1 kHz\n' + sanitized
                                 + _required_canonical_subcircuits(sanitized) + control)
            process = subprocess.run(
                [ngspice, '-b', str(evaluated)], cwd=output, capture_output=True,
                text=True, timeout=90,
                env={key: os.environ[key] for key in ('PATH', 'LANG', 'LD_LIBRARY_PATH', 'SPICE_LIB_DIR') if key in os.environ}
                | {'HOME': str(output), 'TMPDIR': str(output)},
            )
            (output / 'transfer.log').write_text(process.stdout + process.stderr)
            checks['numerical'] = False
            if process.returncode != 0 or not trace.is_file():
                raise ValueError('transfer simulation failed')
            values = _numeric_rows(trace)[-1]
            if len(values) != 4 or not all(math.isfinite(x) for x in values):
                raise ValueError('invalid complex transfer trace')
            real, imag = values[1], values[3]
            measured = math.hypot(real, imag)
            checks['numerical'] = _relative_pass(measured, case['targets']['value'], case['targets']['tolerance'])
            polarity = case['constraints'].get('polarity')
            if polarity:
                checks['polarity'] = real * polarity > 0 and abs(imag) <= abs(real)
    except (ValueError, OSError, IndexError, subprocess.TimeoutExpired) as exc:
        checks['evaluation_completed'] = False
        error = str(exc)
    result = {'passed': bool(checks) and all(checks.values()), 'checks': checks,
              'measured': measured, 'scalar': scalar.as_dict(), 'error': error,
              'protocol': 'revision-v2-checked-constraints'}
    (output / 'specification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def build_cases(source: Path) -> list[dict]:
    original = json.loads(source.read_text())
    constraints = {
        'eda_005': {'devices': ['opamp'], 'polarity': -1, 'supply': 'dual'},
        'eda_006': {'devices': ['opamp'], 'polarity': 1, 'input_coupling': True},
        'eda_007': {'devices': ['Q'], 'polarity': -1, 'input_coupling': True, 'output_coupling': True},
        'eda_008': {'devices': ['opamp'], 'input_coupling': True},
        'eda_009': {'passive_rc': True, 'devices': ['R', 'C']},
        'eda_010': {'devices': ['opamp', 'R', 'C'], 'buffer': True},
        'eda_016': {'devices': ['D', 'R', 'C']},
        'eda_024': {'devices': ['opamp'], 'polarity': 1, 'supply': 'single', 'input_coupling': True, 'output_coupling': True},
        'eda_027': {'devices': ['opamp', 'R', 'C'], 'feedback_capacitor': True},
        'eda_037': {'devices': ['opamp', 'M', 'R', 'C']},
    }
    cases = [{**row, 'constraints': constraints[row['id']], 'split': 'development'} for row in original]
    variants = [('eda_005', 'eda_105', '-10', '-5', 5),
                ('eda_007', 'eda_107', '~-10', '~-6', 6),
                ('eda_009', 'eda_109', '~1 kHz', '~2.5 kHz', 2500),
                ('eda_016', 'eda_116', '5.1', '6.2', 6.2),
                ('eda_037', 'eda_137', '20 mA', '10 mA', 0.01)]
    by_id = {row['id']: row for row in cases}
    for parent, task, old, new, target in variants:
        row = json.loads(json.dumps(by_id[parent]))
        row.update(id=task, parent_benchmark_id=parent, split='transfer')
        row['user_requirement'] = row['user_requirement'].replace(old, new)
        row['targets'].update(value=target, source_value=target * row['constraints'].get('polarity', 1))
        row['functional_spec'].update(target=row['targets']['source_value'])
        cases.append(row)
    return cases
