"""Run end-to-end EDA pipeline comparisons on a selected dataset."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_DIR = PROJECT_ROOT / "framework"
BASELINE_DIR = PROJECT_ROOT / "baselines" / "pipeline_methods"
for path in (FRAMEWORK_DIR, BASELINE_DIR, PROJECT_ROOT):
    sys.path.insert(0, str(path))

from baselines.pipeline_methods.plan_methods import create_plan_method
from baselines.pipeline_methods.retrieval_methods import create_retrieval_method
from experiments.pipeline_comparison.metrics import compute_final_report
from experiments.pipeline_comparison.pipeline_runner import PipelineRunner
from experiments.pipeline_comparison.report_generator import generate_markdown_report


def load_cases(dataset_path: Path, case_id: str = None, limit: int = None):
    with dataset_path.open("r", encoding="utf-8-sig") as f:
        cases = json.load(f)
    if case_id:
        cases = [case for case in cases if case.get("id") == case_id]
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("No test cases selected.")
    return cases


def main():
    parser = argparse.ArgumentParser(description="Run EDA pipeline comparison experiments.")
    parser.add_argument(
        "--dataset",
        default=str(PROJECT_ROOT / "experiments" / "datasets" / "test_cases_v3.json"),
        help="Path to the JSON dataset. Use test_cases_v3.json for Ngspice pipeline experiments.",
    )
    parser.add_argument("--plan-method", default="Ours", choices=["Ours", "CoT", "SelfReflection", "ToT", "AutoGen"])
    parser.add_argument("--retrieval-method", default="Ours", choices=["Ours", "NaiveRAG", "CritiqueRAG", "CRAG"])
    parser.add_argument("--case-id", default=None, help="Optional single case id, e.g. test_1.")
    parser.add_argument("--limit", type=int, default=None, help="Optional number of cases from the start of the dataset.")
    parser.add_argument("--runs", type=int, default=1, help="Repeated runs per selected test case.")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    cases = load_cases(dataset_path, args.case_id, args.limit)

    plan_method = create_plan_method(args.plan_method)
    retrieval_method = create_retrieval_method(args.retrieval_method)
    runner = PipelineRunner(plan_method, retrieval_method)

    all_runs = []
    for case in cases:
        for run_index in range(args.runs):
            print(f"\n[Run] {case['id']} ({run_index + 1}/{args.runs})")
            result = runner.run(case["user_requirement"], case["id"])
            all_runs.append(result)

    test_case_ids = [case["id"] for case in cases]
    golden_components = {case["id"]: case.get("golden_components", []) for case in cases}
    targets = {case["id"]: case.get("targets") for case in cases}
    method_name = f"Plan={args.plan_method}, Retrieval={args.retrieval_method}"

    summary = compute_final_report(
        "Pipeline Comparison",
        method_name,
        all_runs,
        test_case_ids,
        golden_components,
        targets,
    )

    output_dir = PROJECT_ROOT / "experiment_results" / "pipeline_comparison" / "new_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{args.plan_method}_{args.retrieval_method}_summary.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    report_path = generate_markdown_report(
        "Pipeline Comparison",
        [summary],
        test_case_count=len(cases),
        num_runs=args.runs,
        output_dir=str(output_dir),
    )

    print(f"\nSaved summary: {json_path}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
