"""Numerical qualification of proposed references, before any method generation."""

import argparse
import hashlib
import json
from pathlib import Path

from shared_spice_evaluator import evaluate_conditions, _sanitize_deck
from benchmark_structure import topology_checks


ROOT = Path(__file__).resolve().parents[1]

TOPOLOGIES = dict(zip(
    [f"eda_{index}" for index in range(201, 211)],
    ['loaded_inverter', 'difference_amplifier', 'degenerated_ce', 'two_ce',
     'two_buffered_rc', 'sallen_key', 'loaded_zener', 'buffered_zener',
     'opamp_nmos_led', 'two_bjt_led']))
TOPOLOGIES.update(dict(zip(
    ['eda_005', 'eda_006', 'eda_007', 'eda_008', 'eda_009', 'eda_010', 'eda_016', 'eda_024', 'eda_027', 'eda_037'],
    ['inverter', 'noninverting_ac', 'ce', 'mic_preamp', 'passive_rc',
     'buffered_rc', 'zener', 'single_supply_audio', 'active_rc', 'opamp_nmos_led'])))

NEGATIVES = {
    'eda_005': [('XU1 0 NM', 'XU1 IN NM'), ('RIN IN NM 10k', 'RIN NM 0 10k'), ('RF OUT NM 100k', 'RF OUT NM 90k')],
    'eda_006': [('CIN IN NP 10u', 'RBYPASS IN NP 1m')],
    'eda_007': [('COUT C OUT 10u', 'RBYPASS C OUT 1m')],
    'eda_008': [('RMIC VCC IN 2.2k', '* missing microphone bias')],
    'eda_009': [('R1 IN OUT 15.915k', 'R1 IN OUT 159.15k')],
    'eda_010': [('XU1 NP OUT VCC VEE OUT LM2904', 'EBUF OUT 0 NP 0 1')],
    'eda_016': [('DZ 0 OUT 1N4733A', 'DZ OUT 0 1N4733A')],
    'eda_024': [('COUT AOUT OUT 10u', 'RBYPASS AOUT OUT 1m')],
    'eda_027': [('CF OUT NM 10n', 'CF OUT 0 10n')],
    'eda_037': [('M1 OUT GATE SENSE SENSE EDA_NMOS W=10u L=1u', 'Q1 OUT GATE SENSE 2N2222')],
    'eda_201': [('XU1 0 NM', 'XU1 IN NM'), ('RIN IN NM 10k', 'RIN NM 0 10k'), ('RF OUT NM 50k', 'RF OUT NM 40k')],
    'eda_202': [('R4 NP 0 50k', 'R4 NP 0 100k')],
    'eda_203': [('RE E 0 360', 'RE E 0 360\nCE E 0 100u')],
    'eda_204': [('Q1 C1 B1 E1 2N2222', '* missing first transistor')],
    'eda_205': [('XU1 N1 BUF VCC VEE BUF LM2904', 'EBUF BUF 0 N1 0 1')],
    'eda_206': [('C1 N1 OUT 20n', 'C1 N1 0 20n')],
    'eda_207': [('RLOAD OUT 0 1k', '* missing load')],
    'eda_208': [('Q1 VCC B OUT 2N2222', 'Q1 VCC OUT B 2N2222')],
    'eda_209': [('M1 OUT GATE SENSE SENSE EDA_NMOS W=10u L=1u', 'Q1 OUT GATE SENSE 2N2222')],
    'eda_210': [('Q2 B SENSE 0 2N2222', '* missing feedback transistor')],
}


def check(metric, value, tolerance=.1, *, nodes=None, condition=None, bounds=None):
    target = {"metric": metric, "value": value, "tolerance": tolerance}
    if bounds:
        target.update(minimum=bounds[0], maximum=bounds[1])
    return {"nodes": nodes or {"input": "VCC" if metric == "dc_voltage_v" else "IN", "output": "OUT"},
            "target": target, "condition": condition or {}}


