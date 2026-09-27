import typer
import uvicorn
from pathlib import Path
from rich.console import Console
from rich.markup import escape

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
    file_paths: list[str] = typer.Argument(..., help="One or more CSV / JSON / XML files"),
    mapping: str = typer.Option(None, "--mapping", "-m", help="YAML column mapping for unfamiliar files (see beans/ingest/mapping.py)"),
    no_score: bool = typer.Option(False, "--no-score", help="Only load the files; run `beans score` once afterwards"),
):
    """Ingest files, enrich offline, and run the AI/ML pipeline (once, after the last file)."""
    paths = [Path(f) for f in file_paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        console.print(f"[bold red]File(s) not found: {', '.join(missing)}[/bold red]")
        raise typer.Exit(code=1)
    pipeline = ForensicPipeline(mapping=Path(mapping) if mapping else None)
    pipeline.execute_ml_pipeline, run_scoring = (lambda *a: {"skipped": True}), pipeline.execute_ml_pipeline
    for p in paths:
        console.print(f"[bold green]Ingesting {p.name}…[/bold green]")
        r = pipeline.run_file_ingestion(p)
        console.print(f"  {r['records_ingested']:,} rows, {r['rows_quarantined']:,} quarantined")
    if not no_score:
        console.print("[bold green]Scoring the whole database…[/bold green]")
        console.print(run_scoring())


@app.command()
def score():
    """Re-run all engines + fusion over everything in the database (e.g. after `ingest --no-score`)."""
    console.print(ForensicPipeline().execute_ml_pipeline())


@app.command("ofac-seeds")
def ofac_seeds(
    file: str = typer.Option(None, "--file", "-f", help="Official OFAC sdn.xml (default: data/intel/ofac_sdn.xml)"),
    download: bool = typer.Option(False, "--download", help="Fetch the current sdn.xml from treasury.gov first (needs internet)"),
    rescore: bool = typer.Option(True, "--rescore/--no-rescore", help="Re-run the engines so the new seeds propagate"),
    load: bool = typer.Option(True, "--load/--no-load", help="--no-load: only download (e.g. for `beans live`)"),
):
    """Load the Bitcoin addresses on the US Treasury OFAC SDN sanctions list as seeds (real, citable seeds)."""
    from beans.enrich import ofac
    from beans.store.duck import DuckStore
    path = Path(file) if file else ofac.DEFAULT_FILE
    if download:
        ofac.download(path)
        console.print(f"Downloaded {path}")
    if not path.exists():
        raise typer.BadParameter(f"{path} not found: pass --download, or --file with the official sdn.xml")
    parsed = ofac.parse(path)
    if not load:
        console.print(f"{len({e['address'] for e in parsed['entries']})} sanctioned addresses in {path} "
                      f"(list of {parsed['publish_date']}); not loaded into {settings.DB_PATH}")
        return
    conn = DuckStore().get_connection()
    n = ofac.load_seeds(conn, parsed)
    seen = conn.execute("""SELECT COUNT(DISTINCT s.address) FROM seeds s WHERE s.threat_type = 'SANCTIONED' AND s.address IN (
                             SELECT unnest(input_addresses) FROM transactions UNION SELECT unnest(output_addresses) FROM transactions)""").fetchone()[0]
    conn.close()
    console.print(f"[bold green]{n} sanctioned Bitcoin addresses loaded as seeds[/bold green] (list of {parsed['publish_date']}, "
                  f"sha256 {parsed['sha256'][:16]}…); {seen} appear in the loaded transactions")
    if rescore:
        console.print(ForensicPipeline().execute_ml_pipeline())


@app.command()
def watch(
    folder: str = typer.Argument("data/inbox", help="Folder to watch for new CSV/JSON/XML files"),
    interval: float = typer.Option(10.0, "--interval", "-i", help="Seconds between scans"),
    score_every: float = typer.Option(60.0, "--score-every", help="Score at most this often (s); files are loaded meanwhile"),
    mapping: str = typer.Option(None, "--mapping", "-m", help="YAML column mapping applied to every file"),
    once: bool = typer.Option(False, "--once", help="Process what is there now, score once and exit"),
):
    """Monitoring mode: load every new file dropped into a folder and score in batches (files → processed/).

    With the dashboard running, prefer `beans serve --watch FOLDER`: a separate watch process locks the database while it
    scores and the dashboard returns errors meanwhile."""
    from beans.ingest.worker import IngestWorker
    w = IngestWorker(Path(folder), interval=interval, score_every=score_every,
                     mapping=Path(mapping) if mapping else None, log=lambda m: console.print(escape(m)))
    try:
        w.run(once=once)
    except KeyboardInterrupt:
        w.stop()
        w.state["running"] = False
        w.write_status()


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
    """Load an attribution list (entity_type VASP / MINING_POOL / SWAP / BRIDGE) used by the action directive rules."""
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


@app.command()
def collect(
    peer: list[str] = typer.Option(None, "--peer", help="host:port of a Bitcoin node (repeatable)"),
    dns_seed: bool = typer.Option(False, "--dns-seed", help="Ask the public DNS seeds for peers"),
    out: str = typer.Option("data/inbox", "--out", help="Folder for rotated CSV files (watched by `beans watch`)"),
    minutes: float = typer.Option(None, "--minutes", help="Stop after this long (default: run until Ctrl+C)"),
    rotate: int = typer.Option(300, "--rotate", help="Seconds per output file"),
    max_peers: int = typer.Option(8, "--max-peers"),
    rpc: str = typer.Option(None, "--rpc", help="Resolve confirmed inputs from your Bitcoin Core node: http://user:pass@host:8332"),
    esplora: str = typer.Option(None, "--esplora", help="… or from an Esplora API (self-hosted electrs, or https://mempool.space/api)"),
):
    """OPTIONAL live collector (needs network): records transaction announcements per peer into BEANS CSVs.

    The analysis product stays offline; run this on a separate, connected machine and move the files over, or point
    `beans watch` at --out."""
    import asyncio
    from beans.collector.p2p import Collector, dns_seed_peers
    peers = [(h.rsplit(":", 1)[0], int(h.rsplit(":", 1)[1]) if ":" in h else 8333) for h in (peer or [])]
    if dns_seed:
        peers += dns_seed_peers(max_peers)
    if not peers:
        raise typer.BadParameter("give --peer host:port and/or --dns-seed")
    from beans.collector.resolve import from_args
    c = Collector(Path(out), rotate_s=rotate, max_peers=max_peers, resolver=from_args(rpc, esplora))
    console.print(f"[bold green]Collecting from {min(len(peers), max_peers)} peer(s) into {out}…[/bold green]")
    try:
        asyncio.run(c.run(peers, None if minutes is None else minutes * 60, log=lambda m: console.print(m)))
    except KeyboardInterrupt:
        c.flush()
    console.print(c.stats)


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
    port: int = typer.Option(8000, "--port", "-p", help="Port number"),
    watch_folder: str = typer.Option(None, "--watch", "-w", help="Also ingest files dropped into this folder (in-process)"),
    interval: float = typer.Option(5.0, "--interval", help="--watch: seconds between scans"),
    score_every: float = typer.Option(60.0, "--score-every", help="--watch: score at most this often (s)"),
):
    """Start the BEANS API + dashboard; with --watch, also the continuous ingest worker in the same process."""
    worker = _start_worker(Path(watch_folder), interval, score_every) if watch_folder else None
    console.print(f"[bold green]Starting BEANS server on http://{host}:{port}...[/bold green]")
    try:
        uvicorn.run("beans.api.main:app", host=host, port=port, reload=False)
    finally:
        if worker:
            worker.stop()


