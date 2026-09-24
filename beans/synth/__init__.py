"""Synthetic dataset generator. OWNER: Dharmik."""
from pathlib import Path

PRESETS = {"tiny": 5_000, "demo": 200_000, "bench": 1_000_000}  # approx. number of net_obs rows


def generate(preset: str, out_dir: Path, seed: int = 42, formats: tuple[str, ...] = ("csv", "json", "xml")) -> Path:
    """Write transactions.{csv,json,xml}, labels_address.csv, labels_tx.csv, seeds.csv, manifest.json
    into out_dir. Returns the manifest path."""
    raise NotImplementedError("Dharmik: beans.synth.generate")
