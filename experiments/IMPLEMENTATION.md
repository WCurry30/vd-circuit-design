# Implementation settings

These settings describe the final 20-task experiment. Frozen batch manifests remain in `../experiment_results/final/protocols/`; historical component studies keep their own configurations.

## Generation and preparation

- Synthesis and requirement elaboration: temperature 0.3.
- Three planning candidates: temperatures 0.1, 0.2, 0.3.
- Planning encoder: `BAAI/bge-small-zh-v1.5`; grounding encoder: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Planning lexical bonuses: LM2904 +0.15, otherwise amplifier/opamp +0.02; capacitor/cap and resistor/res +0.02 each; speaker/mic +0.03. Matching follows the substring rules in the planner.
- Grounding shortlist: 15. Reranking: exact identifier +10, matching catalog keyword +3 each, short identifier +2, unmatched underscore −5. Semantic threshold: 0.4. Direct/predefined mappings and recognized primitives bypass this screen.
- Seeds: base 260910000 plus numeric task ID × 10 plus repeat (1–3). Synthesis adds attempt index minus one; planning candidates add candidate index (1–3). Seed requests do not guarantee deterministic provider execution.
- Thinking explicitly disabled for V4 Flash and Qwen3.6. Sizing disabled.

## Runtime and model identifiers

Ngspice 36 uses the fixed model catalog in `../revision/benchmark/models/`. The task specification defines every condition and acceptance bound.

| Model | Requested identifier | Expected response identifier |
|---|---|---|
| V4 Flash | deepseek-v4-flash | deepseek-flash |
| V3.2 | Pro/deepseek-ai/DeepSeek-V3.2 | Pro/deepseek-ai/DeepSeek-V3.2 |
| Qwen3.6 | Qwen/Qwen3.6-35B-A3B | Qwen/Qwen3.6-35B-A3B |
| GPT-4o | gpt-4o | gpt-4o-2024-08-06 |

Individual requests and responses provide the observed identifiers and usage. The V4 response alias is recorded explicitly; supplier-side reconciliation is unavailable.
