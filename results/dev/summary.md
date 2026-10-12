| system | n | EX_all | EX_easy | EX_medium | EX_hard | EX_extra | table_P | table_R | table_F1 | avg_seconds | errors | self_corrections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1: Classical NLP | 200 | 29.0 | 62.0 | 26.0 | 16.0 | 12.0 | 0.883 | 0.942 | 0.894 | 0.03 | 0 | 0 |
| S2: NLP + LLM | 200 | 74.5 | 94.0 | 78.0 | 74.0 | 52.0 | 0.938 | 0.991 | 0.955 | 5.35 | 1 | 4 |
| S3: NLP + LLM + RAG | 200 | 72.5 | 94.0 | 80.0 | 62.0 | 54.0 | 0.953 | 0.987 | 0.963 | 5.22 | 5 | 9 |
| Baseline: LLM + RAG | 200 | 68.5 | 90.0 | 80.0 | 56.0 | 48.0 | 0.961 | 0.974 | 0.961 | 5.01 | 8 | 11 |

Schema-linking F1 of the classical NLP front-end alone (keyword matching, before any SQL generation): 0.894

### Paired significance test (exact McNemar, execution match on the same questions)
| comparison | only first right | only second right | p-value | significant (p<0.05) |
|---|---|---|---|---|
| S1: Classical NLP vs S2: NLP + LLM | 6 | 97 | 0.0000 | yes |
| S2: NLP + LLM vs S3: NLP + LLM + RAG | 17 | 13 | 0.5847 | no |
| Baseline: LLM + RAG vs S3: NLP + LLM + RAG | 6 | 14 | 0.1153 | no |
| Baseline: LLM + RAG vs S2: NLP + LLM | 16 | 28 | 0.0961 | no |