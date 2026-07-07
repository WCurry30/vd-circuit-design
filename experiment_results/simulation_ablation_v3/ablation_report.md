## 2. Ablation Experiment Data Comparison Table (NUM_RUNS=3)

### 2.1 Per Test Case Details (3-Run Average)

| Test Case | G0_Ours | G1_No_Expert | G2_No_Shield | G3_No_Metric | G4_No_Iter |
| :--- | :---: | :---: | :---: | :---: | :---: |
| test_1 | ✅(3/3, 2 iter, 4.3%) | ❌(1/3, 4 iter, —) | ✅(3/3, 3 iter, 7.6%) | ✅(3/3, 3 iter, 4.2%) | ❌(0/3, —, —) |
| test_2 | ✅(3/3, 4 iter, 6.8%) | ❌(0/3, —, —) | ❌(0/3, —, —) | ✅(3/3, 3 iter, 6.0%) | ❌(0/3, —, —) |
| test_3 | 🟡(2/3, 1 iter, 11.2%) | ❌(0/3, —, —) | ✅(3/3, 4 iter, 10.0%) | 🟡(2/3, 2 iter, 7.5%) | 🟡(2/3, 1 iter, 11.2%) |
| test_4 | ❌(1/3, 1 iter, 3.6%) | ❌(0/3, —, —) | 🟡(2/3, 4 iter, 6.8%) | ❌(1/3, 3 iter, 5.2%) | ❌(0/3, —, —) |
| test_5 | 🟡(2/3, 2 iter, 0.6%) | ❌(0/3, —, —) | ❌(1/3, 1 iter, 0.3%) | ❌(1/3, 2 iter, 0.8%) | ❌(1/3, 1 iter, 0.3%) |
| test_6 | ✅(3/3, 1 iter, 0.9%) | ❌(0/3, —, —) | ✅(3/3, 2 iter, 1.0%) | ✅(3/3, 1 iter, 0.9%) | 🟡(2/3, 1 iter, 1.0%) |
| test_7 | ✅(3/3, 1 iter, 0.0%) | ❌(0/3, —, —) | ✅(3/3, 1 iter, 0.0%) | ✅(3/3, 1 iter, 0.0%) | ✅(3/3, 1 iter, 0.0%) |
| test_8 | ✅(3/3, 1 iter, 0.0%) | ❌(0/3, —, —) | ✅(3/3, 1 iter, 0.0%) | ✅(3/3, 1 iter, 0.0%) | ✅(3/3, 1 iter, 0.0%) |
| test_9 | ✅(3/3, 1 iter, 0.9%) | ❌(0/3, —, —) | ✅(3/3, 1 iter, 8.0%) | ❌(0/3, —, —) | ❌(0/3, —, —) |
| test_10 | ✅(3/3, 1 iter, 4.7%) | ❌(0/3, —, —) | ✅(3/3, 1 iter, 4.7%) | ✅(3/3, 1 iter, 4.7%) | ✅(3/3, 1 iter, 4.7%) |

### 2.2 Summary by Experiment Group (Mean ± Std)

| Metric | G0_Ours | G1_No_Expert | G2_No_Shield | G3_No_Metric | G4_No_Iter |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Success Rate | 86.7% ±34.6% | 3.3% ±18.3% | 80.0% ±40.7% | 73.3% ±45.0% | 46.7% ±50.7% |
| Target Deviation % (passed only) | 3.1 ±3.4 | — | 4.5 ±4.6 | 3.1 ±3.0 | 2.8 ±4.1 |
| First-Pass Rate | 63.3% ±49.0% | 0.0% ±0.0% | 50.0% ±50.9% | 43.3% ±50.4% | 46.7% ±50.7% |
| Iterations (passed only) | 1.5 ±1.2 | 4.0 | 1.9 ±1.8 | 1.7 ±1.1 | 1.0 ±0.0 |
| Avg Tokens | 8275 ±8009 | 10046 ±2952 | 6510 ±7753 | 4649 ±4867 | 1946 ±836 |

### 2.3 Stability Analysis (Std Dev Across 3 Runs)

| Group | Success Std | Deviation Std | Unstable Cases | Notes |
| :--- | :---: | :---: | :---: | :--- |
| G0_Ours | 0.233 | 3.6 | 3/10 (test_3,4,5) | 7 cases fully consistent across 3 runs; only 3 borderline cases showed variation |
| G1_No_Expert | 0.105 | — | 1/10 (test_1) | Nearly deterministically fails; only 1 accidental pass |
| G2_No_Shield | 0.358 | 4.0 | 2/10 (test_4,5) | No shield at temp=0.5; variation concentrated on hardest cases |
| G3_No_Metric | 0.378 | 2.8 | 3/10 (test_3,4,5) | Hard-threshold decisions more sensitive to borderline cases |
| G4_No_Iter | 0.450 | 4.5 | 3/10 (test_3,5,6) | Single pass without feedback; LLM variance directly determines outcome |

*Note: G0's 0.233 is the lowest across all groups (except G1 due to its deterministic failure); cross-run consistency is optimal.*

---
**CSV**: 
**Model**: deepseek-ai/DeepSeek-V3.2 (SiliconFlow API)
**Config**: NUM_RUNS=3, G0/G1/G3/G4 temp=0.3, G2 temp=0.5, G3 hard-threshold tightened
**Note**: Deviation and iteration count apply only to successful cases