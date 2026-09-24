"""CLI commands for the data workstream. OWNER: Dharmik."""
from pathlib import Path

import typer

from beans import config


def register(app: typer.Typer) -> None:
    @app.command()
    def synth(preset: str = "tiny", out: Path = None, seed: int = config.RANDOM_SEED,
              formats: str = "csv,json,xml"):
        """Generate a labelled synthetic dataset (presets: tiny, demo, bench)."""
        from beans.synth import generate
        out = out or config.SYNTH_DIR / preset
        typer.echo(generate(preset, out, seed, tuple(formats.split(","))))

    @app.command()
    def ingest(paths: list[Path], db: Path = config.DB_PATH, mapping: Path = None, reset: bool = False):
        """Ingest CSV/JSON/XML files into DuckDB (with GeoIP/ASN enrichment)."""
        from beans.ingest import ingest_files
        from beans.store.db import connect
        typer.echo(ingest_files(connect(db), paths, mapping, reset))

    @app.command()
    def graph(db: Path = config.DB_PATH):
        """Build first-spy, wallet-IP and flow-edge tables."""
        from beans.graph import build
        from beans.store.db import connect
        typer.echo(build(connect(db)))
