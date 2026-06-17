"""
Multi-Model Full Pipeline Comparison Experiment
================================================
Runs Plan and Retrieval comparison experiments with 6 different LLMs.
All LLM calls in the entire pipeline use the same model for each experiment.

Models:
  - deepseek-v4-flash (DeepSeek V4 Flash)
  - deepseek-v3.2    (DeepSeek V3.2)
  - qwen-3.5-27b     (Qwen3.5-27B)
  - qwen-3.6-35b-a3b (Qwen3.6-35B-A3B)
  - gpt-4o-mini       (GPT-4o-mini)
  - gpt-4o            (GPT-4o)

Output:
  {OUTPUT_BASE}/model_{name}/
  {OUTPUT_BASE}/summary_all_models_{timestamp}.md
"""

import json
import os
import sys
import io
import time
import statistics
import random
from typing import List, Dict, Any, Optional
from pathlib import Path

if sys.platform == 'win32' and not isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except (AttributeError, OSError):
        pass

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "framework"))

from experiments.pipeline_comparison.pipeline_runner import PipelineRunner
from experiments.pipeline_comparison.plan_methods import create_plan_method
from experiments.pipeline_comparison.retrieval_methods import create_retrieval_method
from experiments.pipeline_comparison.metrics import compute_final_report
from experiments.pipeline_comparison.report_generator import generate_markdown_report, generate_json_results

import circuit_planner_v as planner_module
import experiments.pipeline_comparison.plan_methods as plan_methods_module
import core.netlist_engine as netlist_engine_module
import core.spice_engine as spice_engine_module

