"""E6: probabilistic mixer traversal (taint through CoinJoins).

A CoinJoin hides who paid whom, so plain propagation either stops at it or smears taint evenly over every output.
Both are wrong in different ways. From amounts alone a CoinJoin still leaks two things:

- the equal-valued outputs ("pool" outputs) can belong to any participant: each input links to each of the k pool
  outputs with probability 1/k. That is an honest anonymity set, not a guess;
- every participant also gets change (input − denomination − their share of the fee), and the change amount pins
  an output to its input. A change output with exactly one input that fits is linked with probability 1;
  with several equally fitting inputs, 1/(number of fits).

`links` returns those input→output probabilities. E4 uses them as edge weights through mixing transactions, so a tainted
participant's change comes out tainted and its pool output carries taint/k instead of taint being lost or smeared.
Nothing here reads ground truth; `evaluate` compares the links with it afterwards.
"""
from collections import Counter

import numpy as np
import pandas as pd

SAT = 1e-8
MIN_POOL = 3            # equal outputs needed to call a group a pool
MIN_SLACK_TOL = 2e-6    # BTC; fee-share tolerance floor when the per-participant fee is tiny


def _tx_links(txid: str, ins: list, outs: list, fee: float):
    """ins/outs: [(address, amount)]. Returns (rows, anonymity_set) or None when no equal-output pool is visible."""
    amounts = Counter(round(a, 8) for _, a in outs)
    denom, k = max(amounts.items(), key=lambda kv: (kv[1], kv[0]))
    if k < MIN_POOL or len(ins) < k:
        return None
    pool = [(o, a) for o, a in outs if abs(a - denom) <= SAT / 2]
    resid = [(o, a) for o, a in outs if abs(a - denom) > SAT / 2]
    eligible = [(i, a) for i, a in ins if a >= denom - SAT / 2]
    if len(eligible) < k:
        return None
    rows = []
    p_pool = 1.0 / len(eligible)
    for i, _ in eligible:
        for o, a in pool:
            rows.append((txid, i, o, p_pool, "POOL", a))
    slack = max(fee, 0.0) / k          # expected fee share per participant
    tol = max(0.5 * slack, MIN_SLACK_TOL)
    for o, c in resid:
        fits = [i for i, a in eligible if abs((a - denom - c) - slack) <= tol]
        if fits:
            for i in fits:
                rows.append((txid, i, o, 1.0 / len(fits), "CHANGE", c))
        else:   # no input explains this output: every input that is large enough could have produced it
            big = [i for i, a in ins if a >= c]
            for i in big:
                rows.append((txid, i, o, 1.0 / max(len(big), 1), "UNEXPLAINED", c))
    return rows, k


def links(f, mixer_txids) -> tuple[pd.DataFrame, dict]:
    """Input→output link probabilities for every mixing transaction in `mixer_txids`."""
    cols = ["txid", "src", "dst", "prob", "kind", "amount"]
    mixer_txids = set(mixer_txids)
    if not mixer_txids:
        return pd.DataFrame(columns=cols), {"mixing_transactions": 0, "traversed": 0}
    tin = f.tin[f.tin["txid"].isin(mixer_txids)]
    tout = f.tout[f.tout["txid"].isin(mixer_txids)]
    fee = f.tx.set_index("txid")["fee"]
    ins = {t: list(zip(g["address"], g["amount"])) for t, g in tin.groupby("txid", sort=True)}
    outs = {t: list(zip(g["address"], g["amount"])) for t, g in tout.groupby("txid", sort=True)}
    rows, anon, done = [], {}, 0
    for t in sorted(mixer_txids & set(ins) & set(outs)):
        res = _tx_links(t, ins[t], outs[t], float(fee.get(t, 0.0) or 0.0))
        if res:
            rows += res[0]
            anon[t] = res[1]
            done += 1
    df = pd.DataFrame(rows, columns=cols)
    # a wallet can fund and receive in the same mix; a link from an address to itself carries no information
    df = df[df["src"] != df["dst"]].reset_index(drop=True)
    rep = {"mixing_transactions": len(mixer_txids), "traversed": done,
           "median_anonymity_set": float(np.median(list(anon.values()))) if anon else None,
           "change_links": int((df["kind"] == "CHANGE").sum()), "pool_links": int((df["kind"] == "POOL").sum()),
           "unexplained_links": int((df["kind"] == "UNEXPLAINED").sum())}
    df.attrs["anonymity_set"] = anon
    return df, rep


def evaluate(df: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """Compare links with ground truth (labels indexed by address, column entity_id). Evaluation only."""
    if df.empty:
        return {}
    ent = labels["entity_id"]
    d = df.assign(es=df["src"].map(ent), ed=df["dst"].map(ent))
    d = d.dropna(subset=["es", "ed"])
    d["same"] = d["es"] == d["ed"]
    out = {}
    ch = d[d["kind"] == "CHANGE"]
    if len(ch):
        sure = ch[ch["prob"] >= 0.99]
        out["change_link_precision_p1"] = round(float(sure["same"].mean()), 4) if len(sure) else None
        out["change_links_certain"] = int(len(sure))
        # every change output that really belongs to an input owner: how many did we link to the right input?
        truth = d[(d["kind"] != "POOL") & d["same"]]
        out["change_true_pairs_found"] = int(truth["dst"].nunique())
    pool = d[d["kind"] == "POOL"]
    if len(pool):
        # probability mass the model puts on the true owner of a pool output vs a blind 1/k guess
        tp = pool[pool["same"]]
        out["pool_mean_true_link_prob"] = round(float(tp["prob"].mean()), 4) if len(tp) else None
        out["pool_note"] = "equal outputs are unlinkable from amounts: probability is 1/k by construction"
    return out


def exposure(df: pd.DataFrame, taint, wallets, top: int = 4) -> dict:
    """Per wallet: the mixing transactions it received coins from or sent coins into, with the candidate
    counterparties, their link probability and their taint. Evidence for alerts (not a model input).

    `taint` maps address → E4 taint. Wallets with no mixer link are absent from the result."""
    if df.empty:
        return {}
    wallets = set(wallets)
    anon = df.attrs.get("anonymity_set", {})
    out = {}
    for role, mine, other in (("RECEIVED", "dst", "src"), ("SENT", "src", "dst")):
        sub = df[df[mine].isin(wallets)]
        for (w, t), g in sub.groupby([mine, "txid"], sort=True):
            cands = sorted(({"address": a, "probability": round(float(p), 4), "kind": k,
                             "taint": round(float(taint.get(a, 0.0)), 4)}
                            for a, p, k in zip(g[other], g["prob"], g["kind"])),
                           key=lambda c: (-c["probability"] * c["taint"], -c["probability"], c["address"]))
            out.setdefault(w, []).append({
                "txid": t, "role": role, "anonymity_set": anon.get(t),
                "link_kind": g["kind"].iloc[0], "candidates": cands[:top],
                # taint a received output inherits through the mix: Σ P(input→output) × taint(input)
                "inherited_taint": round(float(sum(c["probability"] * c["taint"] for c in cands)), 4)
                if role == "RECEIVED" else None})
    return out
