"""E6 mixer traversal: link probabilities inside CoinJoins and taint propagated through them."""
import pandas as pd

from beans.engines import e4_propagate, e6_mixer
from tests.test_nextgen import _frames, client  # noqa: F401 (fixture)

FEE = 0.0001   # _frames gives every tx this fee


def _coinjoin(k=5, denom=0.1, slack=FEE / 5):
    """k participants with inputs P0..; each gets one `denom` pool output Mi and change Ci = input - denom - slack."""
    ins = [(f"P{i}", denom + 0.01 * (i + 1) + 0.0007 * i) for i in range(k)]
    outs = [(f"M{i}", denom) for i in range(k)] + [(f"C{i}", round(a - denom - slack, 8)) for i, (_, a) in enumerate(ins)]
    return _frames([("cj", 0, ins, outs)])


def test_change_is_linked_with_certainty_and_pool_outputs_are_uniform():
    f = _coinjoin()
    df, rep = e6_mixer.links(f, {"cj"})
    ch = df[df["kind"] == "CHANGE"]
    assert set(zip(ch["src"], ch["dst"])) == {(f"P{i}", f"C{i}") for i in range(5)} and (ch["prob"] == 1.0).all()
    pool = df[df["kind"] == "POOL"]
    assert len(pool) == 25 and (pool["prob"] == 0.2).all()
    assert rep["median_anonymity_set"] == 5 and rep["traversed"] == 1


def test_equal_fitting_inputs_split_the_probability():
    # two inputs with the same amount: their change outputs cannot be told apart
    ins = [("A", 0.2), ("B", 0.2), ("C", 0.3), ("D", 0.4), ("E", 0.5)]
    outs = [(f"M{i}", 0.1) for i in range(5)] + [("CA", round(0.2 - 0.1 - FEE / 5, 8)), ("CC", round(0.3 - 0.1 - FEE / 5, 8))]
    df, _ = e6_mixer.links(_frames([("cj", 0, ins, outs)]), {"cj"})
    ca = df[(df["dst"] == "CA")]
    assert set(ca["src"]) == {"A", "B"} and (ca["prob"] == 0.5).all()


def test_transaction_without_an_equal_output_pool_is_left_alone():
    f = _frames([("t", 0, [("a", 1.0), ("b", 1.0), ("c", 1.0)], [("x", 0.7), ("y", 1.1), ("z", 1.2)])])
    df, rep = e6_mixer.links(f, {"t"})
    assert df.empty and rep["traversed"] == 0


def test_taint_follows_change_but_is_diluted_on_pool_outputs():
    f = _coinjoin()
    df, _ = e6_mixer.links(f, {"cj"})
    # a seed funds participant P0 before the mix
    f2 = _frames([("pre", -10, [("SEED", 1.0)], [("P0", 0.9)]),
                  ("cj", 0, list(zip(f.tin["address"], f.tin["amount"])), list(zip(f.tout["address"], f.tout["amount"])))])
    seeds = {"SEED"}
    plain, _ = e4_propagate.propagate(e4_propagate.graph(f2), seeds)
    mixed, _ = e4_propagate.propagate(e4_propagate.graph(f2, df), seeds)
    # change goes back to the tainted participant in full; the old proportional split smeared it over every output
    assert mixed.loc["C0", "taint"] > plain.loc["C0", "taint"]
    assert mixed.loc["C1", "taint"] < plain.loc["C1", "taint"]
    # a pool output carries at most 1/k of the participant's taint
    assert 0 < mixed.loc["M3", "taint"] <= mixed.loc["P0", "taint"] / 5 + 1e-9


def test_exposure_lists_candidates_with_taint():
    f = _coinjoin()
    df, _ = e6_mixer.links(f, {"cj"})
    ex = e6_mixer.exposure(df, {"P0": 1.0}, ["M2", "C0"])
    m2 = ex["M2"][0]
    assert m2["role"] == "RECEIVED" and m2["anonymity_set"] == 5 and m2["inherited_taint"] == 0.2
    assert m2["candidates"][0]["address"] == "P0"           # the tainted input is listed first
    assert ex["C0"][0]["inherited_taint"] == 1.0


def test_no_labels_are_read():
    import inspect
    src = inspect.getsource(e6_mixer.links) + inspect.getsource(e6_mixer._tx_links) + inspect.getsource(e6_mixer.exposure)
    assert "labels" not in src and "entity_id" not in src


def test_mixer_api_and_alert_evidence(client):
    c = client
    summary = c.get("/api/mixer").json()
    assert summary["mixing_transactions"] > 0 and summary["certain_change_links"] > 0
    from beans.api import db
    txid = db.query("SELECT txid FROM mixer_links LIMIT 1")[0]["txid"]
    r = c.get(f"/api/mixer/{txid}").json()
    assert r["links"] and r["anonymity_set"] >= 3
    pools = [x for x in r["links"] if x["kind"] == "POOL"]
    assert all(abs(x["prob"] - 1 / r["anonymity_set"]) < 1e-9 for x in pools)
    assert c.get("/api/mixer/" + "0" * 64).status_code == 404