def _start_worker(folder: Path, interval: float, score_every: float):
    """The ingest worker runs as a thread of the server process: the dashboard stays responsive while it scores."""
    from beans.ingest.worker import IngestWorker
    settings.LIVE_INBOX = folder            # the Live Monitor page reads this folder's status files
    w = IngestWorker(folder, interval=interval, score_every=score_every,
                     log=lambda m: console.print(f"[dim]\\[ingest][/dim] {escape(m)}"))
    w.start()
    return w


@app.command()
def live(
    peer: list[str] = typer.Option(None, "--peer", help="host:port of a Bitcoin node (repeatable)"),
    dns_seed: bool = typer.Option(True, "--dns-seed/--no-dns-seed", help="Ask the public DNS seeds for peers"),
    rpc: str = typer.Option(None, "--rpc", help="Resolve confirmed inputs from your Bitcoin Core node: http://user:pass@host:8332"),
    esplora: str = typer.Option(None, "--esplora", help="… or from an Esplora API"),
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    db: str = typer.Option("data/live.duckdb", "--db", help="Live database (kept apart from the demo data)"),
    models: str = typer.Option("data/live_models", "--models", help="Model folder for live scoring (copied from models/ once)"),
    inbox: str = typer.Option("data/live_inbox", "--inbox", help="Folder the collector writes and the worker reads"),
    rotate: int = typer.Option(60, "--rotate", help="Seconds per collector file"),
    score_every: float = typer.Option(60.0, "--score-every", help="Score at most this often (s)"),
    max_peers: int = typer.Option(8, "--max-peers"),
    ofac: bool = typer.Option(True, "--ofac/--no-ofac", help="Load data/intel/ofac_sdn.xml as seeds if present"),
    minutes: float = typer.Option(None, "--minutes", help="Stop collecting after this long (the dashboard keeps running)"),
):
    """Live connected mode in one command: P2P collector + in-process ingest worker + dashboard (needs internet).

    Live data goes to its own database and model folder, never into the demo data."""
    import os
    import shutil
    import sys
    models_dir, inbox_dir = Path(models), Path(inbox)
    models_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    if not (models_dir / "fusion.joblib").exists():
        for f in settings.MODELS_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, models_dir / f.name)
        console.print(f"Copied the trained models to {models_dir} (live scoring never overwrites models/)")
    env = {**os.environ, "DB_PATH": str(Path(db).resolve()), "MODELS_DIR": str(models_dir.resolve()),
           "LIVE_INBOX": str(inbox_dir.resolve())}
    args = [sys.executable, "-m", "beans.cli", "live-run", "--host", host, "--port", str(port), "--rotate", str(rotate),
            "--score-every", str(score_every), "--max-peers", str(max_peers), "--dns-seed" if dns_seed else "--no-dns-seed",
            "--ofac" if ofac else "--no-ofac"]
    for p in peer or []:
        args += ["--peer", p]
    for k, v in (("--rpc", rpc), ("--esplora", esplora), ("--minutes", minutes)):
        if v is not None:
            args += [k, str(v)]
    os.execve(sys.executable, args, env)   # restart with the live paths set before any module reads them


