"""E8 same-operator candidates: fingerprints from habits, rarity-weighted similarity, ranked leads."""
import numpy as np
import pandas as pd

from beans.engines import e8_operator as e8
from beans.features.extractors import Frames

from tests.test_nextgen import client  # noqa: F401 (fixture)

T0 = pd.Timestamp("2026-09-01 00:00")


def _world():
    """Clusters A1/A2 are one operator (hours 2-4, own IP, rare software); the other 30 are noise."""
    rng = np.random.default_rng(0)
    tx, tin, spy, clusters, fee = [], [], [], {}, {}
    n = 0

    def add(cluster, hour, ip, version="v2|0|n", script="P2WPKH", rate=5.0):
        nonlocal n
        n += 1
        txid = f"{n:064x}"
        ts = T0 + pd.Timedelta(days=int(rng.integers(0, 6)), hours=int(hour), minutes=int(rng.integers(0, 60)))
        ver, lock, rbf = version.split("|")
        tx.append({"txid": txid, "ts": ts, "fee": 0.0001, "script_type": script, "tx_version": int(ver[1:]),
                   "locktime": 0 if lock == "0" else 800_000, "rbf": rbf == "r"})
        tin.append({"txid": txid, "ts": ts, "address": f"addr-{cluster}", "amount": 1.0})
        spy.append({"txid": txid, "spy_ip": ip})
        clusters[f"addr-{cluster}"] = cluster
        fee[txid] = rate

    for c in ("A1", "A2"):
        for _ in range(8):
            add(c, rng.integers(2, 5), "203.0.113.7" if c == "A1" or rng.random() < 0.5 else "203.0.113.8",
                version="v1|h|r", script="P2TR", rate=40.0)
    for i in range(30):
        for _ in range(6):
            add(f"N{i}", rng.integers(0, 24), f"198.51.100.{i % 5}", rate=float(rng.choice([2, 5, 10])))
    f = Frames(pd.DataFrame(tx), pd.DataFrame(tin), pd.DataFrame(columns=["txid", "ts", "idx", "address", "amount"]),
               pd.DataFrame(spy))
    return f, pd.Series(clusters, name="cluster_id"), pd.DataFrame({"fee_rate": fee})


def test_sibling_cluster_ranks_first_with_evidence():
    f, cl, X = _world()
    fp = e8.build(f, cl, X)
    lead = e8.candidates(fp, ["A1"])["A1"]
    assert lead[0]["cluster_id"] == "A2" and lead[0]["score"] > lead[1]["score"]
    assert "203.0.113.7" in lead[0]["shared_ips"] or lead[0]["signals"]["ip"] > 0
    assert lead[0]["signals"]["software"] > lead[1]["signals"]["software"]
    assert all(c["cluster_id"] != "A1" for c in lead)


def test_behaviour_alone_still_finds_the_sibling():
    f, cl, X = _world()
    fp = e8.build(f, cl, X)
    q = [fp.index["A1"]]
    sims = fp.similarity(["A1"])
    _, behaviour = e8._combine(fp, sims, q)
    behaviour[0, q[0]] = -1
    assert fp.clusters[int(np.argmax(behaviour[0]))] == "A2"


def test_rare_match_outweighs_a_default_match():
    f, cl, X = _world()
    fp = e8.build(f, cl, X)
    sims = fp.similarity(["A1", "N1"])
    # A1~A2 share a rare software fingerprint; N1~N2 share the default everyone uses
    assert sims["software"][0, fp.index["A2"]] > sims["software"][1, fp.index["N2"]]


def test_services_and_tiny_clusters_are_left_out():
    f, cl, X = _world()
    fp = e8.build(f, cl, X, known_addresses={"addr-N3"})
    assert "N3" not in fp.index
    assert e8.build(f, cl[cl.isin(["A1", "A2"])], X) is None   # fewer than 20 fingerprintable clusters


def test_evaluate_scores_against_labels_only_when_given():
    f, cl, X = _world()
    fp = e8.build(f, cl, X)
    labels = pd.DataFrame({"entity_id": {f"addr-{c}": ("OP" if c in ("A1", "A2") else c) for c in cl.unique()}})
    rep = e8.evaluate(fp, ["A1", "A2"], labels, cl)
    assert rep["hit_at_1"] == 1.0 and rep["without_network"]["hit_at_5"] == 1.0
    assert rep["hit_at_5_random"] < 0.2


def test_engine_never_reads_ground_truth():
    import inspect
    src = "".join(inspect.getsource(x) for x in (e8.build, e8.candidates, e8._combine, e8.Fingerprints))
    assert "labels" not in src and "entity_id" not in src


def test_alerts_carry_operator_candidates(client):
    alerts = client.get("/api/alerts?limit=1000").json()
    assert alerts and all("operator_candidates" in a["evidence"] for a in alerts)
    rows = [r for a in alerts for r in a["evidence"]["operator_candidates"]]
    assert rows and all(set(r["signals"]) == {"ip", "software", "script", "diurnal", "fee"} for r in rows)
