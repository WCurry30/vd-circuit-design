# Final Results

This directory contains the final machine-readable results used in the paper. Intermediate API exchanges, logs, recovery records, and temporary workspaces are intentionally excluded.

## Main Comparison

[`final/statistics/summary.json`](final/statistics/summary.json) is the authoritative aggregate for the 20-task, three-repeat main comparison and the V4 ablations. Each row reports a model, method, passes, trials, success rate, task-level bootstrap interval, generation calls, known tokens, and failure-stage counts.

The final Full-method success rates are:

| Model | Passes | Success rate |
|---|---:|---:|
| V4 | 43 / 60 | 71.7% |
| DeepSeek V3.2 | 33 / 60 | 55.0% |
| GPT-5.5 | 40 / 60 | 66.7% |
| Qwen3.8-27B | 16 / 60 | 26.7% |

Additional final tables are in `final/statistics/`: `task_results.csv`, `trials.csv`, `paired_outcomes.csv`, `exposure_strata.csv`, and `resources.json`.

## Component Study

The retained final summaries for the GPT-5.5 and Qwen3.8 component-planning studies are:

- [`final/statistics/model_component_summary_gpt55.json`](final/statistics/model_component_summary_gpt55.json)
- [`final/statistics/model_component_summary_qwen38.json`](final/statistics/model_component_summary_qwen38.json)

Each file reports component recall, retrieval hit rate, and JSON-format parsing rate for every configuration and stratum.

## Recalculation

Run the offline consistency check without API calls:

```bash
python experiments/scripts/final_report.py --verify-only
```
