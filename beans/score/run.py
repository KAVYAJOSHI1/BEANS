"""ML orchestrator: features → E3 → E1 → E2 → E4 → fusion → SHAP → alerts, over the whole database.

Ground truth (labels_address / labels_tx tables, loaded from a synthetic dataset's sidecar files) is used only
as training targets and for evaluation. When it is absent (e.g. an operational file), the models persisted
by the last training run are applied instead.
"""
import hashlib
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pyarrow as pa

from beans.config import settings
from beans.decision import actions as directives
from beans.engines import e1_cluster, e2_anomaly, e3_peelmix, e4_propagate
from beans.explain.reasons import reasons_from_shap
from beans.explain.shap_explain import explain
from beans.features.extractors import (WALLET_NETWORK_COLS, TX_NETWORK_COLS, load_frames, tx_features,
                                       wallet_features)
from beans.score import fuse

REPORT_PATH = settings.MODELS_DIR / "training_report.json"
ALERT_MIN_P = 0.40
MAX_ALERTS = 300
P_COLS = [f"p_{c}" for c in e3_peelmix.CLASSES if c != "normal"]


def _table(conn, name: str) -> bool:
    return bool(conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0])


def _severity(risk: float) -> str:
    return "CRITICAL" if risk >= 85 else "HIGH" if risk >= 65 else "MEDIUM" if risk >= 40 else "LOW"


def run_ml(store) -> dict:
    t0 = time.time()
    conn = store.get_connection()
    try:
        result = _run(conn, t0)
    finally:
        conn.close()
    from beans.alerting import webhooks   # push new high-severity alerts to configured SIEM webhooks
    webhooks.dispatch_in_background(store)
    return result