@app.command("live-run", hidden=True)
def live_run(
    peer: list[str] = typer.Option(None, "--peer"), dns_seed: bool = typer.Option(True, "--dns-seed/--no-dns-seed"),
    rpc: str = typer.Option(None, "--rpc"), esplora: str = typer.Option(None, "--esplora"),
    host: str = typer.Option("127.0.0.1", "--host"), port: int = typer.Option(8000, "--port"),
    rotate: int = typer.Option(60, "--rotate"), score_every: float = typer.Option(60.0, "--score-every"),
    max_peers: int = typer.Option(8, "--max-peers"), ofac: bool = typer.Option(True, "--ofac/--no-ofac"),
    minutes: float = typer.Option(None, "--minutes"),
):
    import asyncio
    import threading
    from beans.collector.p2p import Collector, dns_seed_peers
    from beans.collector.resolve import from_args
    from beans.store.duck import DuckStore
    inbox = settings.LIVE_INBOX
    console.print(f"[bold green]BEANS live[/bold green] · database {settings.DB_PATH} · inbox {inbox}")
    sdn = settings.INTEL_DIR / "ofac_sdn.xml"
    if ofac and sdn.exists():
        from beans.enrich import ofac as ofac_mod
        conn = DuckStore().get_connection()
        try:
            if not conn.execute("SELECT COUNT(*) FROM seeds WHERE threat_type = 'SANCTIONED'").fetchone()[0]:
                n = ofac_mod.load_seeds(conn, ofac_mod.parse(sdn))
                console.print(f"Loaded {n} OFAC-sanctioned addresses as seeds")
        finally:
            conn.close()
    elif ofac:
        console.print("[yellow]No data/intel/ofac_sdn.xml: run `beans ofac-seeds --download` once for real seeds[/yellow]")
    peers = [(h.rsplit(":", 1)[0], int(h.rsplit(":", 1)[1]) if ":" in h else 8333) for h in (peer or [])]
    if dns_seed:
        peers += dns_seed_peers(max_peers)
    if not peers:
        raise typer.BadParameter("no peers: check the internet connection, or give --peer host:port")
    collector = Collector(inbox, rotate_s=rotate, max_peers=max_peers, resolver=from_args(rpc, esplora))
    ticks = {"n": 0}

    def clog(m):   # the collector reports every 5 s; print one line a minute
        ticks["n"] += 1
        if ticks["n"] % 12 == 1:
            console.print(f"[dim]\\[collector][/dim] {escape(m)}")
    ct = threading.Thread(target=lambda: asyncio.run(collector.run(peers, None if minutes is None else minutes * 60, log=clog)),
                          name="beans-collector", daemon=True)
    ct.start()
    worker = _start_worker(inbox, 5.0, score_every)
    console.print(f"[bold green]Dashboard: http://{host}:{port}/#live[/bold green] (Ctrl+C stops everything)")
    try:
        uvicorn.run("beans.api.main:app", host=host, port=port, reload=False)
    finally:
        collector.halt()
        worker.stop()
        ct.join(timeout=15)

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
