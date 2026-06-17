# Retrieval Comparison (Full Pipeline) — End-to-End Pipeline Comparison

- **Generated**: 20260511_043233
- **Test Cases**: 10
- **Runs per Test Case**: 3
- **Total Pipeline Runs**: 120

## End-to-End Simulation Metrics

All metrics derived from physical simulation (Ngspice) after Plan → Retrieve → Simulate → Schematic pipeline.

| Method | SPR ↑ | Target Dev ↓ | Model Match ↑ | Golden Recall ↑ | First-Pass ↑ | Schematic ↑ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Ours** | **86.7%** | 9.6% | **99.0%** | **94.2%** | 78.3% | **86.7%** |
| **NaiveRAG** | 36.7% | **3.6%** | 9.5% | 23.7% | 66.7% | 36.7% |
| **CritiqueRAG** | 33.3% | 8.1% | 9.5% | 23.7% | 62.5% | 33.3% |
| **CRAG** | 43.3% | 6.1% | 9.8% | 24.5% | **83.3%** | 43.3% |

> **SPR** = Physical Convergence Rate | **Target Dev** = Specification Fidelity Error
> **Model Match** = Component Translatability | **Golden Recall** = Critical Component Coverage
> **First-Pass** = Initial Translation Fidelity (passed-only) | **Schematic** = Pipeline Completion Rate

## Metric Definitions

| Metric | Meaning | Simulation Stage |
| :--- | :--- | :--- |
| **SPR ↑** | Proportion of runs where Ngspice simulation converged | Ngspice pass/fail |
| **Target Dev ↓** | Relative error between simulated and target performance | Waveform analysis + specification check |
| **Model Match ↑** | Retrieved components with valid SPICE models / total planned | SPICE model injection check |
| **Golden Recall ↑** | Critical components found AND with valid models / total critical | SPICE model injection check |
| **First-Pass ↑** | Passed-on-first-attempt / total passed (conditional) | Ngspice iteration tracking |
| **Schematic ↑** | Runs producing valid KiCad .kicad_sch / total runs | Schematic generation |

## Target Deviation per Test Case

Each cell = mean of Target Deviation across runs that passed simulation (N/A = all runs failed).

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 4.8% | 4.7% | 9.3% | 9.4% | 41.0% | 0.5% | 1.0% | 16.7% | 0.0% | 8.0% |
| NaiveRAG | N/A | 4.7% | N/A | N/A | N/A | 0.7% | 1.0% | N/A | N/A | 8.0% |
| CritiqueRAG | N/A | 22.4% | N/A | N/A | N/A | 0.8% | 1.0% | N/A | N/A | 8.0% |
| CRAG | N/A | 4.7% | N/A | 10.0% | 12.2% | 0.5% | 1.0% | N/A | N/A | 8.0% |

## SPR per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 100.0% | 33.3% | 66.7% | 66.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| NaiveRAG | 0.0% | 100.0% | 0.0% | 0.0% | 0.0% | 66.7% | 100.0% | 0.0% | 0.0% | 100.0% |
| CritiqueRAG | 0.0% | 100.0% | 0.0% | 0.0% | 0.0% | 66.7% | 66.7% | 0.0% | 0.0% | 100.0% |
| CRAG | 0.0% | 100.0% | 0.0% | 33.3% | 33.3% | 66.7% | 100.0% | 0.0% | 0.0% | 100.0% |

## Model Match per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 100.0% | 100.0% | 97.2% | 100.0% | 100.0% | 100.0% | 100.0% | 93.0% |
| NaiveRAG | 10.0% | 12.6% | 6.9% | 8.6% | 7.3% | 10.7% | 15.1% | 7.6% | 7.9% | 8.5% |
| CritiqueRAG | 8.6% | 14.5% | 7.5% | 9.4% | 8.0% | 10.4% | 15.1% | 6.9% | 8.3% | 6.1% |
| CRAG | 8.9% | 12.6% | 7.2% | 11.5% | 8.8% | 10.4% | 16.7% | 7.5% | 7.4% | 7.0% |

## Golden Recall per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 100.0% | 100.0% | 83.3% |
| NaiveRAG | 25.0% | 20.0% | 25.0% | 33.3% | 25.0% | 16.7% | 25.0% | 25.0% | 25.0% | 16.7% |
| CritiqueRAG | 25.0% | 20.0% | 25.0% | 33.3% | 25.0% | 16.7% | 25.0% | 25.0% | 25.0% | 16.7% |
| CRAG | 25.0% | 20.0% | 25.0% | 41.7% | 25.0% | 16.7% | 25.0% | 25.0% | 25.0% | 16.7% |


---
*Report generated 20260511_043233*