def _run(conn, t0) -> dict:
    f = load_frames(conn)
    if f.tx.empty:
        return {"status": "empty"}
    timings = {}
    X_tx = tx_features(f)
    timings["tx_features"] = round(time.time() - t0, 2)

    labels_tx = labels_addr = None
    if _table(conn, "labels_tx"):
        labels_tx = conn.execute("SELECT txid, tx_class, entity_id FROM labels_tx ORDER BY txid").df().set_index("txid")
    if _table(conn, "labels_address"):
        labels_addr = conn.execute("SELECT address, typology, entity_id, CAST(is_illicit AS INT) AS is_illicit "
                                   "FROM labels_address ORDER BY address").df().set_index("address")
    seeds = {r[0] for r in conn.execute("SELECT address FROM seeds").fetchall()}
    # analyst verdicts (latest per wallet): CONFIRMED → illicit, FALSE_POSITIVE → legitimate (roadmap S5)
    feedback = {r[0]: int(r[1] == "TRUE_POSITIVE") for r in conn.execute(
        "SELECT entity_id, arg_max(user_label, created_at) FROM feedback WHERE entity_id IS NOT NULL GROUP BY 1").fetchall()}

    # ---- E3: transaction shape
    probs, e3_rep = e3_peelmix.run(X_tx, labels_tx if labels_tx is not None and len(labels_tx) else None)
    timings["e3"] = round(time.time() - t0, 2)

    # ---- E1: clustering (CoinJoins excluded from CIOH)
    coinjoin = set(probs.index[probs["p_coinjoin"] > 0.5])
    clusters, e1_rep = e1_cluster.cluster(f, X_tx, coinjoin)

    # ---- wallet features + E3 aggregates + cluster aggregates
    W = wallet_features(f, X_tx)
    memb = pd.concat([f.tin[["txid", "address"]], f.tout[["txid", "address"]]]).drop_duplicates()
    pj = memb.join(probs[P_COLS], on="txid")
    for c in P_COLS:
        W[f"max_{c}"] = pj.groupby("address")[c].max().reindex(W.index).fillna(0)
    W["cluster_id"] = clusters.reindex(W.index).fillna("SOLO")
    cg = W.groupby("cluster_id")
    W["log_cluster_size"] = np.log1p(cg["n_recv"].transform("size"))
    W["cluster_max_p_peel"] = cg["max_p_peel"].transform("max")
    W["cluster_max_p_coinjoin"] = cg["max_p_coinjoin"].transform("max")
    W["cluster_share_risky"] = cg["share_risky_asn"].transform("mean")
    W["cluster_n_countries"] = cg["n_spend_countries"].transform("sum").clip(upper=50)

    # ---- E2: anomaly on behaviour + network (no model outputs)
    behaviour = [c for c in W.columns if c not in ("cluster_id",) and not c.startswith(("max_p_", "cluster_"))]
    W["anomaly"] = e2_anomaly.anomaly(W, behaviour)
    timings["e2"] = round(time.time() - t0, 2)

    # ---- E4: propagation from seeds
    G = e4_propagate.graph(f)
    e4df, e4info = e4_propagate.propagate(G, seeds)
    W = W.join(e4df, how="left")
    W[["ppr", "ppr_reverse", "taint"]] = W[["ppr", "ppr_reverse", "taint"]].fillna(0)
    W[["hops_from_seed", "hops_to_seed"]] = W[["hops_from_seed", "hops_to_seed"]].fillna(99).clip(upper=20)
    # a CIOH cluster is one owner: wallets sharing a cluster with a seed count as reached (evaluation + evidence).
    # Not a model input: in A/B tests, cluster-level seed features made the model over-trust cluster membership.
    seed_clusters = set(W.loc[W.index.isin(seeds), "cluster_id"])
    in_seed_cluster = W["cluster_id"].isin(seed_clusters)
    timings["e4"] = round(time.time() - t0, 2)

    # ---- E1 embeddings (suggestions only)
    emb = e1_cluster.embedding_suggestions(f, clusters, W)
    e1_rep.update({k: v for k, v in emb.items() if k != "group_of"})

    # ---- fusion
    feats = [c for c in W.columns if c != "cluster_id"]
    Xw = W[feats].replace([np.inf, -np.inf], 0).fillna(0)
    network_cols = WALLET_NETWORK_COLS + ["cluster_share_risky", "cluster_n_countries"]
    fusion_rep, trained = {}, False
    fb = pd.Series(feedback, dtype=float).reindex(Xw.index).dropna()
    if labels_addr is not None and len(labels_addr):
        lab = labels_addr.reindex(Xw.index)
        lab.loc[fb.index, "is_illicit"] = fb.values                      # the analyst's verdict wins
        lab.loc[fb.index, "entity_id"] = lab.loc[fb.index, "entity_id"].fillna(pd.Series("fb:" + fb.index, index=fb.index))
        lab.loc[fb.index, "typology"] = lab.loc[fb.index, "typology"].fillna("ANALYST_CONFIRMED")
        known = lab["is_illicit"].notna()
        weights = pd.Series(1.0, index=Xw.index)
        weights.loc[fb.index] = 5.0
        p, typ, fusion_rep = fuse.train(Xw[known], lab.loc[known, "is_illicit"], lab.loc[known, "entity_id"],
                                        lab.loc[known, "typology"], network_cols, weights[known])
        if (~known).any():
            p2, t2, _ = fuse.predict(Xw[~known])
            p, typ = pd.concat([p, p2]), pd.concat([typ, t2])
        trained = True
    elif len(fb) and fuse.training_set() is not None:
        # operational data: add the analyst's verdicts to the saved training set and retrain (active learning)
        base = fuse.training_set()
        cols = [c for c in base.columns if not c.startswith("_")]
        add = Xw.loc[fb.index].reindex(columns=cols, fill_value=0)
        Xa = pd.concat([base[cols], add])
        Xa.index = range(len(Xa))
        ya = pd.Series(np.r_[base["_y"].values, fb.values], index=Xa.index)
        ga = pd.Series(np.r_[base["_group"].values, ("fb:" + fb.index).values], index=Xa.index)
        ta = pd.Series(np.r_[base["_typology"].values, np.where(fb.values == 1, "ANALYST_CONFIRMED", "NORMAL")], index=Xa.index)
        wa = pd.Series(np.r_[base["_weight"].values, np.full(len(fb), 5.0)], index=Xa.index)
        _, _, fusion_rep = fuse.train(Xa, ya, ga, ta, network_cols, wa)
        p, typ, _ = fuse.predict(Xw)
        trained = True
    else:
        p, typ, fusion_rep = fuse.predict(Xw)
    fusion_rep["analyst_feedback_used"] = int(len(fb))
    p, typ = p.reindex(Xw.index).fillna(0), typ.reindex(Xw.index).fillna("UNKNOWN")
    timings["fusion"] = round(time.time() - t0, 2)

    # ---- alerts: one per cluster (its riskiest wallet), highest risk first
    W["p"], W["typology_pred"] = p, typ
    cand = W[W["p"] >= ALERT_MIN_P].sort_values("p", ascending=False)
    cand = cand[~cand["cluster_id"].duplicated() | cand["cluster_id"].str.startswith("SOLO")].head(MAX_ALERTS)
    shap_map, global_imp = explain(fuse.final_model(), Xw.loc[cand.index]) if len(cand) else ({}, [])
    if not global_imp and fuse.final_model() is not None:
        _, global_imp = explain(fuse.final_model(), Xw.sample(min(500, len(Xw)), random_state=1))
    alerts = _build_alerts(cand, W, X_tx, probs, f, e4info, shap_map)
    directives.recommend(alerts, W, f, directives.load_known(conn))
    timings["actions"] = round(time.time() - t0, 2)
    _write(conn, W, probs, alerts)
    timings["total"] = round(time.time() - t0, 2)

    report = {
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "trained": trained,
        "transactions": int(len(X_tx)), "wallets": int(len(W)), "seeds": len(seeds),
        "seeds_in_graph": e4info.get("seeds_in_graph", 0), "alerts": len(alerts),
        "e3": e3_rep, "e1": e1_rep, "fusion": fusion_rep, "global_importance": global_imp, "timings_s": timings,
        "feature_count": len(feats), "network_features": network_cols + TX_NETWORK_COLS,
    }
    if labels_addr is not None and len(labels_addr):
        report["e1"].update(_cluster_quality(W, labels_addr))
        report["e4"] = _propagation_quality(W, labels_addr, seeds, in_seed_cluster)
        report["alert_quality"] = _alert_quality(alerts, labels_addr)
    report["actions"] = {k: int(v) for k, v in pd.Series([a["recommended_action"]["action"] for a in alerts]).value_counts().items()}
    settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    from beans.score.model_card import build_model_card
    build_model_card(conn)
    return {"total_transactions": int(len(X_tx)), "wallets": int(len(W)),
            "clusters_computed": e1_rep.get("clusters"), "alerts_generated": len(alerts),
            "seeds_propagated": len(seeds), "trained": trained, "seconds": timings["total"]}


