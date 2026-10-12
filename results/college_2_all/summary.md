| system | n | EX_all | EX_easy | EX_medium | EX_hard | EX_extra | table_P | table_R | table_F1 | avg_seconds | errors | self_corrections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1: Classical NLP | 170 | 16.5 | 41.7 | 17.3 | 7.6 | 14.3 | 0.674 | 0.973 | 0.769 | 0.0 | 0 | 0 |
| S2: NLP + LLM | 170 | 68.2 | 79.2 | 78.8 | 54.5 | 71.4 | 0.853 | 0.994 | 0.902 | 5.81 | 0 | 3 |
| S3: NLP + LLM + RAG | 170 | 77.6 | 83.3 | 84.6 | 71.2 | 75.0 | 0.917 | 0.999 | 0.945 | 5.31 | 1 | 2 |
| Baseline: LLM + RAG | 170 | 80.6 | 87.5 | 92.3 | 68.2 | 82.1 | 0.965 | 0.99 | 0.973 | 4.87 | 1 | 3 |

Schema-linking F1 of the classical NLP front-end alone (keyword matching, before any SQL generation): 0.769

### Paired significance test (exact McNemar, execution match on the same questions)
| comparison | only first right | only second right | p-value | significant (p<0.05) |
|---|---|---|---|---|
| S1: Classical NLP vs S2: NLP + LLM | 0 | 88 | 0.0000 | yes |
| S2: NLP + LLM vs S3: NLP + LLM + RAG | 6 | 22 | 0.0037 | yes |
| Baseline: LLM + RAG vs S3: NLP + LLM + RAG | 11 | 6 | 0.3323 | no |
| Baseline: LLM + RAG vs S2: NLP + LLM | 25 | 4 | 0.0001 | yes |