# Experiment entry points

- `scripts/final_report.py`: offline validation and complete final statistics.
- `scripts/verify.sh`: record validation and regression tests.
- `../revision/development/verify_unified_gate.py`: 20 positive references and 20 negative fixtures through Ngspice.
- `../revision/development/unified_runner.py`: selected audited generation implementation.
- `pipeline_comparison/`: source for the separate historical component comparisons.

Full includes preparation, grounding, family prompts, cleanup and repair feedback. Four ablations remove one component each; Equal-call matches its paired Full call count without feedback. Sizing is disabled. The generation budget is three responses. Frozen settings and baseline adapter behavior are in `../experiment_results/final/protocols/`.

Generation requires repeated URL/KEY/MODEL triplets in a private file passed via `--env`; `.env.example` illustrates the format. Model lookup keys are `deepseek-v4-flash`, `gpt-4o`, `Pro/deepseek-ai/DeepSeek-V3.2`, and `Qwen/Qwen3.6-35B-A3B`. Supply the expected response model explicitly. The component catalog is included at `../framework/chroma_db/`. Embedding models must be installed in the runtime.

Exact frozen server runs reside at `nengge-out:/home/nengge/ZY/EDA_Document/EDA_Last_Framework_Repair_20260909/`. Use their snapshots for checkpoint recovery. Relocated source requires a new manifest; the original manifest's source checks stay active.

See [implementation settings](IMPLEMENTATION.md) for sampling, scoring, seed assignment, and model identifiers.