def _build_alerts(cand, W, X_tx, probs, f, e4info, shap_map) -> list:
    spy = f.spy.set_index("txid")
    tx_ts = f.tx.set_index("txid")["ts"]
    chain_id = X_tx.attrs.get("peel_chain_id", {})
    chains = {}
    for t, c in chain_id.items():
        chains.setdefault(c, []).append(t)
    txs_of = pd.concat([f.tin[["txid", "address", "ts"]], f.tout[["txid", "address", "ts"]]]).drop_duplicates(["txid", "address"])
    txs_of = txs_of[txs_of["address"].isin(cand.index)].join(probs[["p_normal"]], on="txid")
    cluster_size = W.groupby("cluster_id").size()
    alerts = []
    for rank, (addr, w) in enumerate(cand.iterrows(), 1):
        mine = txs_of[txs_of["address"] == addr].sort_values(["p_normal", "ts"])
        key_tx = mine["txid"].iloc[0] if len(mine) else None
        s = spy.loc[key_tx] if key_tx is not None and key_tx in spy.index else None
        path = e4info["path"](addr) if e4info and w["hops_from_seed"] < 20 else []
        chain = sorted(chains.get(chain_id.get(key_tx), []), key=lambda t: tx_ts[t]) if key_tx in chain_id else None
        prob = float(w["p"])
        risk = round(100 * prob, 1)
        flags = [w["anomaly"] > 0.9, max(w[f"max_{c}"] for c in P_COLS) > 0.5,
                 w["taint"] > 0.05 or w["hops_from_seed"] <= 3, w["share_risky_asn"] > 0]
        decision = prob >= 0.5
        agreement = sum(fl == decision for fl in flags) / len(flags)
        completeness = np.mean([w["n_spend"] > 0 or w["n_recv"] > 0, s is not None, cluster_size.get(w["cluster_id"], 1) > 1])
        confidence = round(float(np.clip(0.5 * abs(2 * prob - 1) + 0.3 * agreement + 0.2 * completeness, 0, 1)), 3)
        typology = str(w["typology_pred"])
        contribs = shap_map.get(addr, [])
        alerts.append({
            "alert_id": "A-W-" + hashlib.sha1(addr.encode()).hexdigest()[:10], "rank": rank, "entity_id": addr,
            "entity_type": "WALLET", "alert_type": f"{typology}_PATTERN", "risk_score": risk,
            "calibrated_confidence": confidence, "severity": _severity(risk),
            "reasons": reasons_from_shap(contribs, typology, prob),
            "shap_top_features": contribs,
            "engine_scores": {"fused_probability": round(prob, 4), "e2_anomaly": round(float(w["anomaly"]), 4),
                              "e3_max_peel": round(float(w["max_p_peel"]), 4),
                              "e3_max_coinjoin": round(float(w["max_p_coinjoin"]), 4),
                              "e3_max_fan_out": round(float(w["max_p_fan_out"]), 4),
                              "e4_taint": round(float(w["taint"]), 4), "e4_ppr": round(float(w["ppr"]), 4),
                              "network_risky_share": round(float(w["share_risky_asn"]), 4)},
            "evidence": {
                "txid": key_tx, "top_txids": mine["txid"].head(8).tolist(),
                "first_spy_ip": None if s is None else s["spy_ip"],
                "first_spy_confidence": None if s is None or pd.isna(s["spy_delta"]) else round(float(1 - math.exp(-s["spy_delta"] / 1.5)), 3),
                "first_spy_asn_type": None if s is None else s["spy_asn_type"],
                "path_to_seed": path, "peel_chain": chain, "cluster_id": w["cluster_id"],
                "cluster_size": int(cluster_size.get(w["cluster_id"], 1)),
            },
        })
    return alerts


