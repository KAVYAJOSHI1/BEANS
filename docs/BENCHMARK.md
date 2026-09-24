# BEANS throughput benchmark (roadmap S9)

Machine: x86_64, 8 cores, 15 GB RAM, Python 3.12.3. Each stage runs in its own process; peak memory is its max RSS.

| Observation rows | Transactions | Wallets | Generate | Training run (ingest + engines + training) | Scoring run (ingest + engines, saved models) | Rows/s (scoring) |
|---:|---:|---:|---:|---:|---:|---:|
| 56,637 | 19,405 | 43,994 | 6 s | 38 s · 0.92 GB | 18 s · 0.86 GB | 3,110 |
| 97,979 | 33,725 | 72,757 | 9 s | 59 s · 1.31 GB | 30 s · 1.24 GB | 3,267 |
| 117,447 | 40,306 | 86,103 | 13 s | 79 s · 1.47 GB | 35 s · 1.44 GB | 3,330 |

Training is a one-off on labelled data; operational files are handled by the scoring run.
Reproduce: `.venv/bin/python scripts/benchmark.py 50000 150000 300000`
