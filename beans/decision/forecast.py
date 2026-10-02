"""E7: cash-out forecast. Where will this money probably be deposited, and when?

Alerts are reactive: the legal draft is written after the deposit. A freeze only works while the money is still on the
exchange, so the useful question is the one before it: *this wallet still holds coins; how long until it cashes out,
and at which exchange?* The forecast is empirical, not a black box:

- the sample is every cash-out already observed among this database's alerts (wallet → known exchange, with the
  delay since the wallet received the coins);
- timing: quantiles of the delays of alerts with the same predicted typology (all alerts if too few);
- destination: exchange counts of the same typology plus the actor's own earlier cash-outs (same CIOH cluster,
  weighted ×3), smoothed so unseen exchanges keep a small probability;
- for the alert being forecast, its own cluster is left out of the typology sample, so the same procedure scores
  forecasts for already-cashed-out alerts honestly (leave-one-actor-out backtest, `backtest`).

Nothing here reads ground truth. Wallets with a balance and no deposit yet get a predicted window
(last receipt + p25 … p75) to compare with the latest data time; that is the countdown for the analyst.
"""
from collections import Counter
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

MIN_TYPOLOGY_SAMPLES = 5    # below this the typology sample is replaced by all observed cash-outs
MIN_SAMPLES = 3             # below this no forecast is made
ACTOR_WEIGHT = 3.0
SMOOTHING = 0.5             # pseudo-count per known exchange
MIN_BALANCE = 1e-4


def _first_deposit(a: dict) -> Optional[dict]:
    hits = [h for h in ((a.get("recommended_action") or {}).get("vasp_exposure") or [])
            if h.get("minutes_after_receipt") is not None]
    return min(hits, key=lambda h: h["deposit_ts"]) if hits else None


def _quantiles(delays: List[float]) -> Dict[str, float]:
    q = np.percentile(delays, [10, 25, 50, 75, 90])
    return dict(zip(("p10", "p25", "p50", "p75", "p90"), (round(float(x), 1) for x in q)))


def _sample(pool: List[dict], me: dict) -> List[dict]:
    """Observed cash-outs usable for `me`: other actors, same typology when there are enough of them."""
    other = [s for s in pool if s["cluster"] != me["cluster"]]
    same = [s for s in other if s["typology"] == me["typology"]]
    return same if len(same) >= MIN_TYPOLOGY_SAMPLES else other


def _destinations(pool: List[dict], me: dict, sample: List[dict], exchanges: List[str]) -> List[dict]:
    typ = Counter(s["vasp"] for s in sample)
    own = Counter(s["vasp"] for s in pool if s["cluster"] == me["cluster"] and s["alert_id"] != me["alert_id"])
    score = {v: SMOOTHING + typ.get(v, 0) + ACTOR_WEIGHT * own.get(v, 0) for v in set(exchanges) | set(typ) | set(own)}
    tot = sum(score.values())
    return sorted(({"vasp": v, "probability": round(x / tot, 4), "typology_deposits": typ.get(v, 0),
                    "actor_deposits": own.get(v, 0)} for v, x in score.items()),
                  key=lambda d: (-d["probability"], d["vasp"]))


