# Multi-Model Full Pipeline Comparison — Summary

**Generated**: 20260518_111415
**Models**: 6
**Test Cases**: 10
**Runs per Case**: 3

## Plan Comparison

### SPR ↑

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 80.0% | 93.3% | 83.3% | 86.7% | 93.3% |
| DeepSeek V3.2 | 83.3% | 86.7% | 90.0% | 86.7% | 86.7% |
| Qwen3.5-27B | 93.3% | 83.3% | 0.0% | 86.7% | 73.3% |
| Qwen3.6-35B-A3B | 70.0% | 73.3% | 0.0% | 73.3% | 66.7% |
| GPT-4o-mini | 56.7% | 86.7% | 63.3% | 73.3% | 76.7% |
| GPT-4o | 90.0% | 83.3% | 70.0% | 73.3% | 83.3% |

### Target Dev ↓

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 10.4% | 26.6% | 27.0% | 26.6% | 25.7% |
| DeepSeek V3.2 | 7.3% | 19.2% | 26.7% | 18.4% | 18.7% |
| Qwen3.5-27B | 9.6% | 17.6% | N/A | 18.9% | 18.1% |
| Qwen3.6-35B-A3B | 8.9% | 19.6% | N/A | 19.6% | 19.5% |
| GPT-4o-mini | 12.0% | 19.6% | 24.1% | 20.0% | 26.3% |
| GPT-4o | 11.8% | 19.5% | 18.7% | 21.5% | 19.3% |

### Model Match ↑

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 98.6% | 98.8% | 93.3% | 96.8% | 96.8% |
| DeepSeek V3.2 | 98.3% | 98.8% | 92.6% | 97.5% | 97.8% |
| Qwen3.5-27B | 100.0% | 98.8% | N/A | 98.8% | 97.2% |
| Qwen3.6-35B-A3B | 99.1% | 97.5% | N/A | 96.9% | 96.1% |
| GPT-4o-mini | 100.0% | 97.4% | 98.6% | 97.3% | 94.5% |
| GPT-4o | 100.0% | 97.6% | 99.0% | 98.2% | 96.7% |

### Golden Recall ↑

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 94.2% | 92.5% | 94.2% | 93.0% | 91.9% |
| DeepSeek V3.2 | 94.2% | 92.5% | 94.2% | 94.2% | 93.0% |
| Qwen3.5-27B | 94.2% | 94.2% | N/A | 93.6% | 91.9% |
| Qwen3.6-35B-A3B | 94.2% | 94.2% | N/A | 93.5% | 92.5% |
| GPT-4o-mini | 95.8% | 93.0% | 92.5% | 94.2% | 93.0% |
| GPT-4o | 94.2% | 93.0% | 94.2% | 94.2% | 92.2% |

### First-Pass ↑

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 85.2% | 70.0% | 65.0% | 60.0% | 70.0% |
| DeepSeek V3.2 | 66.7% | 81.5% | 65.0% | 77.8% | 77.8% |
| Qwen3.5-27B | 70.0% | 77.8% | N/A | 66.7% | 77.8% |
| Qwen3.6-35B-A3B | 63.0% | 87.5% | N/A | 79.2% | 81.2% |
| GPT-4o-mini | 85.7% | 77.8% | 71.4% | 62.5% | 56.7% |
| GPT-4o | 63.3% | 66.7% | 63.0% | 75.0% | 77.8% |

### Schematic ↑

| Model | Ours | CoT | SelfReflection | ToT | AutoGen |
| :---  | :---: | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 80.0% | 93.3% | 83.3% | 86.7% | 93.3% |
| DeepSeek V3.2 | 83.3% | 86.7% | 90.0% | 86.7% | 86.7% |
| Qwen3.5-27B | 90.0% | 83.3% | 0.0% | 86.7% | 73.3% |
| Qwen3.6-35B-A3B | 70.0% | 73.3% | 0.0% | 73.3% | 66.7% |
| GPT-4o-mini | 53.3% | 86.7% | 63.3% | 73.3% | 76.7% |
| GPT-4o | 90.0% | 83.3% | 70.0% | 73.3% | 83.3% |

### Best Model per Method (Plan)

