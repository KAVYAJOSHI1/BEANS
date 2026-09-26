# External validation: Elliptic (real Bitcoin transactions)

Reproduce: `beans validate-elliptic --download --doc docs/VALIDATION_ELLIPTIC.md` (needs internet once; the files are
checksummed and never committed; the dataset has its own licence). About 1 minute. This page is generated from
`models/elliptic_report.json`, which the Model Card also shows.

## What this does and does not validate

The Elliptic dataset (Weber et al. 2019) has 203,769 real Bitcoin transactions, 234,355 payment-flow
edges and 49 time steps: 4,545 labelled illicit, 42,019 licit, the rest unknown. Its 166
features are **anonymised: no addresses, amounts or IP addresses**. So it cannot exercise BEANS's ingest, clustering (E1),
network layer or action rules. It does test, on real data, the ideas those parts rely on:

1. **the detector recipe**: calibrated LightGBM (`beans/score/fuse.py`) and the E5 GNN features (`beans/engines/e5_gnn.py`)
2. **seed propagation** (E4): does knowing some illicit transactions help find the others?

## 1. Detection (temporal split: train on steps 1-34, test on 35-49)

29,894 labelled training transactions, 16,670 test (1,083 illicit). Calibration on steps
31-34 (held out from fitting). Threshold 0.5. LF = the 93 local features; AF = all 165; graph = degree
and PageRank computed by us; GNN (E5) = SIGN-style 1-2 hop aggregation of the local features.

| Model | Precision | Recall | F1 (illicit) | PR-AUC | ECE |
|---|---|---|---|---|---|
| BEANS LightGBM + calibration (LF) | 0.901 | 0.672 | **0.770** | 0.752 | 0.0216 |
| BEANS LightGBM + calibration (AF) | 0.921 | 0.706 | **0.799** | 0.759 | 0.0175 |
| BEANS LightGBM + calibration (AF + graph) | 0.909 | 0.713 | **0.799** | 0.760 | 0.02 |
| BEANS LightGBM + calibration (LF + GNN (E5)) | 0.803 | 0.721 | **0.760** | 0.755 | 0.0243 |
| BEANS LightGBM + calibration (AF + GNN (E5)) | 0.853 | 0.718 | **0.780** | 0.756 | 0.017 |
| Random forest (LF), re-run here | 0.854 | 0.718 | **0.780** | 0.772 | — |
| Random forest (AF), re-run here | 0.891 | 0.724 | **0.799** | 0.775 | — |

Published on the same split (Weber et al. 2019, Table 1):

| Model | Precision | Recall | F1 |
|---|---|---|---|
| Logistic regression (AF) | 0.404 | 0.593 | 0.481 |
| Random forest (LF) | 0.803 | 0.611 | 0.694 |
| Random forest (AF) | 0.956 | 0.670 | 0.788 |
| Random forest (AF + GCN embeddings) | 0.971 | 0.675 | 0.796 |
| GCN | 0.812 | 0.512 | 0.628 |
| Skip-GCN | 0.812 | 0.623 | 0.705 |

**Reading.** BEANS's recipe reaches illicit F1 0.799, equal to the strongest published baseline (random forest
0.788; our re-run 0.799) and well above the published graph neural networks (GCN 0.628, Skip-GCN 0.705). It does not
beat the random forest. The E5 GNN features do **not** help here (F1 0.780): Elliptic's 72
"aggregated" features already are neighbourhood aggregates, so a second aggregation only adds noise. On the synthetic
wallet graph, where no such features exist, E5 is a clear gain (see the technical write-up). Calibration holds on real
data (ECE 0.0175).

F1 per test time step (all features): 35: 0.97 · 36: 0.90 · 37: 0.74 · 38: 0.93 · 39: 0.90 · 40: 0.75 · 41: 0.95 · 42: 0.86 · 43: 0.00 · 44: 0.06 · 45: 0.00 · 46: 0.00 · 47: 0.00 · 48: 0.00 · 49: 0.03

From step 43 on every model collapses: a large dark market closed and the illicit behaviour changed. Weber et al. report
the same for all their models. A model trained on the past does not catch a new scheme, which is why BEANS pairs the
detector with analyst-feedback retraining and seed propagation.

## 2. Seed propagation on real data

In each test time step, 30 % of the illicit transactions are revealed as seeds (as in the synthetic
benchmark); personalised PageRank from them scores the remaining 755 hidden illicit and
14,877 licit transactions.

| | |
|---|---|
| Hidden illicit transactions within 2 hops of a seed | **50%** |
| Licit transactions within 2 hops of a seed | 5% |
| PR-AUC: detector only | 0.736 |
| PR-AUC: detector + seeds | **0.821** |
| PR-AUC: seeds only | 0.197 (base rate 0.048) |

Seeds are not a detector on their own, but added to the model they lift PR-AUC by
+0.085. The combination rule (`1 − (1 − p)(1 − 0.5·ppr_percentile)` for
transactions within 2 hops of a seed) was fixed before looking at the test results, not tuned on them.

## Limits

- One dataset, one split, labelled by Elliptic's own heuristics; 77% of transactions are unlabelled.
- Transactions only: no address clustering, no network layer, no amounts, so most of what makes BEANS distinctive is
  not tested here.
- Published numbers are quoted from the paper, except the random-forest baseline, which is re-run here.
