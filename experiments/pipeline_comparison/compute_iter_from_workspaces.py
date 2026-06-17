"""
Compute Average Iterations (Iter) from workspace pipeline_result.json files.

Reads all 270 workspace directories sorted by timestamp, splits into 9 groups
of 30 (5 plan methods + 4 retrieval methods), and computes mean Iter per method.

Mapping (confirmed against per-method JSON aggregation timestamps):
  Plan:      [  0– 29] Ours    [ 30– 59] CoT    [ 60– 89] SelfReflection
             [ 90–119] ToT     [120–149] AutoGen
  Retrieval: [150–179] Ours    [180–209] NaiveRAG
             [210–239] CritiqueRAG  [240–269] CRAG

Usage:
  python experiments\pipeline_comparison\compute_iter_from_workspaces.py
"""

import json
import os
import re
import statistics
from pathlib import Path
from collections import defaultdict

WORKSPACES_DIR = Path(__file__).resolve().parents[2] / "experiment_results" / "pipeline_workspaces"


def extract_ts(dirname: str) -> str:
    m = re.search(r"(\d{8}_\d{6})", dirname)
    return m.group(1) if m else ""


def load_all_workspaces():
    records = []
    for entry in os.listdir(WORKSPACES_DIR):
        ws_path = WORKSPACES_DIR / entry
        if not ws_path.is_dir():
            continue
        result_file = ws_path / "pipeline_result.json"
        if not result_file.exists():
            continue
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        tc_id = data.get("test_case_id", "unknown")
        sim = data.get("simulation", {})
        passed = sim.get("passed", False)
        iterations = sim.get("iterations", 0)

        records.append({
            "dir": entry,
            "ts": extract_ts(entry),
            "tc": tc_id,
            "passed": passed,
            "iterations": iterations,
        })

    records.sort(key=lambda r: r["ts"])
    return records


def compute_iter(method_records):
    """Compute mean Iter: per-test-case mean (passed runs only), then average across test cases."""
    by_tc = defaultdict(list)
    for r in method_records:
        if r["passed"]:
            by_tc[r["tc"]].append(r["iterations"])

    case_means = []
    per_case = {}
    for tc in sorted(by_tc.keys()):
        vals = by_tc[tc]
        m = statistics.mean(vals)
        per_case[tc] = {"mean": round(m, 2), "passed": len(vals), "values": vals}
        case_means.append(m)

    overall = round(statistics.mean(case_means), 2) if case_means else None
    return {
        "per_case": per_case,
        "overall": overall,
        "total_passed": sum(len(v["values"]) for v in per_case.values()),
        "total_records": len(method_records),
    }


def main():
    records = load_all_workspaces()
    print(f"Loaded {len(records)} workspace records (sorted by timestamp)\n")

    # 9 methods × up to 30 workspaces each. Some runs may lack pipeline_result.json.
    PLAN_METHODS = ["Ours", "CoT", "SelfReflection", "ToT", "AutoGen"]
    RETRIEVAL_METHODS = ["Ours", "NaiveRAG", "CritiqueRAG", "CRAG"]

    all_methods = []
    for m in PLAN_METHODS:
        all_methods.append(("Plan", m))
    for m in RETRIEVAL_METHODS:
        all_methods.append(("Retrieval", m))

    # Split sorted records into 9 equal chunks
    chunk_size = len(records) // len(all_methods)
    remainder = len(records) % len(all_methods)
    print(f"Records: {len(records)}, chunk_size={chunk_size}, remainder={remainder}\n")

    results = {}
    idx = 0
    for i, (category, method) in enumerate(all_methods):
        start = idx
        extra = 1 if i < remainder else 0
        end = start + chunk_size + extra
        idx = end
        recs = records[start:end]
        result = compute_iter(recs)
        results[(category, method)] = result

        # Quick sanity: count test cases
        tcs = set(r["tc"] for r in recs)
        print(f"[{category}] {method}: {len(recs)} records, {len(tcs)} test cases, "
              f"{result['total_passed']} passed, Iter={result['overall']}")

    # ============================================================
    # Paper-ready output
    # ============================================================
    print("\n" + "=" * 70)
    print("TABLE 4 — Plan Baseline Comparison (DeepSeek V3.2)")
    print("=" * 70)
    print(f"{'Method':<20} {'SPR':>8} {'TD':>8} {'Iter':>8}")
    print("-" * 44)
    plan_spr_td = {
        "Ours": (83.3, 7.3),
        "CoT": (86.7, 19.2),
        "SelfReflection": (90.0, 26.7),
        "ToT": (86.7, 18.4),
        "AutoGen": (86.7, 18.7),
    }
    for method in PLAN_METHODS:
        spr, td = plan_spr_td[method]
        r = results[("Plan", method)]
        it = f"{r['overall']:.2f}" if r["overall"] is not None else "--"
        print(f"{method:<20} {spr:>7.1f}% {td:>7.1f}% {it:>8}")

    print("\n" + "=" * 70)
    print("TABLE 5 — Retrieval Baseline Comparison (DeepSeek V3.2)")
    print("=" * 70)
    print(f"{'Method':<20} {'SPR':>8} {'TD':>8} {'Iter':>8}")
    print("-" * 44)
    retrieval_spr_td = {
        "Ours": (80.0, 10.4),
        "NaiveRAG": (43.3, 5.7),
        "CritiqueRAG": (30.0, 3.5),
        "CRAG": (40.0, 5.2),
    }
    for method in RETRIEVAL_METHODS:
        spr, td = retrieval_spr_td[method]
        r = results[("Retrieval", method)]
        it = f"{r['overall']:.2f}" if r["overall"] is not None else "--"
        print(f"{method:<20} {spr:>7.1f}% {td:>7.1f}% {it:>8}")

    # Detailed per-case breakdown
    print("\n" + "=" * 70)
    print("PER-CASE DETAIL (Plan Comparison)")
    print("=" * 70)
    for method in PLAN_METHODS:
        r = results[("Plan", method)]
        print(f"\n--- {method} (Iter={r['overall']}, passed={r['total_passed']}/{r['total_records']}) ---")
        for tc in sorted(r["per_case"].keys()):
            info = r["per_case"][tc]
            print(f"  {tc}: iter={info['mean']}, passed={info['passed']}, vals={info['values']}")

    print("\n" + "=" * 70)
    print("PER-CASE DETAIL (Retrieval Comparison)")
    print("=" * 70)
    for method in RETRIEVAL_METHODS:
        r = results[("Retrieval", method)]
        print(f"\n--- {method} (Iter={r['overall']}, passed={r['total_passed']}/{r['total_records']}) ---")
        for tc in sorted(r["per_case"].keys()):
            info = r["per_case"][tc]
            print(f"  {tc}: iter={info['mean']}, passed={info['passed']}, vals={info['values']}")


if __name__ == "__main__":
    main()