def attach(alerts: List[dict], W: pd.DataFrame, f, known: Dict[str, dict], now=None) -> dict:
    """Attach `cashout_forecast` to each alert's evidence in place. Returns the backtest report."""
    if not alerts:
        return {}
    now = pd.Timestamp(now if now is not None else pd.to_datetime(f.tx["ts"]).max())
    exchanges = sorted({k["entity_name"] for k in known.values() if k["entity_type"] == "VASP"})
    pool, mine = [], {}
    for a in alerts:
        ev = a.get("evidence") or {}
        me = {"alert_id": a["alert_id"], "cluster": ev.get("cluster_id") or a["entity_id"],
              "typology": str(a.get("alert_type", "")).removesuffix("_PATTERN")}
        mine[a["alert_id"]] = me
        d = _first_deposit(a)
        if d:
            pool.append({**me, "vasp": d["vasp"], "delay": float(d["minutes_after_receipt"]), "in_jurisdiction": d["in_jurisdiction"]})
    last_recv = f.tout[f.tout["address"].isin([a["entity_id"] for a in alerts])].groupby("address")["ts"].max()

    back = []
    for a in alerts:
        me, addr = mine[a["alert_id"]], a["entity_id"]
        sample = _sample(pool, me)
        done = _first_deposit(a)
        w = W.loc[addr] if addr in W.index else None
        balance = 0.0 if w is None else float(w.get("recv_btc", 0)) - float(w.get("sent_btc", 0))
        if len(sample) < MIN_SAMPLES:
            fc = {"status": "INSUFFICIENT_HISTORY", "samples": len(sample),
                  "note": f"needs ≥ {MIN_SAMPLES} observed cash-outs by other actors"}
        else:
            q = _quantiles([s["delay"] for s in sample])
            dests = _destinations(pool, me, sample, exchanges)
            fc = {"status": "CASHED_OUT" if done else "PENDING" if balance > MIN_BALANCE else "NO_BALANCE",
                  "basis": "typology" if all(s["typology"] == me["typology"] for s in sample) else "all_actors",
                  "typology": me["typology"], "samples": len(sample), "delay_minutes": q,
                  "destinations": dests[:3], "balance_btc": round(balance, 8)}
            if done:
                fc["observed"] = {"vasp": done["vasp"], "delay_minutes": done["minutes_after_receipt"],
                                  "in_window": q["p25"] <= done["minutes_after_receipt"] <= q["p75"],
                                  "predicted_top": dests[0]["vasp"]}
                back.append({"delay": float(done["minutes_after_receipt"]), "q": q, "vasp": done["vasp"],
                             "top": dests[0]["vasp"], "p_true": next((d["probability"] for d in dests if d["vasp"] == done["vasp"]), 0.0)})
            elif fc["status"] == "PENDING" and addr in last_recv.index:
                t0 = pd.Timestamp(last_recv[addr])
                start, end = t0 + pd.Timedelta(minutes=q["p25"]), t0 + pd.Timedelta(minutes=q["p75"])
                fc["window"] = {"from": str(start), "to": str(end), "last_receipt": str(t0),
                                "minutes_to_window_start": round((start - now).total_seconds() / 60, 1),
                                "state": "EXPECTED_LATER" if now < start else "IN_WINDOW" if now <= end else "OVERDUE"}
                fc["likely_exchange"] = dests[0]["vasp"]
                fc["in_jurisdiction"] = any(k["entity_name"] == dests[0]["vasp"] and k["in_jurisdiction"]
                                            for k in known.values())
        a.setdefault("evidence", {})["cashout_forecast"] = fc
    return backtest(back, exchanges)


def backtest(rows: List[dict], exchanges: List[str]) -> dict:
    """How well did the leave-one-actor-out forecasts match the cash-outs that really happened?"""
    if not rows:
        return {"cashed_out_alerts": 0}
    delays = np.array([r["delay"] for r in rows])
    cover = lambda lo, hi: float(np.mean([r["q"][lo] <= r["delay"] <= r["q"][hi] for r in rows]))
    naive = float(np.median(delays))      # one global median for everybody (in-sample, so it favours the baseline)
    mae_model = float(np.mean([abs(r["delay"] - r["q"]["p50"]) for r in rows]))
    mae_naive = float(np.mean(np.abs(delays - naive)))
    n_ex = max(len(exchanges), len({r["vasp"] for r in rows}), 1)
    return {"cashed_out_alerts": len(rows),
            "delay_coverage_p25_p75": round(cover("p25", "p75"), 3), "delay_coverage_p10_p90": round(cover("p10", "p90"), 3),
            "delay_mae_hours": round(mae_model / 60, 2), "delay_mae_hours_naive_global_median": round(mae_naive / 60, 2),
            "destination_top1": round(float(np.mean([r["top"] == r["vasp"] for r in rows])), 3),
            "destination_top1_uniform_baseline": round(1 / n_ex, 3),
            "destination_mean_prob_on_truth": round(float(np.mean([r["p_true"] for r in rows])), 3),
            "note": "nominal coverage is 0.50 / 0.80; destination beats chance only where actors reuse exchanges"}
