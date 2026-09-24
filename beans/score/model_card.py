"""Model card: measure the current pipeline output against the synthetic ground truth.

Reads what the pipeline stored in DuckDB (wallet_profiles, alerts, seeds) and the generator's labels.csv,
computes metrics, and writes models/model_card.json, which the dashboard's Model Card page renders.
Only measured values are written. If something can't be measured from stored outputs, it's listed under
`not_measured` rather than estimated.
"""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sklearn.metrics import (average_precision_score, completeness_score, homogeneity_score,
                             precision_score, recall_score, roc_auc_score)

from beans.config import settings

BENIGN = {"NORMAL", "EXCHANGE", "EXCHANGE_SWEEP", "MERCHANT", "MINER"}
CARD_PATH = settings.MODELS_DIR / "model_card.json"


def _labels(path: Path) -> tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """address -> typology, address -> true cluster, txid -> typology (illicit wins if an address has several)."""
    typ, clus, tx_typ = {}, {}, {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            a, t = row["address"], row["typology"].upper()
            tx_typ[row["txid"]] = t
            if a not in typ or typ[a] in BENIGN:
                typ[a], clus[a] = t, row.get("cluster_id") or ""
    return typ, clus, tx_typ


def _precision_at(y_true, scores, k: int) -> Optional[float]:
    if not y_true or k <= 0:
        return None
    ranked = sorted(zip(scores, y_true), key=lambda x: -x[0])[:k]
    return round(sum(t for _, t in ranked) / len(ranked), 4)


def build_model_card(conn, labels_path: Path) -> Dict[str, Any]:
    typ, true_cluster, tx_typ = _labels(labels_path)

    wallets = {r[0]: (float(r[1] or 0.0), r[2]) for r in conn.execute(
        "SELECT address, risk_score, cluster_id FROM wallet_profiles").fetchall()}
    alerts = conn.execute("SELECT entity_id, alert_type, risk_score, evidence FROM alerts").fetchall()
    alerted = {a[0]: a for a in alerts}
    seeds = {r[0] for r in conn.execute("SELECT address FROM seeds").fetchall()}
    labelled_seeds = [s for s in seeds if s in typ]

    universe = sorted(set(wallets) | set(alerted))
    y = [1 if typ.get(a, "NORMAL") not in BENIGN else 0 for a in universe]
    score = [max(wallets.get(a, (0.0, None))[0], float(alerted[a][2]) if a in alerted else 0.0) for a in universe]
    flagged = [1 if a in alerted else 0 for a in universe]
    n_pos = sum(y)

    fusion: Dict[str, Any] = {"wallets_evaluated": len(universe), "illicit_wallets": n_pos, "alerts": len(alerts)}
    metrics = []
    if n_pos and n_pos < len(y):
        fusion.update({
            "pr_auc": round(average_precision_score(y, score), 4),
            "roc_auc": round(roc_auc_score(y, score), 4),
            "precision_at_10": _precision_at(y, score, 10),
            "precision_at_50": _precision_at(y, score, 50),
            "alert_precision": round(precision_score(y, flagged, zero_division=0), 4),
            "alert_recall": round(recall_score(y, flagged, zero_division=0), 4),
            "base_rate": round(n_pos / len(y), 4),
        })
        metrics += [
            {"engine": "Fused risk score", "metric": "PR-AUC (wallet illicit vs benign)", "score": fusion["pr_auc"],
             "target": ">= 0.90", "baseline": fusion["base_rate"]},
            {"engine": "Fused risk score", "metric": "ROC-AUC", "score": fusion["roc_auc"], "target": ">= 0.90"},
            {"engine": "Alert list", "metric": "Precision (alerted wallets that are illicit)", "score": fusion["alert_precision"]},
            {"engine": "Alert list", "metric": "Recall (illicit wallets that were alerted)", "score": fusion["alert_recall"]},
        ]
        if fusion["precision_at_10"] is not None:
            metrics.append({"engine": "Ranking", "metric": "Precision@10", "score": fusion["precision_at_10"]})

    # E4: can risk reach illicit wallets that were NOT given as seeds?
    hidden = [a for a in universe if typ.get(a, "NORMAL") not in BENIGN and a not in seeds]
    e4 = {"seeds_total": len(seeds), "seeds_in_labels": len(labelled_seeds), "hidden_illicit_wallets": len(hidden)}
    if hidden:
        e4["hidden_recall_alerted"] = round(sum(1 for a in hidden if a in alerted) / len(hidden), 4)
        metrics.append({"engine": "E4 seed propagation", "metric": "Recall of hidden (non-seed) illicit wallets",
                        "score": e4["hidden_recall_alerted"], "target": ">= 0.75"})

    # E1: are predicted clusters pure w.r.t. true illicit entities?
    illicit_clustered = [a for a in universe if typ.get(a, "NORMAL") not in BENIGN and wallets.get(a, (0, None))[1]]
    e1: Dict[str, Any] = {"illicit_wallets_with_cluster": len(illicit_clustered)}
    if len(illicit_clustered) >= 2:
        t = [true_cluster.get(a, "") for a in illicit_clustered]
        p = [wallets[a][1] for a in illicit_clustered]
        e1.update({"homogeneity": round(homogeneity_score(t, p), 4), "completeness": round(completeness_score(t, p), 4),
                   "predicted_clusters": len(set(p)), "true_entities": len(set(t))})
        metrics.append({"engine": "E1 clustering (CIOH)", "metric": "Completeness (entity kept together)",
                        "score": e1["completeness"], "target": ">= 0.80"})

    # E3: typology of alerted wallets vs their true typology
    pairs = [(typ.get(a, "NORMAL"), row[1].replace("_PATTERN", "")) for a, row in alerted.items()]
    labels_order = sorted({x for p in pairs for x in p})
    matrix = [[sum(1 for t, pr in pairs if t == lt and pr == lp) for lp in labels_order] for lt in labels_order]
    typology_accuracy = round(sum(1 for t, pr in pairs if t == pr) / len(pairs), 4) if pairs else None
    if typology_accuracy is not None:
        metrics.append({"engine": "E3 typology", "metric": "Accuracy on alerted wallets", "score": typology_accuracy})

    # Illicit transactions caught (alert evidence points at the transaction)
    alert_txids = set()
    for a in alerts:
        try:
            ev = json.loads(a[3]) if isinstance(a[3], str) else (a[3] or {})
            if ev.get("txid"):
                alert_txids.add(ev["txid"])
        except ValueError:
            pass
    illicit_txs = [t for t, ty in tx_typ.items() if ty not in BENIGN]
    per_typology = {}
    for ty, n in Counter(tx_typ[t] for t in illicit_txs).items():
        caught = sum(1 for t in illicit_txs if tx_typ[t] == ty and t in alert_txids)
        per_typology[ty] = {"transactions": n, "caught_by_alert_evidence": caught}

    card = {
        "model_overview": {
            "name": "BEANS pipeline: measured against synthetic ground truth",
            "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "labels_file": labels_path.name,
            "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest()[:16],
            "wallets": len(universe), "illicit_wallets": n_pos, "alerts": len(alerts),
        },
        "engine_metrics": metrics,
        "confusion_matrix": {"labels": labels_order, "matrix": matrix} if labels_order else None,
        "feature_importances": [],
        "fusion_detail": fusion,
        "e1_clustering": e1,
        "e4_propagation": e4,
        "illicit_transactions_by_typology": per_typology,
        "not_measured": {
            "E2 anomaly (separately)": "per-wallet anomaly scores are not stored by the pipeline yet",
            "feature importance / SHAP global": "fusion model is not persisted yet",
            "calibration (ECE)": "requires a calibrated fusion model",
        },
    }
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_PATH.write_text(json.dumps(card, indent=2))
    return card


def default_labels_path() -> Optional[Path]:
    """labels.csv of the most recently generated synthetic dataset."""
    candidates = sorted(settings.SYNTH_DIR.glob("*/labels.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
