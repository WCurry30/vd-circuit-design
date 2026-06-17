# Plan Comparison (Full Pipeline) — End-to-End Pipeline Comparison

- **Generated**: 20260511_001552
- **Test Cases**: 10
- **Runs per Test Case**: 3
- **Total Pipeline Runs**: 150

## End-to-End Simulation Metrics

All metrics derived from physical simulation (Ngspice) after Plan → Retrieve → Simulate → Schematic pipeline.

| Method | SPR ↑ | Target Dev ↓ | Model Match ↑ | Golden Recall ↑ | First-Pass ↑ | Schematic ↑ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Ours** | 76.7% | **10.0%** | 98.1% | 93.6% | **81.5%** | 76.7% |
| **CoT** | **90.0%** | 26.2% | **98.3%** | 92.5% | 68.3% | **90.0%** |
| **SelfReflection** | 76.7% | 18.8% | 93.4% | **94.2%** | 66.7% | 76.7% |
| **ToT** | 83.3% | 19.4% | 97.3% | **94.2%** | 77.8% | 83.3% |
| **AutoGen** | 73.3% | 28.8% | 97.3% | 91.4% | 66.7% | 73.3% |

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
| Ours | 10.0% | 4.7% | 28.5% | 8.3% | 12.9% | N/A | 1.0% | 16.7% | 0.0% | 8.0% |
| CoT | 9.5% | 84.0% | 7.6% | 6.8% | 94.2% | 0.3% | 1.9% | 50.0% | 0.0% | 8.0% |
| SelfReflection | 11.2% | 84.0% | 4.5% | 9.7% | N/A | 0.2% | 1.2% | 50.0% | 0.0% | 8.0% |
| ToT | 6.0% | 84.0% | 18.2% | 7.4% | N/A | 0.2% | 1.2% | 50.0% | 0.0% | 8.0% |
| AutoGen | 5.0% | 84.0% | 8.8% | 8.1% | 94.0% | N/A | 1.2% | 50.0% | 0.0% | 8.0% |

## SPR per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 66.7% | 66.7% | 33.3% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| CoT | 100.0% | 100.0% | 100.0% | 100.0% | 33.3% | 66.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| SelfReflection | 100.0% | 100.0% | 66.7% | 66.7% | 0.0% | 33.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| ToT | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 33.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| AutoGen | 100.0% | 100.0% | 66.7% | 100.0% | 33.3% | 0.0% | 100.0% | 33.3% | 100.0% | 100.0% |

## Model Match per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 96.1% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 95.6% | 89.4% |
| CoT | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 96.3% | 86.3% |
| SelfReflection | 94.9% | 100.0% | 82.8% | 92.3% | 88.9% | 100.0% | 100.0% | 83.3% | 100.0% | 91.9% |
| ToT | 100.0% | 100.0% | 100.0% | 89.5% | 100.0% | 100.0% | 95.2% | 100.0% | 97.0% | 90.9% |
| AutoGen | 95.2% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 94.9% | 95.8% | 87.5% |

## Golden Recall per Test Case

| Method | test_1 | test_10 | test_2 | test_3 | test_4 | test_5 | test_6 | test_7 | test_8 | test_9 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Ours | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 100.0% | 100.0% | 77.8% |
| CoT | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 100.0% | 100.0% | 66.7% |
| SelfReflection | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 100.0% | 100.0% | 83.3% |
| ToT | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 100.0% | 100.0% | 83.3% |
| AutoGen | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 83.3% | 100.0% | 83.3% | 100.0% | 72.2% |


---
*Report generated 20260511_001552*