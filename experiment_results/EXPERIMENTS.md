# Experiment Results

This directory contains pre-computed experiment results for the paper *"A Verification-Driven Framework for Harnessing Large Language Models for Analog Circuit Design"*.

All experiments use the toolchain-aligned benchmark: a 30-task planning-stage subset (`test_cases_v2.json`) for semantic grounding evaluation, and a 10-task synthesis-stage subset (`test_cases_v3.json`) for end-to-end SPICE verification across 5 circuit families.

---

## 1. Synthesis-Stage Ablation (G0-G4)

**Model**: DeepSeek V3.2 | **Runs per group**: 3 | **Task count**: 10

### Aggregate Metrics

| Metric | G0: Full System | G1: No Expert | G2: No Shield | G3: No Metric | G4: No Iter |
|--------|:---:|:---:|:---:|:---:|:---:|
| **SPR** (Sim. Pass Rate) | **86.7%** | 3.3% | 80.0% | 73.3% | 46.7% |
| **Target Deviation** | 3.1% | — | 4.5% | 3.1% | 2.8% |
| **First-Pass Rate** | 63.3% | 0.0% | 50.0% | 43.3% | 46.7% |
| **Iterations** (mean±std) | 1.5±1.2 | 4.0 | 1.9±1.8 | 1.7±1.1 | 1.0±0.0 |
| **Avg Tokens/run** | 8,275 | 10,047 | 6,511 | 4,649 | 1,947 |

### Per-Task Detail

| Case | G0: Full System | G1: No Expert | G2: No Shield | G3: No Metric | G4: No Iter |
|------|:---:|:---:|:---:|:---:|:---:|
| test_1 (LPF 600Hz) | 3/3, 2 iter, 4.3% | 1/3 | 3/3, 3 iter, 7.6% | 3/3, 3 iter, 4.2% | 0/3 |
| test_2 (LPF 1000Hz) | 3/3, 4 iter, 6.8% | 0/3 | 0/3 | 3/3, 3 iter, 6.0% | 0/3 |
| test_3 (CE Amp 40dB) | 2/3, 1 iter, 11.2% | 0/3 | 3/3, 4 iter, 10.0% | 2/3, 2 iter, 7.5% | 2/3, 1 iter, 11.2% |
| test_4 (CE Amp 30dB) | 1/3, 1 iter, 3.6% | 0/3 | 2/3, 4 iter, 6.8% | 1/3, 3 iter, 5.2% | 0/3 |
| test_5 (Zener Reg, BJT) | 2/3, 2 iter, 0.6% | 0/3 | 1/3, 1 iter, 0.3% | 1/3, 2 iter, 0.8% | 1/3, 1 iter, 0.3% |
| test_6 (Zener Reg, basic) | 3/3, 1 iter, 0.9% | 0/3 | 3/3, 2 iter, 1.0% | 3/3, 1 iter, 0.9% | 2/3, 1 iter, 1.0% |
| test_7 (Inv Amp 40dB) | 3/3, 1 iter, 0.0% | 0/3 | 3/3, 1 iter, 0.0% | 3/3, 1 iter, 0.0% | 3/3, 1 iter, 0.0% |
| test_8 (Non-inv 20dB) | 3/3, 1 iter, 0.0% | 0/3 | 3/3, 1 iter, 0.0% | 3/3, 1 iter, 0.0% | 3/3, 1 iter, 0.0% |
| test_9 (LED 20mA) | 3/3, 1 iter, 0.9% | 0/3 | 3/3, 1 iter, 8.0% | 0/3 | 0/3 |
| test_10 (LED 10mA) | 3/3, 1 iter, 4.7% | 0/3 | 3/3, 1 iter, 4.7% | 3/3, 1 iter, 4.7% | 3/3, 1 iter, 4.7% |

Cell format: passed/3 runs, mean iterations, target deviation (passed-only).

**Raw data**: `simulation_ablation_v3/ablation_results.csv`

---

## 2. Planning-Stage Ablation (30 Tasks, 6 Models)

### Component Recall (%)

| Model | Full | w/o CoT | w/o Pool | w/o PRM | w/o Exact Match |
|-------|:---:|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | 61.7 | 62.9 | 59.5 | 62.2 | 51.0 |
| DeepSeek V3.2 | 65.3 | 65.7 | 60.2 | 63.2 | 53.5 |
| Qwen3.5-27B | 66.7 | 67.1 | 62.7 | 67.5 | 55.2 |
| Qwen3.6-35B-A3B | 62.7 | 68.6 | 58.0 | 62.2 | 51.4 |
| GPT-4o-mini | 58.9 | 55.7 | 56.4 | 58.4 | 46.7 |
| GPT-4o | 63.4 | 63.2 | 59.1 | 62.0 | 52.5 |
| **Average** | **63.1** | **63.9** | **59.3** | **62.6** | **51.7** |

### Retrieval Hit Rate (%)