# ================= Model Configuration =================
DEEPSEEK_API_KEY = os.environ.get("EDA_API_KEY", "")
GPT_API_KEY = os.environ.get("EDA_GPT_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("EDA_BASE_URL", "")
GPT_BASE_URL = os.environ.get("EDA_GPT_BASE_URL", "")

MODELS = [
    {
        "name": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model_id": "deepseek-ai/DeepSeek-V3.2",
        "thinking_enabled": False,
        "explicit_disable_thinking": False,
    },
    {
        "name": "deepseek-v3.2",
        "display_name": "DeepSeek V3.2",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model_id": "deepseek-ai/DeepSeek-V3.2",
        "thinking_enabled": False,
        "explicit_disable_thinking": False,
    },
    {
        "name": "qwen-3.5-27b",
        "display_name": "Qwen3.5-27B",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model_id": "Qwen/Qwen3.5-27B",
        "thinking_enabled": False,
        "explicit_disable_thinking": True,
    },
    {
        "name": "qwen-3.6-35b-a3b",
        "display_name": "Qwen3.6-35B-A3B",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model_id": "Qwen/Qwen3.6-35B-A3B",
        "thinking_enabled": False,
        "explicit_disable_thinking": True,
    },
    {
        "name": "gpt-4o-mini",
        "display_name": "GPT-4o-mini",
        "api_key": GPT_API_KEY,
        "base_url": GPT_BASE_URL,
        "model_id": "gpt-4o-mini",
        "thinking_enabled": False,
        "explicit_disable_thinking": False,
    },
    {
        "name": "gpt-4o",
        "display_name": "GPT-4o",
        "api_key": GPT_API_KEY,
        "base_url": GPT_BASE_URL,
        "model_id": "gpt-4o",
        "thinking_enabled": False,
        "explicit_disable_thinking": False,
    },
]

# ================= Experiment Config =================
TEST_CASES_FILE = project_root / "experiments" / "datasets" / "test_cases_v3.json"
OUTPUT_BASE = os.environ.get("EDA_OUTPUT_DIR", str(project_root / "experiment_results" / "pipeline_comparison"))
WORKSPACE_BASE = os.environ.get("EDA_WORKSPACE_DIR", str(project_root / "experiment_results" / "pipeline_workspaces"))

PLAN_METHODS = ["Ours", "CoT", "SelfReflection", "ToT", "AutoGen"]
RETRIEVAL_METHODS = ["Ours", "NaiveRAG", "CritiqueRAG", "CRAG"]
NUM_RUNS = 3


def load_test_cases(filepath: Path) -> List[Dict]:
    if not filepath.exists():
        print(f"ERROR: Test case file not found: {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()
    try:
        test_cases = json.loads(content)
    except json.JSONDecodeError:
        import re
        test_cases = []
        objects = re.findall(r'\{[^{}]*\}', content)
        for obj_str in objects:
            try:
                test_cases.append(json.loads(obj_str))
            except:
                pass
    return test_cases if isinstance(test_cases, list) else []


def setup_all_modules(model_config: Dict):
    """Switch ALL modules to use the specified model."""
    api_key = model_config["api_key"]
    base_url = model_config["base_url"]
    model_id = model_config["model_id"]
    thinking = model_config.get("thinking_enabled", False)
    disable_thinking = model_config.get("explicit_disable_thinking", False)

    modules = [
        planner_module,
        plan_methods_module,
        netlist_engine_module,
        spice_engine_module,
    ]

    for mod in modules:
        mod.API_KEY = api_key
        mod.BASE_URL = base_url
        mod.MODEL_NAME = model_id
        mod.THINKING_ENABLED = thinking
        mod.EXPLICIT_DISABLE_THINKING = disable_thinking

    # Also update planner_module inside plan_methods (same object, but be explicit)
    plan_methods_module.planner_module.API_KEY = api_key
    plan_methods_module.planner_module.BASE_URL = base_url
    plan_methods_module.planner_module.MODEL_NAME = model_id
    plan_methods_module.planner_module.THINKING_ENABLED = thinking
    plan_methods_module.planner_module.EXPLICIT_DISABLE_THINKING = disable_thinking

    print(f"   [Model] Switched to: {model_config['display_name']} ({model_id})")


def run_method_comparison(
    experiment_name: str,
    variable_methods: List[str],
    variable_type: str,
    test_cases: List[Dict],
    num_runs: int = 3,
) -> List[Dict[str, Any]]:
    """Run comparison across multiple methods (Plan or Retrieval)."""
    all_results = []

    for method_name in variable_methods:
        print(f"\n{'#'*70}")
        print(f"# {experiment_name}: {method_name}")
        print(f"{'#'*70}")

        all_run_results = []
        method_start_time = time.time()

        for run_idx in range(num_runs):
            print(f"\n{'~'*50}")
            print(f" Run {run_idx + 1}/{num_runs}")
            print(f"{'~'*50}")
            random.seed(42 + run_idx)

            for tc_idx, test_case in enumerate(test_cases):
                tc_id = test_case["id"]
                user_req = test_case["user_requirement"]

                print(f"\n  [{tc_idx + 1}/{len(test_cases)}] {tc_id}: {user_req[:60]}...")

                if variable_type == "plan":
                    plan_method = create_plan_method(method_name)
                    retrieval_method = create_retrieval_method("Ours")
                else:
                    plan_method = create_plan_method("Ours")
                    retrieval_method = create_retrieval_method(method_name)

                runner = PipelineRunner(plan_method, retrieval_method)
                result = runner.run(user_req, tc_id, base_workspace=WORKSPACE_BASE)
                all_run_results.append(result)

                sim_ok = result.get("simulation", {}).get("passed", False)
                sch_ok = result.get("schematic", {}).get("generated", False)
                print(f"  -> {'SIM_OK' if sim_ok else 'SIM_FAIL'}, "
                      f"{'SCH_OK' if sch_ok else 'SCH_FAIL'}")

        golden_map = {tc["id"]: tc["golden_components"] for tc in test_cases}
        targets_map = {tc["id"]: tc.get("targets") for tc in test_cases}
        tc_ids = [tc["id"] for tc in test_cases]

        report = compute_final_report(
            experiment_name, method_name, all_run_results,
            tc_ids, golden_map, targets_map
        )
        report["runtime_seconds"] = round(time.time() - method_start_time, 1)
        all_results.append(report)

        # Print intermediate summary
        spr = report.get("spr", {}).get("mean", 0) or 0
        dev = report.get("target_deviation", {}).get("mean", 0) or 0
        mm = report.get("model_match", {}).get("mean", 0) or 0
        gr = report.get("golden_recall", {}).get("mean", 0) or 0
        fp = report.get("first_pass", {}).get("mean", 0) or 0
        print(f"\n  [{method_name}] SPR={spr:.0%} Dev={dev:.1%} MM={mm:.1%} "
              f"GR={gr:.1%} FP={fp:.0%}")

    return all_results


def run_experiment_for_model(model_config: Dict, test_cases: List[Dict]) -> Dict:
    """Run both Plan and Retrieval experiments for one model."""
    model_name = model_config["name"]
    model_display = model_config["display_name"]

    print(f"\n{'='*80}")
    print(f" MODEL: {model_display} ({model_config['model_id']})")
    print(f"{'='*80}")

    setup_all_modules(model_config)

    n_cases = len(test_cases)
    tc_ids = [tc["id"] for tc in test_cases]
    golden_map = {tc["id"]: tc["golden_components"] for tc in test_cases}
    targets_map = {tc["id"]: tc.get("targets") for tc in test_cases}

    model_output_dir = os.path.join(OUTPUT_BASE, f"model_{model_name}")
    os.makedirs(model_output_dir, exist_ok=True)

    # ---- Plan Comparison ----
    print(f"\n{'~'*60}")
    print(f" PLAN COMPARISON ({model_display})")
    print(f"{'~'*60}")

    plan_results = run_method_comparison(
        f"Plan_{model_name}", PLAN_METHODS, "plan", test_cases, NUM_RUNS
    )

    plan_md = generate_markdown_report(
        f"Plan_Comparison_{model_name}", plan_results, n_cases, NUM_RUNS, model_output_dir
    )
    plan_json = generate_json_results(
        f"Plan_Comparison_{model_name}", plan_results, model_output_dir
    )

    print(f"\n  Plan results saved to: {model_output_dir}")

    # ---- Retrieval Comparison ----
    print(f"\n{'~'*60}")
    print(f" RETRIEVAL COMPARISON ({model_display})")
    print(f"{'~'*60}")

    retrieval_results = run_method_comparison(
        f"Retrieval_{model_name}", RETRIEVAL_METHODS, "retrieval", test_cases, NUM_RUNS
    )

    ret_md = generate_markdown_report(
        f"Retrieval_Comparison_{model_name}", retrieval_results, n_cases, NUM_RUNS, model_output_dir
    )
    ret_json = generate_json_results(
        f"Retrieval_Comparison_{model_name}", retrieval_results, model_output_dir
    )

    print(f"\n  Retrieval results saved to: {model_output_dir}")

    return {
        "model_name": model_name,
        "model_display": model_display,
        "model_id": model_config["model_id"],
        "plan_results": plan_results,
        "retrieval_results": retrieval_results,
        "output_dir": model_output_dir,
    }


# ================= Cross-Model Summary =================

METRIC_NAMES = ["spr", "target_deviation", "model_match", "golden_recall",
                "first_pass", "schematic_pass"]
METRIC_LABELS = {
    "spr": "SPR ↑", "target_deviation": "Target Dev ↓",
    "model_match": "Model Match ↑", "golden_recall": "Golden Recall ↑",
    "first_pass": "First-Pass ↑", "schematic_pass": "Schematic ↑",
}

def _fmt(val, is_pct=True):
    """Format a metric value."""
    if val is None:
        return "N/A"
    if is_pct:
        return f"{val*100:.1f}%"
    return f"{val:.4f}"


def generate_cross_model_summary(all_model_results: List[Dict], output_dir: str):
    """Generate cross-model comparison tables for Plan and Retrieval experiments."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    summary_path = os.path.join(output_dir, f"summary_all_models_{timestamp}.md")

    with open(summary_path, "w", encoding="utf-8-sig") as f:
        f.write("# Multi-Model Full Pipeline Comparison — Summary\n\n")
        f.write(f"**Generated**: {timestamp}\n")
        f.write(f"**Models**: {len(all_model_results)}\n")
        f.write(f"**Test Cases**: 10\n")
        f.write(f"**Runs per Case**: {NUM_RUNS}\n\n")

        model_names = [r["model_display"] for r in all_model_results]

        for exp_type in ["plan", "retrieval"]:
            exp_label = "Plan" if exp_type == "plan" else "Retrieval"
            methods = PLAN_METHODS if exp_type == "plan" else RETRIEVAL_METHODS

            f.write(f"## {exp_label} Comparison\n\n")

            # --- One table per method per metric ---
            for metric_key in METRIC_NAMES:
                label = METRIC_LABELS[metric_key]
                f.write(f"### {label}\n\n")
                f.write("| Model | " + " | ".join(methods) + " |\n")
                f.write("| :--- " + " | :---:" * len(methods) + " |\n")

                for model_result in all_model_results:
                    results_key = "plan_results" if exp_type == "plan" else "retrieval_results"
                    results = model_result[results_key]

                    row = [model_result["model_display"]]
                    for method in methods:
                        method_report = next(
                            (r for r in results if r.get("method") == method), None
                        )
                        if method_report:
                            val = method_report.get(metric_key, {}).get("mean")
                            row.append(_fmt(val))
                        else:
                            row.append("—")
                    f.write("| " + " | ".join(row) + " |\n")
                f.write("\n")

            # --- Best-model summary per method ---
            f.write(f"### Best Model per Method ({exp_label})\n\n")
            f.write("| Method | Best SPR | Best Target Dev |\n")
            f.write("| :--- | :--- | :--- |\n")

            for method in methods:
                best_spr_model = "—"
                best_spr_val = -1
                best_dev_model = "—"
                best_dev_val = float("inf")

                for model_result in all_model_results:
                    results_key = "plan_results" if exp_type == "plan" else "retrieval_results"
                    results = model_result[results_key]
                    method_report = next(
                        (r for r in results if r.get("method") == method), None
                    )
                    if method_report:
                        spr_m = method_report.get("spr", {}).get("mean") or 0
                        if spr_m > best_spr_val:
                            best_spr_val = spr_m
                            best_spr_model = model_result["model_display"]

                        dev_m = method_report.get("target_deviation", {}).get("mean")
                        if dev_m is not None and dev_m < best_dev_val:
                            best_dev_val = dev_m
                            best_dev_model = model_result["model_display"]

                f.write(f"| {method} | {best_spr_model} ({best_spr_val*100:.0f}%) "
                        f"| {best_dev_model} ({best_dev_val*100:.1f}%) |\n")
            f.write("\n")

    print(f"\n{'='*80}")
    print(f"Cross-model summary: {summary_path}")
    print(f"{'='*80}")
    return summary_path


# ================= Main =================

def run_all_models(model_filter: Optional[List[str]] = None):
    """Run the experiment for all (or selected) models."""
    test_cases = load_test_cases(TEST_CASES_FILE)
    if not test_cases:
        print("ERROR: No test cases loaded!")
        return

    print(f"Loaded {len(test_cases)} test cases")
    print(f"Models: {[m['display_name'] for m in MODELS]}")
    print(f"Output base: {OUTPUT_BASE}")
    print(f"Plan methods: {PLAN_METHODS}")
    print(f"Retrieval methods: {RETRIEVAL_METHODS}")
    print(f"Runs per case: {NUM_RUNS}")
    print(f"Total pipeline runs per model: "
          f"{(len(PLAN_METHODS) + len(RETRIEVAL_METHODS)) * len(test_cases) * NUM_RUNS}")

    all_model_results = []

    for model_config in MODELS:
        if model_filter and model_config["name"] not in model_filter:
            print(f"\nSkipping model: {model_config['display_name']}")
            continue

        try:
            result = run_experiment_for_model(model_config, test_cases)
            all_model_results.append(result)
        except Exception as e:
            print(f"\nERROR running model {model_config['display_name']}: {e}")
            import traceback
            traceback.print_exc()
            continue

    if all_model_results:
        generate_cross_model_summary(all_model_results, OUTPUT_BASE)
        print("\nALL EXPERIMENTS COMPLETE")
    else:
        print("\nNo successful experiments!")


if __name__ == "__main__":
    # Supports: python run_full_pipeline_multi_model.py [model_filter]
    # e.g.: python run_full_pipeline_multi_model.py deepseek
    args = sys.argv[1:]
    if args:
        filters = [f.lower() for f in args]
        run_filter = [m["name"] for m in MODELS if any(f in m["name"] for f in filters)]
        if not run_filter:
            print(f"No matching models. Available: {[m['name'] for m in MODELS]}")
            sys.exit(1)
        print(f"Running only: {run_filter}")
        run_all_models(model_filter=run_filter)
    else:
        run_all_models()