def proposed_checks():
    current = {"input": "VCC", "output": "OUT", "load_element": "VLOAD"}
    differential = {"input": "INP", "input_negative": "INN", "output": "OUT"}
    return {
        'eda_005': [check('gain_real_v_per_v', -10, .2)],
        'eda_006': [check('gain_real_v_per_v', 11, .2)],
        'eda_007': [check('gain_real_v_per_v', -10, .3)],
        'eda_008': [check('gain_real_v_per_v', 100, .3)],
        'eda_009': [check('cutoff_freq_hz', 1000, .2)],
        'eda_010': [check('cutoff_freq_hz', 1000, .2)],
        'eda_016': [check('dc_voltage_v', 5.1, .15)],
        'eda_024': [check('gain_real_v_per_v', 11, .3)],
        'eda_027': [check('cutoff_freq_hz', 1000, .2)],
        'eda_037': [check('load_current_a', .02, .3, nodes=current)],
        "eda_201": [check("gain_real_v_per_v", -5, condition={
            "dc_sources": {"VCC": 5, "VEE": -5}, "resistances": {"RLOAD": 2000}})],
        "eda_202": [
            check("gain_real_v_per_v", 5, nodes=differential,
                  condition={"dc_sources": {"VCC": 12, "VEE": -12},
                             "ac_sources": {"VIP": [.5, 0], "VIN": [.5, 180]}}),
            check("output_ac_magnitude_v", 0, nodes=differential, bounds=(0, .01),
                  condition={"dc_sources": {"VCC": 12, "VEE": -12},
                             "ac_sources": {"VIP": [1, 0], "VIN": [1, 0]}})],
        "eda_203": [check("gain_real_v_per_v", -5, .2,
                          condition={"dc_sources": {"VDD": 12}, "resistances": {"RLOAD": 4700}})],
        "eda_204": [check("gain_real_v_per_v", 25, .2,
                          condition={"dc_sources": {"VDD": 12}, "resistances": {"RLOAD": 10000}})],
        "eda_205": [check("cutoff_freq_hz", 500, .15,
                          condition={"dc_sources": {"VCC": 12, "VEE": -12}}),
                    check("gain_at_frequency_v_per_v", 1, .05, condition={
                        "frequency_hz": 10, "dc_sources": {"VCC": 12, "VEE": -12}})],
        "eda_206": [check("cutoff_freq_hz", 2000, .15,
                          condition={"dc_sources": {"VCC": 12, "VEE": -12}}),
                    check("gain_at_frequency_v_per_v", 1, .05, condition={
                        "frequency_hz": 10, "dc_sources": {"VCC": 12, "VEE": -12}}),
                    check("gain_at_frequency_v_per_v", 1, bounds=(.94, 1.06),
                          condition={"frequency_hz": 500, "dc_sources": {"VCC": 12, "VEE": -12}})],
        "eda_207": [check("dc_voltage_v", 5.1, .1, condition={
            "dc_sources": {"VDD": supply}, "resistances": {"RLOAD": 1000}}) for supply in (9, 12)],
        "eda_208": [check("dc_voltage_v", 4.4, .1, condition={
            "dc_sources": {"VDD": 12}, "resistances": {"RLOAD": load}}) for load in (470, 1000)],
        "eda_209": [check("load_current_a", .01, .1, nodes=current,
                          condition={"dc_sources": {"VDD": 5}})],
        "eda_210": [check("load_current_a", .006, .15, nodes=current,
                          condition={"dc_sources": {"VDD": supply}}) for supply in (9, 12)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model_paths = [ROOT / "benchmark/models" / name for name in ("LM2904.lib", "discrete.lib")]
    models = "\n".join(path.read_text() for path in model_paths)
    report = {"scope": "reference numerical qualification only; not method performance",
              "model_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in model_paths},
              "tasks": {}}
    for task_id, checks in proposed_checks().items():
        source = ROOT / f"benchmark/references/{task_id}.cir"
        task_dir = output / task_id
        task_dir.mkdir()
        assembled = task_dir / "self_contained.cir"
        assembled.write_text(_sanitize_deck(source.read_text()) + "\n" + models + "\n.end\n")
        result = evaluate_conditions(assembled, checks, task_dir / "evaluation")
        structure = topology_checks(assembled.read_text(), TOPOLOGIES[task_id])
        negative_text = source.read_text()
        for old, new in NEGATIVES[task_id]:
            if negative_text.count(old) != 1:
                raise ValueError(f"negative fixture edit is not unique: {task_id}")
            negative_text = negative_text.replace(old, new)
        negative = task_dir / 'negative.cir'
        negative.write_text(_sanitize_deck(negative_text) + '\n' + models + '\n.end\n')
        negative_result = evaluate_conditions(negative, checks, task_dir / 'negative_evaluation')
        negative_structure = topology_checks(negative.read_text(), TOPOLOGIES[task_id])
        negative_passed = negative_result['passed'] and all(negative_structure.values())
        passed = result['passed'] and all(structure.values()) and not negative_passed
        report["tasks"][task_id] = {"passed": passed, "checks": result["checks"],
                                    "structure": structure,
                                    "negative": {"passed": negative_passed, 'structure': negative_structure,
                                                 'numerical_passed': negative_result['passed']},
                                    "reference_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        print(json.dumps({"task": task_id, "qualified": passed, "structure": structure,
                          "negative_rejected": not negative_passed,
                          "measurements": [row["result"]["measured"] for row in result["checks"]],
                          "errors": [row["result"]["detail"] for row in result["checks"] if not row["result"]["passed"]]}))
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
