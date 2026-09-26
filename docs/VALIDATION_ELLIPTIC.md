# External validation: Elliptic (real Bitcoin transactions)

Reproduce: `beans validate-elliptic --download` (needs internet once; files are checksummed and never committed,
the dataset has its own licence). Takes about 30 s. Output: `models/elliptic_report.json`, also shown on the Model Card.

## What this does and does not validate

The Elliptic dataset (Weber et al. 2019) has 203,769 real Bitcoin transactions, 234,355 payment-flow
edges and 49 time steps: 4,545 labelled illicit, 42,019 licit, the rest unknown. Its 166 features
are **anonymised: no addresses, amounts or IP addresses**. So it cannot exercise BEANS's ingest, clustering (E1),
network layer or action rules. It does test, on real data, the two ideas those parts rely on:

1. **the detector recipe** (calibrated LightGBM, `beans/score/fuse.py`)
2. **seed propagation** (E4): does knowing some illicit transactions help find the others?

## 1. Detection (temporal split: train on steps 1-34, test on 35-49)

29,894 labelled training transactions, 16,670 test (1,083 illicit). Calibration on steps
31-34 (held out from fitting). Threshold 0.5. LF = the 93 local features, AF = all 165, graph = in/out degree,
PageRank and neighbour degree computed by us from the edge list.

| Model | Precision | Recall | F1 (illicit) | PR-AUC | ECE |
|---|---|---|---|---|---|
| BEANS LightGBM + calibration (LF) | 0.901 | 0.672 | **0.770** | 0.752 | 0.0216 |
| BEANS LightGBM + calibration (AF) | 0.921 | 0.706 | **0.799** | 0.759 | 0.0175 |
| BEANS LightGBM + calibration (AF + graph) | 0.909 | 0.713 | **0.799** | 0.760 | 0.02 |
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

**Reading.** BEANS's recipe reaches illicit F1 0.799. That matches the strongest
published baseline (random forest, 0.788; our own re-run of it: 0.799) and is well
above the published graph neural networks (GCN 0.628, Skip-GCN 0.705). It does **not** beat the random forest: the two
are equal within noise. Our graph features add nothing here, because Elliptic's aggregated features already describe
each transaction's neighbourhood. Calibration holds on real data (ECE ≈ 0.0175).

F1 per test time step (AF + graph): 35: 0.96 · 36: 0.88 · 37: 0.75 · 38: 0.92 · 39: 0.91 · 40: 0.76 · 41: 0.95 · 42: 0.86 · 43: 0.00 · 44: 0.11 · 45: 0.00 · 46: 0.20 · 47: 0.00 · 48: 0.05 · 49: 0.03

From step 43 on, every model collapses. A large dark market closed at that point and the illicit behaviour changed;
Weber et al. report the same for all their models. A model trained on the past does not catch a new scheme, which is why
BEANS pairs the detector with analyst feedback (retraining on confirmed / false-positive verdicts) and seed propagation.

## 2. Seed propagation on real data

In each test time step, 30 % of the illicit transactions are revealed as seeds (as in the synthetic benchmark);
personalised PageRank from them scores the remaining 755 hidden illicit and 14,877 licit
transactions.

| | |
|---|---|
| Hidden illicit transactions within 2 hops of a seed | **50%** |
| Licit transactions within 2 hops of a seed | 5% |
| PR-AUC: detector only | 0.740 |
| PR-AUC: detector + seeds | **0.823** |
| PR-AUC: seeds only | 0.197 (base rate 0.048) |

Seeds are not a detector on their own, but added to the model they lift PR-AUC by
+0.083. The combination rule (`1 − (1 − p)(1 − 0.5·ppr_percentile)` for
transactions within 2 hops of a seed) was fixed before looking at the test results, not tuned on them. This is the real-data
counterpart of E4.

## Limits

- One dataset, one split, labelled by Elliptic's own heuristics; 77 % of transactions are unlabelled.
- Transactions only: no address clustering, no network layer, no amounts, so most of what makes BEANS distinctive is
  not tested here.
- The published numbers are quoted from the paper, not re-derived, except the random-forest baseline, which we re-ran.
