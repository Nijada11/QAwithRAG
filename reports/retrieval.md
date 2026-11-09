# Retrieval: 41 answerable questions, top 5

| Setup | Hit@1 | Hit@3 | Hit@5 | MRR@5 | p50 latency |
|---|---|---|---|---|---|
| 600w vector (baseline) | 49% | 78% | 80% | 0.62 | 19 ms |
| 600w keyword (BM25) | 51% | 76% | 83% | 0.63 | 1 ms |
| 600w hybrid | 56% | 78% | 88% | 0.68 | 23 ms |
| 600w hybrid + rerank | 54% | 78% | 85% | 0.66 | 1159 ms |
| 250w vector | 44% | 73% | 83% | 0.59 | 19 ms |
| 250w keyword (BM25) | 39% | 73% | 78% | 0.54 | 2 ms |
| 250w hybrid | 46% | 80% | 95% | 0.65 | 24 ms |
| 250w hybrid + rerank | 49% | 73% | 80% | 0.61 | 932 ms |
