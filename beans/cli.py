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
    file_path: str = typer.Argument(..., help="Path to CSV, JSON, or XML file to ingest")
):
    """Ingest multi-format transaction file, enrich offline, and execute AI/ML pipeline."""
    p = Path(file_path)
    if not p.exists():
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Ingesting and running forensic ML pipeline on {p.name}...[/bold green]")
    pipeline = ForensicPipeline()
    result = pipeline.run_file_ingestion(p)
    console.print(f"[bold cyan]Ingestion complete![/bold cyan]")
    console.print(result)

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
