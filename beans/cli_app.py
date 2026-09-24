"""CLI commands for the app workstream. OWNER: Kavya."""
from pathlib import Path

import typer

from beans import config


def register(app: typer.Typer) -> None:
    @app.command()
    def serve(db: Path = config.DB_PATH, host: str = config.API_HOST, port: int = config.API_PORT):
        """Start the API + dashboard."""
        raise NotImplementedError("Kavya: beans serve")

    @app.command()
    def pipeline(paths: list[Path], db: Path = config.DB_PATH, reset: bool = True):
        """ingest -> graph -> score -> eval in one go."""
        from beans.graph import build
        from beans.ingest import ingest_files
        from beans.score import evaluate, run_all
        from beans.store.db import connect
        con = connect(db)
        typer.echo(ingest_files(con, paths, None, reset))
        typer.echo(build(con))
        typer.echo(run_all(con, train=True))
        typer.echo(evaluate(con))
