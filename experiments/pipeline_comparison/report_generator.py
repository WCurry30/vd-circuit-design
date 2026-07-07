"""
Report Generator
================
Generates Markdown comparison reports with 6 simulation-grounded metrics.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List


def _fmt_pct(mean, std=None):
    if mean is None:
        return "N/A"
    m = mean * 100
    if std is not None and std > 0.001:
        return f"{m:.1f}% ± {std*100:.1f}%"
    return f"{m:.1f}%"


def _fmt_num(mean, std=None):
    if mean is None:
        return "N/A"
    if std is not None and std > 0.001:
        return f"{mean:.2f} ± {std:.2f}"
    return f"{mean:.2f}"


def _best(values, higher_is_better=True):
    """Mark the best value(s), ignoring None."""
    if not values:
        return []
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if not valid:
        return [False] * len(values)
    try:
        best_val = max(v for _, v in valid) if higher_is_better else min(v for _, v in valid)
        return [v == best_val if v is not None else False for v in values]
    except TypeError:
        return [False] * len(values)


def _bold(val, is_best):
    return f"**{val}**" if is_best else val


def generate_markdown_report(
    experiment_name: str,
    all_results: List[Dict[str, Any]],
    test_case_count: int,
    num_runs: int,
    output_dir: str = None
) -> str:
    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parents[2] / "experiment_results" / "pipeline_comparison" / "new_runs")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"{experiment_name.replace(' ', '_')}_{timestamp}.md")

    lines = []
    def w(text=""):
        lines.append(text)

    w(f"# {experiment_name} — End-to-End Pipeline Comparison")
    w()
    w(f"- **Generated**: {timestamp}")
    w(f"- **Test Cases**: {test_case_count}")
    w(f"- **Runs per Test Case**: {num_runs}")
    total_runs = len(all_results) * test_case_count * num_runs if all_results else 0
    w(f"- **Total Pipeline Runs**: {total_runs}")
    w()

    if not all_results:
        w("**No results to report.**")
        with open(report_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines))
        return report_path

    # ---- Main Metrics Table ----
    w("## End-to-End Simulation Metrics")
    w()
    w("All metrics derived from physical simulation (Ngspice) after "
      "Plan → Retrieve → Simulate → Schematic pipeline.")
    w()
    w("| Method | SPR ↑ | Target Dev ↓ | Model Match ↑ | Golden Recall ↑ | First-Pass ↑ | Schematic ↑ |")
    w("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    def _get(r, key, default=None):
        return r.get(key, {}).get("mean", default)

    spr_vals = [_get(r, "spr") for r in all_results]
    dev_vals = [_get(r, "target_deviation") for r in all_results]
    mm_vals  = [_get(r, "model_match") for r in all_results]
    gr_vals  = [_get(r, "golden_recall") for r in all_results]
    fp_vals  = [_get(r, "first_pass") for r in all_results]
    sch_vals = [_get(r, "schematic_pass") for r in all_results]

    b_spr = _best(spr_vals, True)
    b_dev = _best(dev_vals, False)
    b_mm  = _best(mm_vals, True)
    b_gr  = _best(gr_vals, True)
    b_fp  = _best(fp_vals, True)
    b_sch = _best(sch_vals, True)

    for i, r in enumerate(all_results):
        w(f"| **{r['method']}** | "
          f"{_bold(_fmt_pct(spr_vals[i]), b_spr[i])} | "
          f"{_bold(_fmt_pct(dev_vals[i]), b_dev[i])} | "
          f"{_bold(_fmt_pct(mm_vals[i]), b_mm[i])} | "
          f"{_bold(_fmt_pct(gr_vals[i]), b_gr[i])} | "
          f"{_bold(_fmt_pct(fp_vals[i]), b_fp[i])} | "
          f"{_bold(_fmt_pct(sch_vals[i]), b_sch[i])} |")

    w()
    w("> **SPR** = Physical Convergence Rate | **Target Dev** = Specification Fidelity Error")
    w("> **Model Match** = Component Translatability | **Golden Recall** = Critical Component Coverage")
    w("> **First-Pass** = Initial Translation Fidelity (passed-only) | **Schematic** = Pipeline Completion Rate")
    w()

    # ---- Metric Definitions ----
    w("## Metric Definitions")
    w()
    w("| Metric | Meaning | Simulation Stage |")
    w("| :--- | :--- | :--- |")
    w("| **SPR ↑** | Proportion of runs where Ngspice simulation converged | Ngspice pass/fail |")
    w("| **Target Dev ↓** | Relative error between simulated and target performance | Waveform analysis + specification check |")
    w("| **Model Match ↑** | Retrieved components with valid SPICE models / total planned | SPICE model injection check |")
    w("| **Golden Recall ↑** | Critical components found AND with valid models / total critical | SPICE model injection check |")
    w("| **First-Pass ↑** | Passed-on-first-attempt / total passed (conditional) | Ngspice iteration tracking |")
    w("| **Schematic ↑** | Runs producing valid KiCad .kicad_sch / total runs | Schematic generation |")
    w()

    # ---- Target Deviation per Test Case (horizontal layout) ----
    if all_results:
        first_result = all_results[0]
        per_case = first_result.get("per_case", {})
        tc_ids = sorted(per_case.keys())

        if tc_ids:
            w("## Target Deviation per Test Case")
            w()
            w("Each cell = mean of Target Deviation across runs that passed simulation (N/A = all runs failed).")
            w()
            # Table header
            w("| Method | " + " | ".join(tc_ids) + " |")
            w("| :--- |" + " :---: |" * len(tc_ids))

            for r in all_results:
                cells = [r['method']]
                for tc_id in tc_ids:
                    c = r.get("per_case", {}).get(tc_id, {})
                    dev = c.get("target_deviation", {}).get("mean")
                    cells.append(_fmt_pct(dev))
                w("| " + " | ".join(cells) + " |")
            w()

    # ---- SPR per Test Case (horizontal layout) ----
    if all_results:
        w("## SPR per Test Case")
        w()
        w("| Method | " + " | ".join(tc_ids) + " |")
        w("| :--- |" + " :---: |" * len(tc_ids))

        for r in all_results:
            cells = [r['method']]
            for tc_id in tc_ids:
                c = r.get("per_case", {}).get(tc_id, {})
                spr = c.get("spr", {}).get("mean")
                cells.append(_fmt_pct(spr))
            w("| " + " | ".join(cells) + " |")
        w()

    # ---- Model Match per Test Case (horizontal layout) ----
    if all_results:
        w("## Model Match per Test Case")
        w()
        w("| Method | " + " | ".join(tc_ids) + " |")
        w("| :--- |" + " :---: |" * len(tc_ids))

        for r in all_results:
            cells = [r['method']]
            for tc_id in tc_ids:
                c = r.get("per_case", {}).get(tc_id, {})
                mm = c.get("model_match", {}).get("mean")
                cells.append(_fmt_pct(mm))
            w("| " + " | ".join(cells) + " |")
        w()

    # ---- Golden Recall per Test Case (horizontal layout) ----
    if all_results:
        w("## Golden Recall per Test Case")
        w()
        w("| Method | " + " | ".join(tc_ids) + " |")
        w("| :--- |" + " :---: |" * len(tc_ids))

        for r in all_results:
            cells = [r['method']]
            for tc_id in tc_ids:
                c = r.get("per_case", {}).get(tc_id, {})
                gr = c.get("golden_recall", {}).get("mean")
                cells.append(_fmt_pct(gr))
            w("| " + " | ".join(cells) + " |")
        w()

    w()
    w("---")
    w(f"*Report generated {timestamp}*")

    with open(report_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    print(f"\n   Report saved: {report_path}")
    return report_path


def generate_json_results(
    experiment_name: str,
    all_results: List[Dict[str, Any]],
    output_dir: str = None
) -> str:
    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parents[2] / "experiment_results" / "pipeline_comparison")
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"{experiment_name.replace(' ', '_')}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"experiment": experiment_name, "timestamp": timestamp, "results": all_results},
                  f, indent=2, ensure_ascii=False)
    print(f"   Raw JSON saved: {json_path}")
    return json_path