| Model | Full | w/o CoT | w/o Pool | w/o PRM | w/o Exact Match |
|-------|:---:|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | 98.1 | 98.2 | 97.0 | 98.1 | 97.0 |
| DeepSeek V3.2 | 98.5 | 98.3 | 97.0 | 98.0 | 96.7 |
| Qwen3.5-27B | 97.7 | 97.8 | 96.8 | 97.9 | 95.7 |
| Qwen3.6-35B-A3B | 98.1 | 97.8 | 93.6 | 98.2 | 96.3 |
| GPT-4o-mini | 95.0 | 96.3 | 95.8 | 96.4 | 92.7 |
| GPT-4o | 97.4 | 97.9 | 96.0 | 96.3 | 95.0 |
| **Average** | **97.5** | **97.7** | **96.0** | **97.5** | **95.6** |

### Format Pass Rate (%)

| Model | Full | w/o CoT | w/o Pool | w/o PRM | w/o Exact Match |
|-------|:---:|:---:|:---:|:---:|:---:|
| **All models (avg)** | **100.0** | **100.0** | **99.5** | **100.0** | **100.0** |

**Raw data**: `planning_retrieval_ablation_30/summary_all_models_20260501_083627.md`

---

## 3. Multi-Model Planning Baseline Comparison

10-task synthesis subset, 6 models, 3 runs each.

### SPR (%) — Planning Methods

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
|-------|:---:|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | 80.0 | **93.3** | 83.3 | 86.7 | 93.3 |
| DeepSeek V3.2 | 83.3 | 86.7 | **90.0** | 86.7 | 86.7 |
| Qwen3.5-27B | **93.3** | 83.3 | 0.0 | 86.7 | 73.3 |
| Qwen3.6-35B-A3B | 70.0 | **73.3** | 0.0 | 73.3 | 66.7 |
| GPT-4o-mini | 56.7 | **86.7** | 63.3 | 73.3 | 76.7 |
| GPT-4o | **90.0** | 83.3 | 70.0 | 73.3 | 83.3 |

### Target Deviation (%) — Planning Methods

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
|-------|:---:|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | **10.4** | 26.6 | 27.0 | 26.6 | 25.7 |
| DeepSeek V3.2 | **7.3** | 19.2 | 26.7 | 18.4 | 18.7 |
| Qwen3.5-27B | **9.6** | 17.6 | N/A | 18.9 | 18.1 |
| Qwen3.6-35B-A3B | **8.9** | 19.6 | N/A | 19.6 | 19.5 |
| GPT-4o-mini | **12.0** | 19.6 | 24.1 | 20.0 | 26.3 |
| GPT-4o | **11.8** | 19.5 | 18.7 | 21.5 | 19.3 |

### Model Match (%) — Planning Methods

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
|-------|:---:|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | 98.6 | **98.8** | 93.3 | 96.8 | 96.8 |
| DeepSeek V3.2 | 98.3 | **98.8** | 92.6 | 97.5 | 97.8 |
| Qwen3.5-27B | **100.0** | 98.8 | N/A | 98.8 | 97.2 |
| Qwen3.6-35B-A3B | **99.1** | 97.5 | N/A | 96.9 | 96.1 |
| GPT-4o-mini | **100.0** | 97.4 | 98.6 | 97.3 | 94.5 |
| GPT-4o | **100.0** | 97.6 | 99.0 | 98.2 | 96.7 |

**Raw data**: `multi_model_comparison_v3/summary_all_models_20260518_111415.md`

---

## 4. Multi-Model Retrieval Baseline Comparison

10-task synthesis subset, 6 models, 3 runs each. All using "Ours" planner.

### SPR (%) — Retrieval Methods

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
|-------|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | **76.7** | 36.7 | 33.3 | 30.0 |
| DeepSeek V3.2 | **80.0** | 43.3 | 30.0 | 40.0 |
| Qwen3.5-27B | **86.7** | 36.7 | 23.3 | 40.0 |
| Qwen3.6-35B-A3B | **73.3** | 26.7 | 40.0 | 23.3 |
| GPT-4o-mini | **73.3** | 30.0 | 30.0 | 33.3 |
| GPT-4o | **93.3** | 40.0 | 30.0 | 43.3 |

### Model Match (%) — Retrieval Methods

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
|-------|:---:|:---:|:---:|:---:|
| DeepSeek V4 Flash | **98.2** | 0.2 | 0.5 | 1.0 |
| DeepSeek V3.2 | **99.0** | 0.0 | 0.0 | 0.2 |
| Qwen3.5-27B | **100.0** | 11.8 | 11.2 | 12.0 |
| Qwen3.6-35B-A3B | **99.7** | 12.1 | 11.8 | 12.2 |
| GPT-4o-mini | **100.0** | 0.0 | 0.0 | 0.0 |
| GPT-4o | **100.0** | 0.9 | 0.0 | 12.1 |

**Raw data**: `multi_model_comparison_v3/summary_all_models_20260518_111415.md` (Retrieval section)
**Per-method raw JSON**: `pipeline_comparison/`

---

## 5. Legacy Data

### Legacy Model Comparison (Planning-Stage)

`legacy_model_comparison/model_comparison_summary.md`

Older model comparison (DeepSeek 7B/14B/32B, Qwen 7B/14B/32B, GLM-32B, GPT-128k, Gemini-128k, Kimi 8k/32k/128k). Retained for reference.

### Legacy Simulation Ablation

`legacy_simulation_ablation/ablation_results.csv`

Older simulation ablation data (pre-V3). Superseded by `simulation_ablation_v3/`.
