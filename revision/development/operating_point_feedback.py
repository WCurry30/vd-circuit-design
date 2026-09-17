"""Condition-specific BJT diagnostics; never changes acceptance thresholds."""

import json
import math
import os
from pathlib import Path
import re
import subprocess

from revision_spec import statements
from shared_spice_evaluator import AnalysisCondition, _condition_commands, _sanitize_deck


def opamp_operating_point(prepared, check, output, *, ngspice='ngspice'):
    """Report measured external op-amp voltages without inferring acceptance."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    text = _sanitize_deck(Path(prepared).read_text())
    devices = [r for r in statements(text) if r[0].startswith('X') and len(r) >= 7
               and r[6] == 'LM2904']
    report = {'status': 'unavailable', 'diagnostics': [], 'condition': check.get('condition', {})}
    try:
        nodes = sorted({n for amp in devices for n in amp[1:6]} - {'0'})
        if not nodes or len(devices) > 16 or any(not re.fullmatch(r'[A-Za-z0-9_+-]+', n) for n in nodes):
            raise ValueError('no supported bounded op-amp terminal set')
        commands = _condition_commands(AnalysisCondition(**check.get('condition', {})), text)
        trace = output / 'voltages.txt'
        deck = output / 'operating_point.cir'
        deck.write_text('* op-amp operating point diagnostic\n' + text + '\n.control\n'
                        + '\n'.join(commands) + '\nop\nwrdata ' + str(trace) + ' '
                        + ' '.join(f'v("{n}")' for n in nodes) + '\nquit\n.endc\n.end\n')
        process = subprocess.run([ngspice, '-b', str(deck)], cwd=output,
                                 capture_output=True, text=True, timeout=30,
                                 env={k: os.environ[k] for k in ('PATH', 'LANG', 'LD_LIBRARY_PATH', 'SPICE_LIB_DIR') if k in os.environ}
                                 | {'HOME': str(output), 'TMPDIR': str(output)})
        log = process.stdout + process.stderr
        (output / 'ngspice.log').write_text(log)
        if process.returncode or not trace.exists() or re.search(
                r'singular matrix|failed|transient op|error|no convergence', log, re.I):
            raise ValueError('operating point unavailable or required unreliable solver recovery')
        lines = trace.read_text().strip().splitlines()
        values = [float(x) for x in lines[-1].split()]
        if len(lines) != 1 or len(values) != 2 * len(nodes) or not all(math.isfinite(v) for v in values):
            raise ValueError('invalid operating point trace')
        voltages = {'0': 0.0, **dict(zip(nodes, values[1::2]))}
        observations = []
        for amp in devices:
            vp, vn, vcc, vee, vout = (voltages[n] for n in amp[1:6])
            observations.append({'device': amp[0], 'positive_input': vp, 'negative_input': vn,
                                 'positive_supply': vcc, 'negative_supply': vee, 'output': vout})
            report['diagnostics'].append(
                f'{amp[0]} DC: positive input ({amp[1]})={vp:.6g} V, '
                f'negative input ({amp[2]})={vn:.6g} V, supplies={vee:.6g} to {vcc:.6g} V, '
                f'output ({amp[5]})={vout:.6g} V. '
                'Check input common-mode range and output headroom against these measured voltages; '
                'DC bias alone does not verify the AC reference impedance or closed-loop gain.')
        report.update(status='measured', devices=observations)
    except (ValueError, OSError, IndexError, subprocess.TimeoutExpired) as error:
        report['reason'] = str(error)
        report['diagnostics'] = ['Op-amp DC diagnostic unavailable: ' + str(error)]
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def bjt_operating_point(prepared, check, output, *, ngspice='ngspice'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    text = _sanitize_deck(Path(prepared).read_text())
    devices = [r for r in statements(text) if r[0].startswith('Q') and len(r) >= 5]
    nodes = sorted({n for q in devices for n in q[1:4]})
    report = {'status': 'unavailable', 'diagnostics': [], 'condition': check.get('condition', {})}
    try:
        if not nodes or len(devices) > 16 or any(not re.fullmatch(r'[A-Za-z0-9_]+', n) for n in nodes):
            raise ValueError('no supported bounded BJT terminal set')
        commands = _condition_commands(AnalysisCondition(**check.get('condition', {})), text)
        trace = output / 'voltages.txt'
        deck = output / 'operating_point.cir'
        deck.write_text('* operating point diagnostic\n' + text + '\n.control\n'
                        + '\n'.join(commands) + '\nop\nwrdata ' + str(trace) + ' '
                        + ' '.join(f'v({n})' for n in nodes) + '\nquit\n.endc\n.end\n')
        process = subprocess.run([ngspice, '-b', str(deck)], cwd=output,
                                 capture_output=True, text=True, timeout=30,
                                 env={k: os.environ[k] for k in ('PATH', 'LANG', 'LD_LIBRARY_PATH', 'SPICE_LIB_DIR') if k in os.environ}
                                 | {'HOME': str(output), 'TMPDIR': str(output)})
        log = process.stdout + process.stderr
        (output / 'ngspice.log').write_text(log)
        if process.returncode or not trace.exists() or re.search(
                r'singular matrix|failed|transient op|error|no convergence', log, re.I):
            raise ValueError('operating point unavailable or required unreliable solver recovery; inspect supply and DC return paths')
        lines = trace.read_text().strip().splitlines()
        values = [float(x) for x in lines[-1].split()]
        if len(lines) != 1 or len(values) != 2 * len(nodes) or not all(math.isfinite(v) for v in values):
            raise ValueError('invalid operating point trace')
        voltages = dict(zip(nodes, values[1::2]))
        observations = []
        for q in devices:
            vc, vb, ve = (voltages[n] for n in q[1:4])
            observations.append({'device': q[0], 'vc': vc, 'vb': vb, 've': ve, 'vce': vc-ve})
            message = f'{q[0]} DC: Vc={vc:.6g} V, Vb={vb:.6g} V, Ve={ve:.6g} V, Vce={vc-ve:.6g} V.'
            if q[4] == '2N2222' and vc <= vb:
                message += ' Collector is not above base; inspect saturation and bias headroom before gain tuning.'
            report['diagnostics'].append(message)
        report.update(status='measured', devices=observations)
    except (ValueError, OSError, IndexError, subprocess.TimeoutExpired) as error:
        report['reason'] = str(error)
        report['diagnostics'] = ['DC operating point diagnostic unavailable: ' + str(error)]
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
