# BEANS throughput benchmark (roadmap S9)

Machine: x86_64, 8 cores, 15 GB RAM, Python 3.12.3. Each stage runs in its own process; peak memory is its max RSS.

| Observation rows | Transactions | Wallets | Generate | Training run (ingest + engines + training) | Scoring run (ingest + engines, saved models) | Rows/s (scoring) |
|---:|---:|---:|---:|---:|---:|---:|
| 53,486 | 18,331 | 42,205 | 7 s | 52 s · 0.76 GB | 21 s · 0.71 GB | 2,495 |
| 97,979 | 33,725 | 72,757 | 13 s | 86 s · 1.28 GB | 35 s · 1.17 GB | 2,788 |

Training is a one-off on labelled data; operational files are handled by the scoring run.
Reproduce: `.venv/bin/python scripts/benchmark.py 40000 150000`

About one million rows (several files, chunked ingest + one scoring pass): [BENCHMARK_1M.md](BENCHMARK_1M.md)
