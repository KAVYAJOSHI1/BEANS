"""Multi-seed accuracy benchmark: generate N independent synthetic datasets, run the full pipeline on each in a
fresh database, and report the mean ± std of the headline metrics. Use it to judge any model change: a change
that helps one seed and hurts the others is noise, not an improvement.

    .venv/bin/python scripts/evaluate_seeds.py --seeds 42 7 123 --n-tx 5000 [--out report.json]

Every run uses its own temp DB_PATH / MODELS_DIR / DATA_DIR, so the repository's data/ and models/ are untouched.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUN = r"""
import json, sys
from pathlib import Path
from beans.synth.writer import SyntheticDatasetWriter
from beans.ingest.pipeline import ForensicPipeline
from beans.config import settings
d = Path(sys.argv[1]) / "ds"
SyntheticDatasetWriter.generate_dataset(d, n_tx=int(sys.argv[2]), seed=int(sys.argv[3]))
ForensicPipeline().run_file_ingestion(d / "transactions.csv")
r = json.loads((settings.MODELS_DIR / "training_report.json").read_text())
f, q, e1, e4 = r["fusion"], r.get("alert_quality", {}), r["e1"], r.get("e4", {})
print(json.dumps({
    "pr_auc": f.get("pr_auc"), "pr_auc_no_network": f.get("ablation", {}).get("pr_auc_without_network"),
    "roc_auc": f.get("roc_auc"), "recall_at_p50": f.get("recall_at_p50"), "precision_at_p50": f.get("precision_at_p50"),
    "precision_at_100": f.get("precision_at_100"), "ece": f.get("ece"),
    "typology_accuracy": f.get("typology_accuracy_grouped_cv"), "typology_unpooled": f.get("typology_accuracy_grouped_cv_unpooled"), "alert_typology_accuracy": q.get("typology_accuracy"),
    "e3_macro_f1": r["e3"].get("macro_f1"), "e1_completeness_illicit": e1.get("completeness_illicit"),
    "e1_homogeneity_illicit": e1.get("homogeneity_illicit"), "e4_hidden_reached": e4.get("hidden_reached"),
    "alert_precision": q.get("alert_precision"), "entity_recall": q.get("entity_recall"),
    "seconds": r["timings_s"]["total"],
}))
"""


def run_seed(seed: int, n_tx: int) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"beans-eval-{seed}-") as tmp:
        env = {**os.environ, "DB_PATH": f"{tmp}/eval.duckdb", "MODELS_DIR": f"{tmp}/models", "DATA_DIR": f"{tmp}/data"}
        out = subprocess.run([sys.executable, "-c", RUN, tmp, str(n_tx), str(seed)], cwd=ROOT, env=env,
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123])
    ap.add_argument("--n-tx", type=int, default=5000)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    runs = {s: run_seed(s, a.n_tx) for s in a.seeds}
    keys = list(next(iter(runs.values())))
    summary = {}
    print(f"{'metric':28s}" + "".join(f"{'seed ' + str(s):>12s}" for s in a.seeds) + f"{'mean':>10s}{'std':>8s}")
    for k in keys:
        vals = [runs[s][k] for s in a.seeds]
        nums = [v for v in vals if isinstance(v, (int, float))]
        mean = statistics.mean(nums) if nums else None
        sd = statistics.pstdev(nums) if len(nums) > 1 else 0.0
        summary[k] = {"mean": mean, "std": sd}
        cell = lambda v: f"{v:12.4f}" if isinstance(v, (int, float)) else f"{str(v):>12s}"  # noqa: E731
        print(f"{k:28s}" + "".join(cell(v) for v in vals) + (f"{mean:10.4f}{sd:8.4f}" if mean is not None else ""))
    if a.out:
        a.out.write_text(json.dumps({"n_tx": a.n_tx, "runs": runs, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
