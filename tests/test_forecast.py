"""E7 cash-out forecast: timing quantiles, destination probabilities, windows and the leave-one-actor-out backtest."""
import pandas as pd

from beans.decision import forecast
from tests.test_nextgen import T, VASP_IN, _frames, client  # noqa: F401 (fixture)

KNOWN = {"D1": {**VASP_IN, "entity_name": "EX-A"}, "D2": {**VASP_IN, "entity_name": "EX-B"}}


def _alert(i, vasp, delay, typology="RANSOMWARE", cluster=None):
    return {"alert_id": f"A{i}", "entity_id": f"W{i}", "alert_type": f"{typology}_PATTERN",
            "evidence": {"cluster_id": cluster or f"C{i}"},
            "recommended_action": {"vasp_exposure": [] if vasp is None else [
                {"vasp": vasp, "minutes_after_receipt": delay, "deposit_ts": f"2026-09-01 {10 + i:02d}:00:00",
                 "in_jurisdiction": True}]}}


def _setup(alerts, balances=None):
    f = _frames([(f"t{a['alert_id']}", 0, [("src", 1.0)], [(a["entity_id"], 0.5)]) for a in alerts]
                + [("late", 600, [("x", 1)], [("y", 1)])])
    W = pd.DataFrame({"recv_btc": 0.5, "sent_btc": 0.0}, index=[a["entity_id"] for a in alerts])
    for k, v in (balances or {}).items():
        W.loc[k, "sent_btc"] = 0.5 - v
    return f, W


def test_pending_wallet_gets_a_window_from_other_actors_delays():
    done = [_alert(i, "EX-A", 100 + 10 * i) for i in range(6)]          # delays 100..150 min
    pending = _alert(9, None, None)
    f, W = _setup(done + [pending])
    forecast.attach(done + [pending], W, f, KNOWN)
    fc = pending["evidence"]["cashout_forecast"]
    assert fc["status"] == "PENDING" and fc["samples"] == 6 and fc["basis"] == "typology"
    assert fc["delay_minutes"]["p50"] == 125.0
    assert fc["likely_exchange"] == "EX-A" and fc["destinations"][0]["probability"] > fc["destinations"][1]["probability"]
    # received at T, latest data at T+600 min, window T+112.5 … T+137.5 → already past
    assert fc["window"]["state"] == "OVERDUE" and fc["window"]["minutes_to_window_start"] < 0


def test_own_actor_history_pulls_the_destination():
    done = [_alert(i, "EX-A", 100) for i in range(6)] + [_alert(10, "EX-B", 100, cluster="ME")]
    me = _alert(11, None, None, cluster="ME")
    f, W = _setup(done + [me])
    forecast.attach(done + [me], W, f, KNOWN)
    d = me["evidence"]["cashout_forecast"]["destinations"]
    by = {x["vasp"]: x for x in d}
    assert by["EX-B"]["actor_deposits"] == 1 and by["EX-A"]["typology_deposits"] == 6


def test_cashed_out_alert_is_scored_without_using_its_own_actor():
    done = [_alert(i, "EX-A", 100 + 10 * i) for i in range(8)]
    f, W = _setup(done)
    rep = forecast.attach(done, W, f, KNOWN)
    obs = done[0]["evidence"]["cashout_forecast"]
    assert obs["status"] == "CASHED_OUT" and obs["samples"] == 7        # its own cash-out was left out
    assert rep["cashed_out_alerts"] == 8 and rep["destination_top1"] == 1.0


def test_too_little_history_makes_no_forecast():
    a = [_alert(0, "EX-A", 100), _alert(1, None, None)]
    f, W = _setup(a)
    forecast.attach(a, W, f, KNOWN)
    assert a[1]["evidence"]["cashout_forecast"]["status"] == "INSUFFICIENT_HISTORY"


def test_drained_wallet_is_not_pending():
    done = [_alert(i, "EX-A", 100) for i in range(5)] + [_alert(9, None, None)]
    f, W = _setup(done, balances={"W9": 0.0})
    forecast.attach(done, W, f, KNOWN)
    assert done[-1]["evidence"]["cashout_forecast"]["status"] == "NO_BALANCE"


def test_forecast_never_reads_ground_truth():
    import inspect
    src = inspect.getsource(forecast)
    assert "labels" not in src and "is_illicit" not in src


def test_forecast_api_and_alert_evidence(client):
    alerts = client.get("/api/alerts?limit=1000").json()
    fcs = [a["evidence"].get("cashout_forecast") for a in alerts]
    assert all(fc and fc["status"] for fc in fcs)
    q = client.get("/api/forecast").json()
    assert q["count"] == len(q["pending"])
    states = [p["window"]["state"] for p in q["pending"]]
    assert states == sorted(states, key=lambda s: {"IN_WINDOW": 0, "OVERDUE": 1, "EXPECTED_LATER": 2}[s])
