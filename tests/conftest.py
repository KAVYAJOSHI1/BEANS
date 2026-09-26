"""Isolate every test run: throwaway DB, models and datasets (never touch data/ or models/ in the repo)."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="beans-test-"))
os.environ["DB_PATH"] = str(_TMP / "test.duckdb")
os.environ["MODELS_DIR"] = str(_TMP / "models")
os.environ["DATA_DIR"] = str(_TMP / "data")          # inbox uploads, local TSA keys

import pytest  # noqa: E402

from beans.synth.writer import SyntheticDatasetWriter  # noqa: E402


@pytest.fixture(scope="session")
def dataset() -> Path:
    """A small labelled v2 dataset (≈1k transactions, all typologies)."""
    d = _TMP / "ds"
    SyntheticDatasetWriter.generate_dataset(d, n_tx=600, seed=11)
    return d


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP
