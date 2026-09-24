"""`beans` command line. SHARED FILE: owners add commands in cli_data.py / cli_ml.py / cli_app.py."""
import typer

from beans import cli_app, cli_data, cli_ml

app = typer.Typer(no_args_is_help=True, help="BEANS: Bitcoin Encryption, Analysis & Network Security")
cli_data.register(app)
cli_ml.register(app)
cli_app.register(app)

if __name__ == "__main__":
    app()
