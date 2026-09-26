"""Build the typology reference corpus: illicit wallets (features + typology) from N extra synthetic datasets.

One synthetic dataset holds only a handful of operations per typology (e.g. one darknet market, three hack crews), too
few for the typology model to generalise. The corpus adds many more operations. Each dataset is generated and scored
in its own temporary database with the corpus switched off, and the corpus is always on the *training* side, so the
grouped cross-validation of the dataset being analysed stays honest. Use seeds that differ from any evaluation seed.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from beans.score.fuse import TYPOLOGY_CORPUS

ROOT = Path(__file__).resolve().parents[2]
_ONE = r"""
import sys
from pathlib import Path
from beans.synth.writer import SyntheticDatasetWriter
from beans.ingest.pipeline import ForensicPipeline
d = Path(sys.argv[1]) / "ds"
SyntheticDatasetWriter.generate_dataset(d, n_tx=int(sys.argv[2]), seed=int(sys.argv[3]))
ForensicPipeline().run_file_ingestion(d / "transactions.csv")
"""


def build(seeds, n_tx: int = 5000, out: Path = TYPOLOGY_CORPUS, log=print) -> pd.DataFrame:
    parts = []
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"beans-corpus-{seed}-") as tmp:
            env = {**os.environ, "DB_PATH": f"{tmp}/c.duckdb", "MODELS_DIR": f"{tmp}/models", "DATA_DIR": f"{tmp}/data",
                   "USE_TYPOLOGY_CORPUS": "false"}
            subprocess.run([sys.executable, "-c", _ONE, tmp, str(n_tx), str(seed)], cwd=ROOT, env=env, check=True,
                           capture_output=True)
            ts = pd.read_parquet(Path(tmp) / "models" / "fusion_training_set.parquet")
        ill = ts[ts["_y"] == 1].drop(columns=["_y", "_weight"], errors="ignore").copy()
        ill["_group"] = f"corpus{seed}:" + ill["_group"].astype(str)
        parts.append(ill)
        log(f"seed {seed}: {len(ill)} illicit wallets, {ill['_group'].nunique()} operations")
    corpus = pd.concat(parts, ignore_index=True)
    feats = [c for c in corpus.columns if not c.startswith("_")]
    corpus[feats] = corpus[feats].fillna(0).astype("float32")
    out.parent.mkdir(parents=True, exist_ok=True)
    corpus.to_parquet(out)
    return corpus
