# BEANS large-scale benchmark (~1M rows)

Machine: x86_64, 8 cores, 15 GB RAM.
10 independent synthetic files (seeds 1-10) loaded into one database, then scored with the shipped models.

| | |
|---|---|
| Observation rows | **980,803** |
| Transactions / wallets | 336,260 / 726,035 |
| Ingest (`beans ingest … --no-score`, chunked) | **96 s** · peak 0.88 GB · 10,170 rows/s |
| Scoring (`beans score`, all engines) | **190 s** · peak 5.29 GB · 5,174 rows/s |
| End to end | **286 s** · 3,429 rows/s |

Scoring stages (cumulative seconds): tx_features 25 s · e3 44 s · e2 108 s · e4 126 s · e5 132 s · fusion 158 s · counterfactuals 163 s · actions 181 s.

Reproduce: `.venv/bin/python scripts/benchmark_1m.py --files 10`
