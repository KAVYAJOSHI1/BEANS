import typer
import uvicorn
from pathlib import Path
from rich.console import Console

from beans.config import settings
from beans.synth.writer import SyntheticDatasetWriter
from beans.ingest.pipeline import ForensicPipeline

app = typer.Typer(help="BEANS — Bitcoin Forensics Intelligence CLI")
console = Console()

@app.command()
def synth(
    n_tx: int = typer.Option(5000, "--n-tx", "-n", help="Total number of transactions to generate"),
    illicit_rate: float = typer.Option(0.05, "--illicit-rate", "-r", help="Fraction of illicit transactions"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed for reproducibility"),
    out: str = typer.Option("data/synth/demo", "--out", "-o", help="Output directory path")
):
    """Generate realistic synthetic Bitcoin P2P forensic dataset (CSV, JSON, XML)."""
    out_dir = Path(out)
    console.print(f"[bold green]Generating synthetic dataset with {n_tx} transactions (illicit rate: {illicit_rate:.1%})...[/bold green]")
    manifest = SyntheticDatasetWriter.generate_dataset(out_dir, n_tx=n_tx, illicit_rate=illicit_rate, seed=seed)
    console.print(f"[bold cyan]Dataset generated successfully at: {out_dir}[/bold cyan]")
    console.print(manifest)

@app.command()
def ingest(
    file_path: str = typer.Argument(..., help="Path to CSV, JSON, or XML file to ingest"),
    mapping: str = typer.Option(None, "--mapping", "-m", help="YAML column mapping for unfamiliar files (see beans/ingest/mapping.py)")
):
    """Ingest multi-format transaction file, enrich offline, and execute AI/ML pipeline."""
    p = Path(file_path)
    if not p.exists():
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Ingesting and running forensic ML pipeline on {p.name}...[/bold green]")
    pipeline = ForensicPipeline(mapping=Path(mapping) if mapping else None)
    result = pipeline.run_file_ingestion(p)
    console.print(f"[bold cyan]Ingestion complete![/bold cyan]")
    console.print(result)

@app.command()
def watch(
    folder: str = typer.Argument("data/inbox", help="Folder to watch for new CSV/JSON/XML files"),
    interval: float = typer.Option(10.0, "--interval", "-i", help="Seconds between scans"),
    mapping: str = typer.Option(None, "--mapping", "-m", help="YAML column mapping applied to every file"),
    once: bool = typer.Option(False, "--once", help="Process what is there now and exit"),
):
    """Monitoring mode: ingest + score every new file dropped into a folder (moved to processed/ afterwards)."""
    import shutil
    import time
    inbox, done = Path(folder), Path(folder) / "processed"
    inbox.mkdir(parents=True, exist_ok=True)
    done.mkdir(exist_ok=True)
    console.print(f"[bold green]Watching {inbox} every {interval:.0f}s (Ctrl+C to stop)…[/bold green]")
    while True:
        files = sorted(f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in {".csv", ".json", ".ndjson", ".jsonl", ".xml"})
        for f in files:
            console.print(f"→ {f.name}")
            try:
                res = ForensicPipeline(mapping=Path(mapping) if mapping else None).run_file_ingestion(f)
                console.print(f"  {res['records_ingested']} rows, {res['rows_quarantined']} quarantined, "
                              f"{res['pipeline_stats'].get('alerts_generated')} alerts")
            except Exception as e:  # keep watching; the file stays for inspection
                console.print(f"  [red]failed: {e}[/red]")
                continue
            shutil.move(str(f), done / f"{time.strftime('%Y%m%d_%H%M%S')}_{f.name}")
        if once:
            break
        time.sleep(interval)


@app.command()
def export(
    neo4j: str = typer.Option(None, "--neo4j", help="Output folder for neo4j-admin import CSVs"),
    stix: str = typer.Option(None, "--stix", help="Output file for a STIX 2.1 bundle of alert indicators"),
    min_risk: float = typer.Option(65.0, "--min-risk", help="STIX: only alerts at or above this risk"),
):
    """Export the graph (Neo4j) and/or alert indicators (STIX 2.1)."""
    from beans import export as ex
    if not (neo4j or stix):
        raise typer.BadParameter("give --neo4j DIR and/or --stix FILE")
    if neo4j:
        console.print(ex.neo4j(Path(neo4j)))
    if stix:
        console.print(ex.stix(Path(stix), min_risk))


@app.command("known-entities")
def known_entities(
    file_path: str = typer.Argument(..., help="CSV: address, entity_name[, entity_type, country, in_jurisdiction, source]"),
    rescore: bool = typer.Option(True, "--rescore/--no-rescore", help="Re-run scoring so action directives use the list"),
):
    """Load an attribution list (exchange / mining-pool addresses) used by the action directive rules."""
    from beans.store.duck import DuckStore
    store = DuckStore()
    n = store.load_known_entities(Path(file_path))
    console.print(f"[bold cyan]{n} attribution addresses loaded.[/bold cyan]")
    if rescore:
        console.print(ForensicPipeline(store).execute_ml_pipeline())


@app.command("validate-elliptic")
def validate_elliptic(
    data: str = typer.Option(None, "--data", help="Folder with the Elliptic CSVs (default data/external/elliptic)"),
    download: bool = typer.Option(False, "--download", help="Fetch the dataset first (needs internet once; checksummed)"),
    doc: str = typer.Option(None, "--doc", help="Also write the Markdown write-up here (e.g. docs/VALIDATION_ELLIPTIC.md)"),
):
    """External validation on the real Elliptic Bitcoin dataset (writes models/elliptic_report.json)."""
    from beans.validate import elliptic
    folder = Path(data) if data else elliptic.DEFAULT_DIR
    if download:
        elliptic.download(folder)
    if not (folder / "elliptic_txs_features.csv").exists():
        console.print(f"[bold red]No Elliptic data in {folder}. Run with --download (needs internet once).[/bold red]")
        raise typer.Exit(code=1)
    r = elliptic.run(folder)
    for name, m in r["detection"].items():
        console.print(f"{name:45s} P {m['precision']:.3f}  R {m['recall']:.3f}  F1 {m['f1']:.3f}  PR-AUC {m['pr_auc']:.3f}")
    console.print(f"Published (Weber et al. 2019) random forest AF: F1 0.788 · GCN: F1 0.628")
    console.print(f"Seeds (30 %): PR-AUC {r['propagation']['pr_auc_model_only']} → {r['propagation']['pr_auc_model_plus_seeds']}")
    console.print(f"Report: {elliptic.REPORT}")
    if doc:
        Path(doc).write_text(elliptic.markdown(r))
        console.print(f"Write-up: {doc}")


@app.command("typology-corpus")
def typology_corpus(
    seeds: str = typer.Option("1001,1002,1003,1004,1005,1006,1007,1008", "--seeds",
                              help="Comma-separated generator seeds (keep them apart from evaluation seeds)"),
    n_tx: int = typer.Option(5000, "--n-tx"),
):
    """Build models/typology_corpus.parquet: illicit wallets of extra synthetic datasets for the typology model."""
    from beans.score import typology_corpus as tc
    corpus = tc.build([int(s) for s in seeds.split(",")], n_tx, log=console.print)
    console.print(f"[bold green]{len(corpus)} wallets from {corpus['_group'].nunique()} operations → {tc.TYPOLOGY_CORPUS}[/bold green]")
    console.print(corpus.groupby("_typology")["_group"].nunique().to_dict())


user_app = typer.Typer(help="Local users (login switches on once the first user exists)")
app.add_typer(user_app, name="user")


@user_app.command("add")
def user_add(
    username: str = typer.Argument(...),
    role: str = typer.Option("ANALYST", "--role", "-r", help="VIEWER | ANALYST | SUPERVISOR | ADMIN"),
    display_name: str = typer.Option("", "--name", help="Full name shown in the audit trail"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True,
                                 help="At least 10 characters (prompted if omitted)"),
):
    """Create a user. The first user switches BEANS from single-user mode to login-required."""
    from beans.api import auth
    from beans.store.duck import DuckStore
    conn = DuckStore().get_connection()
    try:
        first = not auth.auth_enabled(conn)
        auth.create_user(conn, username, password, role, display_name)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)
    finally:
        conn.close()
    console.print(f"[bold green]User {username} ({role.upper()}) created.[/bold green]")
    if first:
        console.print("[yellow]Login is now required for the dashboard and API.[/yellow]")