| Method | Best SPR | Best Target Dev |
| :--- | :--- | :--- |
| Ours | Qwen3.5-27B (93%) | DeepSeek V3.2 (7.3%) |
| CoT | DeepSeek V4 Flash (93%) | Qwen3.5-27B (17.6%) |
| SelfReflection | DeepSeek V3.2 (90%) | GPT-4o (18.7%) |
| ToT | DeepSeek V4 Flash (87%) | DeepSeek V3.2 (18.4%) |
| AutoGen | DeepSeek V4 Flash (93%) | Qwen3.5-27B (18.1%) |

## Retrieval Comparison

### SPR ↑

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 76.7% | 36.7% | 33.3% | 30.0% |
| DeepSeek V3.2 | 80.0% | 43.3% | 30.0% | 40.0% |
| Qwen3.5-27B | 86.7% | 36.7% | 23.3% | 40.0% |
| Qwen3.6-35B-A3B | 73.3% | 26.7% | 40.0% | 23.3% |
| GPT-4o-mini | 73.3% | 30.0% | 30.0% | 33.3% |
| GPT-4o | 93.3% | 40.0% | 30.0% | 43.3% |

### Target Dev ↓

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 10.8% | 5.6% | 3.5% | 5.0% |
| DeepSeek V3.2 | 10.4% | 5.7% | 3.5% | 5.2% |
| Qwen3.5-27B | 10.3% | 8.7% | 4.5% | 6.5% |
| Qwen3.6-35B-A3B | 12.5% | 9.3% | 7.2% | 7.6% |
| GPT-4o-mini | 6.3% | 14.1% | 5.2% | 12.2% |
| GPT-4o | 7.8% | 12.7% | 4.7% | 5.8% |

### Model Match ↑

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 98.2% | 0.2% | 0.5% | 1.0% |
| DeepSeek V3.2 | 99.0% | 0.0% | 0.0% | 0.2% |
| Qwen3.5-27B | 100.0% | 11.8% | 11.2% | 12.0% |
| Qwen3.6-35B-A3B | 99.7% | 12.1% | 11.8% | 12.2% |
| GPT-4o-mini | 100.0% | 0.0% | 0.0% | 0.0% |
| GPT-4o | 100.0% | 0.9% | 0.0% | 12.1% |

### Golden Recall ↑

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 94.2% | 0.8% | 0.8% | 1.7% |
| DeepSeek V3.2 | 94.7% | 0.0% | 0.0% | 0.8% |
| Qwen3.5-27B | 94.2% | 22.8% | 22.8% | 22.8% |
| Qwen3.6-35B-A3B | 94.2% | 24.5% | 22.8% | 24.5% |
| GPT-4o-mini | 95.8% | 0.0% | 0.0% | 0.0% |
| GPT-4o | 94.2% | 2.5% | 0.0% | 23.7% |

### First-Pass ↑

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 85.2% | 58.3% | 83.3% | 60.0% |
| DeepSeek V3.2 | 74.1% | 83.3% | 50.0% | 83.3% |
| Qwen3.5-27B | 70.0% | 87.5% | 66.7% | 70.0% |
| Qwen3.6-35B-A3B | 85.2% | 100.0% | 90.0% | 100.0% |
| GPT-4o-mini | 83.3% | 66.7% | 75.0% | 50.0% |
| GPT-4o | 65.0% | 70.0% | 60.0% | 58.3% |

### Schematic ↑

| Model | Ours | NaiveRAG | CritiqueRAG | CRAG |
| :---  | :---: | :---: | :---: | :---: |
| DeepSeek V4 Flash | 76.7% | 36.7% | 33.3% | 30.0% |
| DeepSeek V3.2 | 80.0% | 43.3% | 30.0% | 40.0% |
| Qwen3.5-27B | 86.7% | 36.7% | 23.3% | 40.0% |
| Qwen3.6-35B-A3B | 73.3% | 26.7% | 40.0% | 23.3% |
| GPT-4o-mini | 73.3% | 30.0% | 30.0% | 33.3% |
| GPT-4o | 93.3% | 40.0% | 30.0% | 36.7% |

### Best Model per Method (Retrieval)

| Method | Best SPR | Best Target Dev |
| :--- | :--- | :--- |
| Ours | GPT-4o (93%) | GPT-4o-mini (6.3%) |
| NaiveRAG | DeepSeek V3.2 (43%) | DeepSeek V4 Flash (5.6%) |
| CritiqueRAG | Qwen3.6-35B-A3B (40%) | DeepSeek V4 Flash (3.5%) |
| CRAG | GPT-4o (43%) | DeepSeek V4 Flash (5.0%) |

