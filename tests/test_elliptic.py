"""Elliptic validation harness, on a small generated file in the Elliptic format (the real data is not in the repo)."""
import numpy as np
import pandas as pd
import pytest

from beans.validate import elliptic


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    d = tmp_path_factory.mktemp("elliptic")
    rng = np.random.default_rng(0)
    n = 3000
    ids = 230_425_980 + np.arange(n) * 7            # 9-digit ids: float32 would make neighbours collide
    step = np.repeat(np.arange(1, 50), int(np.ceil(n / 49)))[:n]
    y = (rng.random(n) < 0.12).astype(int)
    X = rng.normal(size=(n, 165)).astype(np.float32)
    X[:, 0] += 2.5 * y                                # a learnable signal
    pd.DataFrame(np.column_stack([ids, step, X])).to_csv(d / "elliptic_txs_features.csv", header=False, index=False,
                                                        float_format="%.6f")
    cls = np.where(rng.random(n) < 0.5, "unknown", np.where(y == 1, "1", "2"))
    pd.DataFrame({"txId": ids, "class": cls}).to_csv(d / "elliptic_txs_classes.csv", index=False)
    src = rng.integers(0, n, 4000)
    dst = np.clip(src + rng.integers(1, 20, 4000), 0, n - 1)
    same = step[src] == step[dst]
    pd.DataFrame({"txId1": ids[src[same]], "txId2": ids[dst[same]]}).to_csv(d / "elliptic_txs_edgelist.csv", index=False)
    return d


def test_ids_survive_loading(mini):
    feats, y, edges = elliptic.load(mini)
    assert feats.index.is_unique and feats.index.dtype == np.int64 and feats.index[1] == 230_425_987
    assert set(y.dropna().unique()) <= {0.0, 1.0}


def test_report(mini, tmp_path, monkeypatch):
    monkeypatch.setattr(elliptic, "REPORT", tmp_path / "elliptic_report.json")
    r = elliptic.run(mini)
    assert (tmp_path / "elliptic_report.json").exists()
    det = r["detection"]["BEANS LightGBM + calibration (AF)"]
    assert 0 <= det["f1"] <= 1 and det["pr_auc"] > r["propagation"]["base_rate"]      # beats random on the signal
    assert r["split"]["train_steps"] == "1-34" and r["published_weber_2019"]["Random forest (AF)"]["f1"] == 0.788
    assert {"pr_auc_model_only", "pr_auc_model_plus_seeds"} <= set(r["propagation"])


def test_download_rejects_a_bad_checksum(tmp_path, monkeypatch):
    def fake(url, path):
        open(path, "wb").write(b"not the dataset")
    monkeypatch.setattr(elliptic.urllib.request, "urlretrieve", fake)
    with pytest.raises(ValueError, match="checksum"):
        elliptic.download(tmp_path)
