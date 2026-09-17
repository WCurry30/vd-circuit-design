"""
Six Simulation-Grounded Evaluation Metrics
==========================================
All metrics are derived from the simulation pipeline, reflecting
end-to-end quality through physical verification (Ngspice).

1. SPR — Physical Convergence Rate
2. Target Deviation — Specification Fidelity Error
3. Model Match Rate — Component Translatability
4. Golden Recall — Critical Component Coverage
5. First-Pass Rate — Initial Translation Fidelity
6. Schematic Pass — Pipeline Completion Rate
"""

import statistics
from typing import List, Dict, Any, Optional


# ================= Target Deviation =================

def calculate_target_deviation(actual_metrics: Optional[Dict],
                               targets: Optional[Dict]) -> Optional[float]:
    """|actual - target| / target. None if not computable."""
    if not targets or not actual_metrics:
        return None
    metric_name = targets.get("metric")
    target_value = targets.get("value")
    if not metric_name or target_value is None or target_value == 0:
        return None
    actual = actual_metrics.get(metric_name)
    if actual is None:
        return None
    return abs(actual - target_value) / target_value


# ================= Aggregation =================

def aggregate_metrics(values: List[float]) -> Dict[str, Optional[float]]:
    """Mean and std of a list. Returns None for empty lists."""
    if not values:
        return {"mean": None, "std": None}
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean_val, 4), "std": round(std_val, 4)}


# ================= Per-Test-Case Metrics =================

def compute_per_case_metrics(runs: List[Dict], tc_targets: Optional[Dict],
                             golden_components: List[str]) -> Dict[str, Any]:
    """
    Compute per-test-case metrics from a list of runs for the same test case.

    Each run is a dict from pipeline_runner.run() containing:
      - retrieval.model_match: {uid: bool}
      - simulation.passed, simulation.first_pass, simulation.iterations,
        simulation.actual_metrics
      - schematic.generated
    """
    spr_vals = []
    dev_vals = []
    fp_vals = []
    sch_vals = []
    model_match_total = []  # per-run proportion
    golden_recall_vals = [] # per-run proportion

    for r in runs:
        sim = r.get("simulation", {})
        sch = r.get("schematic", {})
        ret = r.get("retrieval", {})

        # 1. SPR
        passed = sim.get("passed", False)
        spr_vals.append(1 if passed else 0)

        # 2. Target Deviation (only when simulation passed & metrics available)
        if passed:
            actual = sim.get("actual_metrics", {})
            dev = calculate_target_deviation(actual, tc_targets)
            if dev is not None:
                dev_vals.append(dev)
            fp_vals.append(1 if sim.get("first_pass", False) else 0)

        # 5. First-Pass: tracked per passed run (conditional)

        # 6. Schematic
        sch_vals.append(1 if sch.get("generated", False) else 0)

        # 3. Model Match Rate (independent of simulation success)
        model_match = ret.get("model_match", {})
        if model_match:
            total = len(model_match)
            matched = sum(1 for v in model_match.values() if v)
            model_match_total.append(matched / total if total > 0 else 0.0)

        # 4. Golden Recall (golden ∩ model-valid / golden, independent of simulation)
        if golden_components and model_match:
            # A golden component is "covered" if it appears in any retrieved lib_id
            # AND that retrieved component has a SPICE model.
            retrieved_data = ret.get("data", {})
            covered = set()
            for uid, info in retrieved_data.items():
                if not info or not model_match.get(uid, False):
                    continue
                lib_id = info.get("lib_id", "").lower()
                for gold in golden_components:
                    gold_lower = gold.lower()
                    if gold_lower in lib_id or lib_id in gold_lower:
                        covered.add(gold)
                        break
            golden_recall_vals.append(
                len(covered) / len(golden_components)
            )

    # Per-case aggregates
    spr_agg = aggregate_metrics(spr_vals)
    dev_agg = aggregate_metrics(dev_vals) if dev_vals else {"mean": None, "std": None}
    mm_agg = aggregate_metrics(model_match_total) if model_match_total else {"mean": None, "std": None}
    gr_agg = aggregate_metrics(golden_recall_vals) if golden_recall_vals else {"mean": None, "std": None}
    sch_agg = aggregate_metrics(sch_vals)

    # First-Pass: conditional — only among passed runs
    fp_rate = None
    if spr_vals.count(1) > 0:
        fp_rate = sum(fp_vals) / spr_vals.count(1)

    return {
        "spr": spr_agg,
        "target_deviation": dev_agg,
        "model_match": mm_agg,
        "golden_recall": gr_agg,
        "first_pass": {"mean": round(fp_rate, 4) if fp_rate is not None else None, "std": 0.0},
        "schematic_pass": sch_agg,
    }


# ================= Final Report =================

def compute_final_report(experiment_name: str, method_name: str,
                         all_run_results: List[Dict],
                         test_case_ids: List[str],
                         golden_components_map: Dict[str, List[str]],
                         targets_map: Dict[str, Optional[Dict]] = None) -> Dict[str, Any]:
    """Compute final aggregated report for one method across all test cases and runs."""
    if targets_map is None:
        targets_map = {}

    # Group by test case
    by_test_case = {}
    for r in all_run_results:
        tc_id = r.get("test_case_id", "unknown")
        if tc_id not in by_test_case:
            by_test_case[tc_id] = []
        by_test_case[tc_id].append(r)

    per_case_results = {}
    for tc_id, runs in by_test_case.items():
        tc_targets = targets_map.get(tc_id)
        golden = golden_components_map.get(tc_id, [])
        per_case_results[tc_id] = compute_per_case_metrics(runs, tc_targets, golden)

    # Overall: mean of per-case means (equal weight per test case)
    def _overall(key: str) -> Dict[str, Optional[float]]:
        vals = []
        for tc_id, case in per_case_results.items():
            entry = case.get(key, {})
            m = entry.get("mean")
            if m is not None:
                vals.append(m)
        return aggregate_metrics(vals)

    return {
        "experiment": experiment_name,
        "method": method_name,
        "num_test_cases": len(test_case_ids),
        "num_runs": len(all_run_results) // max(len(test_case_ids), 1),
        "spr": _overall("spr"),
        "target_deviation": _overall("target_deviation"),
        "model_match": _overall("model_match"),
        "golden_recall": _overall("golden_recall"),
        "first_pass": _overall("first_pass"),
        "schematic_pass": _overall("schematic_pass"),
        "per_case": per_case_results,
    }