def _write(conn, W, probs, alerts):
    kept = conn.execute("SELECT entity_id, status, assigned_to FROM alerts WHERE status != 'OPEN' OR assigned_to != 'Unassigned'").fetchall()
    conn.execute("DELETE FROM alerts")
    if alerts:
        tab = pa.Table.from_pylist([{
            "alert_id": a["alert_id"], "entity_id": a["entity_id"], "entity_type": a["entity_type"],
            "alert_type": a["alert_type"], "risk_score": a["risk_score"], "calibrated_confidence": a["calibrated_confidence"],
            "severity": a["severity"], "reasons": a["reasons"], "shap_top_features": json.dumps(a["shap_top_features"]),
            "engine_scores": json.dumps(a["engine_scores"]), "evidence": json.dumps(a["evidence"], default=str),
            "recommended_action": json.dumps(a.get("recommended_action") or {}, default=str),
        } for a in alerts])
        conn.register("alerts_in", tab)
        conn.execute("""INSERT INTO alerts (alert_id, entity_id, entity_type, alert_type, risk_score, calibrated_confidence,
                        severity, reasons, shap_top_features, engine_scores, evidence, recommended_action)
                        SELECT alert_id, entity_id, entity_type, alert_type, risk_score, calibrated_confidence, severity,
                        reasons, shap_top_features, engine_scores, evidence, recommended_action FROM alerts_in""")
        for eid, st, who in kept:
            conn.execute("UPDATE alerts SET status = ?, assigned_to = ? WHERE entity_id = ?", [st, who, eid])

    prof = pd.DataFrame({
        "address": W.index, "transaction_count": (W["n_recv"] + W["n_spend"]).astype(int).values,
        "total_received": W["recv_btc"].values, "total_sent": W["sent_btc"].values,
        "balance": (W["recv_btc"] - W["sent_btc"]).values, "risk_score": (100 * W["p"]).round(1).values,
        "threat_classification": np.where(W["p"] >= ALERT_MIN_P, W["typology_pred"], "NORMAL"),
        "cluster_id": W["cluster_id"].values,
    })
    conn.execute("DELETE FROM wallet_profiles")
    conn.register("prof_in", prof)
    conn.execute("""INSERT INTO wallet_profiles (address, transaction_count, total_received, total_sent, balance,
                    risk_score, threat_classification, cluster_id)
                    SELECT address, transaction_count, total_received, total_sent, balance, risk_score,
                    threat_classification, cluster_id FROM prof_in""")
    scores = W[["p", "typology_pred", "cluster_id", "anomaly", "ppr", "ppr_reverse", "taint", "hops_from_seed",
                "hops_to_seed", "max_p_peel", "max_p_coinjoin", "share_risky_asn"]].reset_index(names="address")
    conn.execute("CREATE OR REPLACE TABLE wallet_scores AS SELECT * FROM scores")
    txs = probs.reset_index(names="txid")
    conn.execute("CREATE OR REPLACE TABLE tx_scores AS SELECT * FROM txs")