@user_app.command("list")
def user_list():
    """List users."""
    from beans.store.duck import DuckStore
    conn = DuckStore().get_connection()
    for u, name, role, active in conn.execute("SELECT username, display_name, role, active FROM users ORDER BY created_at").fetchall():
        console.print(f"{u:20s} {role:11s} {'active' if active else 'disabled':9s} {name}")
    conn.close()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number")
):
    """Start the BEANS FastAPI forensic backend server."""
    console.print(f"[bold green]Starting BEANS server on http://{host}:{port}...[/bold green]")
    uvicorn.run("beans.api.main:app", host=host, port=port, reload=False)

@app.command()
def demo(
    n_tx: int = typer.Option(2000, "--n-tx", "-n", help="Transaction count for demo"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number")
):
    """Execute complete end-to-end 1-click offline demo."""
    console.print("[bold yellow]=== EXECUTING BEANS OFFLINE DEMO PIPELINE ===[/bold yellow]")
    demo_dir = settings.DATA_DIR / "synth" / "demo"
    SyntheticDatasetWriter.generate_dataset(demo_dir, n_tx=n_tx)
    
    csv_file = demo_dir / "transactions.csv"
    pipeline = ForensicPipeline()
    res = pipeline.run_file_ingestion(csv_file)
    console.print(f"[bold green]Demo dataset seeded & scored. Starting web dashboard...[/bold green]")
    uvicorn.run("beans.api.main:app", host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    app()
