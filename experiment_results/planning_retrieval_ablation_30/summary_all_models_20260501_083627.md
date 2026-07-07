# Multi-Model Ablation Experiment Summary Report

## Participating Models
- DeepSeek V4 Flash (deepseek-ai/DeepSeek-V4-Flash)
- DeepSeek V3.2 (deepseek-ai/DeepSeek-V3.2)
- Qwen3.5-27B (Qwen/Qwen3.5-27B)
- Qwen3.6-35B-A3B (Qwen/Qwen3.6-35B-A3B)
- GPT-4o-mini (gpt-4o-mini)
- GPT-4o (gpt-4o)

## Summary Comparison Table

### Recall — Primary Metric

| Model | Group_0 (Ours Full) | Group_1 (w/o CoT) | Group_2 (w/o Component Pool) | Group_3 (w/o PRM) | Group_4 (w/o Exact Match) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| DeepSeek V4 Flash | 61.7% | 62.9% | 59.5% | 62.2% | 51.0% |
| DeepSeek V3.2 | 65.3% | 65.7% | 60.2% | 63.2% | 53.5% |
| Qwen3.5-27B | 66.7% | 67.1% | 62.7% | 67.5% | 55.2% |
| Qwen3.6-35B-A3B | 62.7% | 68.6% | 58.0% | 62.2% | 51.4% |
| GPT-4o-mini | 58.9% | 55.7% | 56.4% | 58.4% | 46.7% |
| GPT-4o | 63.4% | 63.2% | 59.1% | 62.0% | 52.5% |

### RHR (Retrieval Hit Rate)

| Model | Group_0 (Ours Full) | Group_1 (w/o CoT) | Group_2 (w/o Component Pool) | Group_3 (w/o PRM) | Group_4 (w/o Exact Match) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| DeepSeek V4 Flash | 98.1% | 98.2% | 97.0% | 98.1% | 97.0% |
| DeepSeek V3.2 | 98.5% | 98.3% | 97.0% | 98.0% | 96.7% |
| Qwen3.5-27B | 97.7% | 97.8% | 96.8% | 97.9% | 95.7% |
| Qwen3.6-35B-A3B | 98.1% | 97.8% | 93.6% | 98.2% | 96.3% |
| GPT-4o-mini | 95.0% | 96.3% | 95.8% | 96.4% | 92.7% |
| GPT-4o | 97.4% | 97.9% | 96.0% | 96.3% | 95.0% |

### Retrieval Quality (Average Match Score)

| Model | Group_0 (Ours Full) | Group_1 (w/o CoT) | Group_2 (w/o Component Pool) | Group_3 (w/o PRM) | Group_4 (w/o Exact Match) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| DeepSeek V4 Flash | 0.91 | 0.80 | 0.92 | 0.90 | 0.67 |
| DeepSeek V3.2 | 0.86 | 0.87 | 0.92 | 0.84 | 0.69 |
| Qwen3.5-27B | 0.86 | 0.78 | 0.90 | 0.85 | 0.69 |
| Qwen3.6-35B-A3B | 0.89 | 0.79 | 0.88 | 0.87 | 0.63 |
| GPT-4o-mini | 0.90 | 0.88 | 0.92 | 0.89 | 0.67 |
| GPT-4o | 0.91 | 0.78 | 0.91 | 0.90 | 0.67 |

### FPR (Format Parse Rate)

| Model | Group_0 (Ours Full) | Group_1 (w/o CoT) | Group_2 (w/o Component Pool) | Group_3 (w/o PRM) | Group_4 (w/o Exact Match) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| DeepSeek V4 Flash | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| DeepSeek V3.2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Qwen3.5-27B | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Qwen3.6-35B-A3B | 100.0% | 100.0% | 96.7% | 100.0% | 100.0% |
| GPT-4o-mini | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| GPT-4o | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Detailed Metrics

### DeepSeek V4 Flash

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_deepseek-v4-flash\ablation_deepseek-v4-flash_20260430_153241.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.1% |
| Recall | 61.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.91 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.2% |
| Recall | 62.9%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.80 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.0% |
| Recall | 59.5%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.92 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.1% |
| Recall | 62.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.90 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.0% |
| Recall | 51.0%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.67 |

### DeepSeek V3.2

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_deepseek-v3.2\ablation_deepseek-v3.2_20260501_003133.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.5% |
| Recall | 65.3%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.86 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.3% |
| Recall | 65.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.87 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.0% |
| Recall | 60.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.92 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.0% |
| Recall | 63.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.84 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.7% |
| Recall | 53.5%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.69 |

### Qwen3.5-27B

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_qwen-3.5-27b\ablation_qwen-3.5-27b_20260501_034732.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.7% |
| Recall | 66.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.86 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.8% |
| Recall | 67.1%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.78 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.8% |
| Recall | 62.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.90 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.9% |
| Recall | 67.5%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.85 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 95.7% |
| Recall | 55.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.69 |

### Qwen3.6-35B-A3B

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_qwen-3.6-35b-a3b\ablation_qwen-3.6-35b-a3b_20260501_055507.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.1% |
| Recall | 62.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.89 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.8% |
| Recall | 68.6%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.79 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 96.7% |
| RHR | 93.6% |
| Recall | 58.0%% |
| JSON Quality | 64.4% |
| Retrieval Quality | 0.88 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 98.2% |
| Recall | 62.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.87 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.3% |
| Recall | 51.4%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.63 |

### GPT-4o-mini

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_gpt-4o-mini\ablation_gpt-4o-mini_20260501_064933.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 95.0% |
| Recall | 58.9%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.90 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.3% |
| Recall | 55.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.88 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 95.8% |
| Recall | 56.4%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.92 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.4% |
| Recall | 58.4%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.89 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 92.7% |
| Recall | 46.7%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.67 |

### GPT-4o

File: `D:\EDA\Multi_Model_Ablation_OutputV2\model_gpt-4o\ablation_gpt-4o_20260501_074906.md`

#### Group_0 (Ours Full)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.4% |
| Recall | 63.4%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.91 |

#### Group_1 (w/o CoT)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 97.9% |
| Recall | 63.2%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.78 |

#### Group_2 (w/o Component Pool)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.0% |
| Recall | 59.1%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.91 |

#### Group_3 (w/o PRM)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 96.3% |
| Recall | 62.0%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.90 |

#### Group_4 (w/o Exact Match)
| Metric | Value |
| :--- | :--- |
| FPR | 100.0% |
| RHR | 95.0% |
| Recall | 52.5%% |
| JSON Quality | 66.7% |
| Retrieval Quality | 0.67 |

