"""Large-scale benchmark: ~1M observation rows = N independent synthetic files loaded into one database, then scored.

The generator simulates a fixed 7-day economy and saturates at ~100k rows per file, and a real 1M-row load arrives as
several files anyway. Steps, each in its own process with peak memory measured:
  1. generate N files (seeds 1..N, not timed as part of the product)
  2. `beans ingest f1.csv … fN.csv --no-score`   (chunked, earliest relay wins across files)
  3. `beans score`                                 (all engines over the whole database, shipped models)

    .venv/bin/python scripts/benchmark_1m.py [--files 10]     → docs/BENCHMARK_1M.md
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def timed(args, env):
    out = subprocess.run(["/usr/bin/time", "-f", "BENCH %e %M", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    line = [ln for ln in out.stderr.splitlines() if ln.startswith("BENCH ")]
    if out.returncode or not line:
        raise RuntimeError(out.stderr[-3000:])
    sec, kb = line[-1].split()[1:]
    return float(sec), int(kb) / 1024 / 1024, out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=10)
    ap.add_argument("--n-tx", type=int, default=150000, help="generator size per file (~100k rows)")
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="beans-1m-"))
    env = {**os.environ, "DB_PATH": str(work / "db.duckdb"), "MODELS_DIR": str(work / "models"), "DATA_DIR": str(work / "data")}
    (work / "models").mkdir()
    for f in ("fusion.joblib", "e3_txclass.joblib", "typology_corpus.parquet", "fusion_training_set.parquet"):
        if (ROOT / "models" / f).exists():
            shutil.copy(ROOT / "models" / f, work / "models" / f)
    files = []
    for seed in range(1, a.files + 1):
        d = work / f"ds{seed}"
        subprocess.run([PY, "-c", f"from pathlib import Path; from beans.synth.writer import SyntheticDatasetWriter as W; "
                        f"W.generate_dataset(Path('{d}'), n_tx={a.n_tx}, seed={seed})"], cwd=ROOT, env=env, check=True)
        f = work / f"f{seed}.csv"
        shutil.move(d / "transactions.csv", f)       # no sidecars: operational (unlabelled) scoring
        shutil.rmtree(d)
        files.append(f)
    rows = sum(sum(1 for _ in open(f)) - 1 for f in files)
    ing_s, ing_gb, _ = timed([PY, "-m", "beans.cli", "ingest", *map(str, files), "--no-score"], env)
    sc_s, sc_gb, _ = timed([PY, "-m", "beans.cli", "score"], env)
    rep = json.loads((work / "models" / "training_report.json").read_text())
    t = rep["timings_s"]
    stages = " · ".join(f"{k} {v:.0f} s" for k, v in t.items() if not k.startswith("mem") and k not in ("peak_memory_gb", "total"))
    md = f"""# BEANS large-scale benchmark (~1M rows)

Machine: x86_64, {os.cpu_count()} cores, {round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1024 ** 3)} GB RAM.
{a.files} independent synthetic files (seeds 1-{a.files}) loaded into one database, then scored with the shipped models.

| | |
|---|---|
| Observation rows | **{rows:,}** |
| Transactions / wallets | {rep['transactions']:,} / {rep['wallets']:,} |
| Ingest (`beans ingest … --no-score`, chunked) | **{ing_s:.0f} s** · peak {ing_gb:.2f} GB · {rows / ing_s:,.0f} rows/s |
| Scoring (`beans score`, all engines) | **{sc_s:.0f} s** · peak {sc_gb:.2f} GB · {rows / sc_s:,.0f} rows/s |
| End to end | **{ing_s + sc_s:.0f} s** · {rows / (ing_s + sc_s):,.0f} rows/s |

Scoring stages (cumulative seconds): {stages}.

Reproduce: `.venv/bin/python scripts/benchmark_1m.py --files {a.files}`
"""
    (ROOT / "docs" / "BENCHMARK_1M.md").write_text(md)
    print(md)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
