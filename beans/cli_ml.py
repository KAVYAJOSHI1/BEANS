"""CLI commands for the ML workstream. OWNER: Dhairya."""
from pathlib import Path

import typer

from beans import config


def register(app: typer.Typer) -> None:
    @app.command()
    def score(db: Path = config.DB_PATH, train: bool = True):
        """Run all engines + fusion and write wallet_scores / alert tables."""
        from beans.score import run_all
        from beans.store.db import connect
        typer.echo(run_all(connect(db), train=train))

    @app.command(name="eval")
    def evaluate_cmd(db: Path = config.DB_PATH):
        """Evaluate against synthetic ground truth and fill model_card."""
        from beans.score import evaluate
        from beans.store.db import connect
        typer.echo(evaluate(connect(db)))