def _cluster_quality(W, labels) -> dict:
    from sklearn.metrics import completeness_score, homogeneity_score
    lab = labels.reindex(W.index).dropna(subset=["entity_id"])
    ill = lab[lab["is_illicit"] == 1]
    out = {"homogeneity_all": round(float(homogeneity_score(lab["entity_id"], W.loc[lab.index, "cluster_id"])), 4)}
    if len(ill) > 1:
        out["homogeneity_illicit"] = round(float(homogeneity_score(ill["entity_id"], W.loc[ill.index, "cluster_id"])), 4)
        out["completeness_illicit"] = round(float(completeness_score(ill["entity_id"], W.loc[ill.index, "cluster_id"])), 4)
    return out


def _propagation_quality(W, labels, seeds, in_seed_cluster) -> dict:
    lab = labels.reindex(W.index)
    hidden = lab[(lab["is_illicit"] == 1) & (~lab.index.isin(seeds))].index
    legit = lab[lab["is_illicit"] == 0].index
    if not len(hidden):
        return {}
    reach = lambda idx: float(((W.loc[idx, "taint"] > 0.01) | (W.loc[idx, "hops_from_seed"] <= 4) |
                               (W.loc[idx, "hops_to_seed"] <= 4) | in_seed_cluster.loc[idx]).mean())
    return {"hidden_illicit_wallets": int(len(hidden)), "hidden_reached": round(reach(hidden), 4),
            "legit_reached": round(reach(legit), 4), "hidden_flagged_p50": round(float((W.loc[hidden, "p"] >= 0.5).mean()), 4)}


def _alert_quality(alerts, labels) -> dict:
    if not alerts:
        return {"alerts": 0}
    ents = [a["entity_id"] for a in alerts]
    lab = labels.reindex(ents)
    hit = lab["is_illicit"] == 1
    ill_entities = labels[labels["is_illicit"] == 1]["entity_id"].nunique()
    return {"alerts": len(alerts), "alert_precision": round(float(hit.mean()), 4),
            "illicit_entities_alerted": int(lab[hit]["entity_id"].nunique()), "illicit_entities_total": int(ill_entities),
            "entity_recall": round(float(lab[hit]["entity_id"].nunique() / max(ill_entities, 1)), 4),
            "precision_top10": round(float(hit.head(10).mean()), 4)}
