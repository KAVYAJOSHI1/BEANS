"""Throughput benchmark (roadmap S9): wall time + peak memory per dataset size, training vs scoring mode.

  training  : labelled synthetic data → ingest + 4 engines + model training + evaluation (one-off)
  scoring   : the same file without labels → ingest + 4 engines + saved models (operational use)

Each stage runs in its own process under /usr/bin/time so peak RSS is measured per stage.
Usage: .venv/bin/python scripts/benchmark.py 50000 150000 300000   (sizes = generator --n-tx; rows are measured)
Writes docs/BENCHMARK.md.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def timed(code: str, env: dict) -> tuple[float, float, str]:
    out = subprocess.run(["/usr/bin/time", "-f", "BENCH %e %M", PY, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    line = [l for l in out.stderr.splitlines() if l.startswith("BENCH ")]
    if out.returncode or not line:
        raise RuntimeError(out.stderr[-2000:])
    sec, kb = line[-1].split()[1:]
    return float(sec), int(kb) / 1024 / 1024, out.stdout.strip()


def main(sizes):
    work = Path(tempfile.mkdtemp(prefix="beans-bench-"))
    results = []
    for n_tx in sizes:
        rows = n_tx
        d = work / f"ds{rows}"
        env = {**os.environ, "MODELS_DIR": str(work / f"models{rows}"), "DB_PATH": str(work / f"train{rows}.duckdb")}
        g_s, g_mem, out = timed(f"from pathlib import Path; from beans.synth.writer import SyntheticDatasetWriter as W; "
                                f"import json; print(json.dumps(W.generate_dataset(Path('{d}'), n_tx={n_tx}, seed=1)))", env)
        man = json.loads(out.splitlines()[-1])
        ingest = ("from pathlib import Path; from beans.ingest.pipeline import ForensicPipeline; import json; "
                  "print(json.dumps(ForensicPipeline().run_file_ingestion(Path('{f}'))['pipeline_stats']))")
        t_s, t_mem, t_out = timed(ingest.format(f=d / "transactions.csv"), env)
        un = work / f"unlabelled{rows}"
        un.mkdir()
        shutil.copy(d / "transactions.csv", un / "transactions.csv")
        env2 = {**env, "DB_PATH": str(work / f"score{rows}.duckdb")}
        s_s, s_mem, s_out = timed(ingest.format(f=un / "transactions.csv"), env2)
        res = {"rows": man["observation_rows"], "transactions": man["total_transactions"], "wallets": man["wallets"],
               "generate_s": g_s, "train_s": t_s, "train_peak_gb": round(t_mem, 2), "score_s": s_s,
               "score_peak_gb": round(s_mem, 2), "alerts": json.loads(s_out.splitlines()[-1])["alerts_generated"]}
        print(res, flush=True)
        results.append(res)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(un, ignore_errors=True)
    cpu = subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip()
    mem = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3)
    lines = ["# BEANS throughput benchmark (roadmap S9)", "",
             f"Machine: {platform.processor() or platform.machine()}, {cpu} cores, {mem} GB RAM, Python {platform.python_version()}. "
             "Each stage runs in its own process; peak memory is its max RSS.", "",
             "| Observation rows | Transactions | Wallets | Generate | Training run (ingest + engines + training) | "
             "Scoring run (ingest + engines, saved models) | Rows/s (scoring) |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['rows']:,} | {r['transactions']:,} | {r['wallets']:,} | {r['generate_s']:.0f} s | "
                     f"{r['train_s']:.0f} s · {r['train_peak_gb']} GB | {r['score_s']:.0f} s · {r['score_peak_gb']} GB | "
                     f"{r['rows'] / r['score_s']:,.0f} |")
    lines += ["", "Training is a one-off on labelled data; operational files are handled by the scoring run.",
              "Reproduce: `.venv/bin/python scripts/benchmark.py " + " ".join(map(str, sizes)) + "`",
              "", "About one million rows (several files, chunked ingest + one scoring pass): [BENCHMARK_1M.md](BENCHMARK_1M.md)"]
    (ROOT / "docs" / "BENCHMARK.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [50000, 150000, 300000])
