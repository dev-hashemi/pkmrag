"""Command Line Interface for Project Orbit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from orbit import __version__
from orbit.cli_views import (
    render_discovery_results,
    render_doctor_report,
    render_ingest_report,
    render_mcp_config,
    render_search_results,
)
from orbit.doctor import run_diagnostics
from orbit.ingest import IngestPipeline
from orbit.search import SearchService

app = typer.Typer(
    name="orbit",
    help="🛰️ Project Orbit: In-process Hybrid GraphRAG Retrieval Engine & MCP Server.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print the version of Orbit and exit."""
    if value:
        console.print(f"[bold cyan]Project Orbit[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version.", callback=version_callback, is_eager=True
    ),
) -> None:
    """Project Orbit CLI root callback."""


@app.command()
def doctor(
    json_output: bool = typer.Option(
        False, "--json", help="Output diagnostics in raw JSON format."
    ),
) -> None:
    """Verify system requirements and embedded in-process storage engines (LadybugDB & LanceDB)."""
    with console.status("[bold blue]Running Project Orbit diagnostics...[/bold blue]"):
        report = run_diagnostics()

    if json_output:
        console.print_json(report.model_dump_json())
    else:
        render_doctor_report(report, console)
    sys.exit(0 if report.all_passed else 1)


@app.command()
def ingest(
    vault_path: Path = typer.Argument(
        ...,
        help="Path to the Obsidian vault directory.",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    target: str = typer.Option(
        "all",
        "--target",
        "-t",
        help="Ingestion target plane: all, graph, or vector. Defaults to all.",
    ),
    db_dir: Optional[Path] = typer.Option(
        None,
        "--db-dir",
        "-d",
        help="Custom LadybugDB database directory. Defaults to <vault>/.orbit/graph.",
    ),
    vector_dir: Optional[Path] = typer.Option(
        None,
        "--vector-dir",
        help="Custom LanceDB vector directory. Defaults to <vault>/.orbit/vectors.",
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Rebuild graph and vector indices from scratch."
    ),
    clear_cache: bool = typer.Option(False, "--clear-cache", help="Purge cached search queries."),
    dialect: str = typer.Option(
        "auto", "--dialect", "-m", help="Source dialect (auto, obsidian, commonmark)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output ingestion metrics in raw JSON format."
    ),
) -> None:
    """Ingest notes, links, tags, and semantic vectors from a knowledge base."""
    if rebuild or clear_cache:
        from orbit.cache import CacheManager

        CacheManager(vault_path).invalidate_all()

    pipeline = IngestPipeline(
        vault_path=vault_path,
        db_path=db_dir,
        vector_dir=vector_dir,
        rebuild=rebuild,
        dialect=dialect,
        target=target,
    )

    if json_output:
        stats = pipeline.run()
        console.print_json(stats.model_dump_json())
        sys.exit(0)

    if rebuild:
        console.print("[yellow]Rebuild mode enabled: existing indices and cache wiped.[/yellow]")

    with _make_progress() as progress:
        task_id = progress.add_task("[cyan]Ingesting vault...", total=100)

        def on_progress(phase: str, current: int, total: int) -> None:
            progress.update(
                task_id, description=f"[cyan]{phase}...", total=max(total, 1), completed=current
            )

        stats = pipeline.run(progress_callback=on_progress)
        progress.update(task_id, description="[bold green]Ingestion complete!")

    render_ingest_report(stats, console)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query string."),
    vault_path: Path = typer.Option(
        Path.cwd(),
        "--vault",
        "-v",
        help="Path to the Obsidian vault.",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    near: Optional[str] = typer.Option(
        None, "--near", "-n", help="Note path/title to bias results towards via graph proximity."
    ),
    mode: str = typer.Option(
        "hybrid", "--mode", "-m", help="Search mode: hybrid (default), dense, or sparse (BM25)."
    ),
    limit: int = typer.Option(5, "--limit", "-l", help="Maximum number of search results."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON results."),
) -> None:
    """Search knowledge base chunks using dense vectors, BM25, and optional graph proximity."""
    with SearchService(vault_path=vault_path) as service:
        results = service.search(query=query, near=near, mode=mode, limit=limit)

    if json_output:
        dump = [r.model_dump() for r in results]
        typer.echo(json.dumps(dump, indent=2))
        sys.exit(0)

    render_search_results(results, query=query, near=near, mode=mode, console=console)


@app.command()
def serve(
    vault_path: Path = typer.Argument(
        ..., help="Path to indexed vault directory.", exists=True, dir_okay=True, resolve_path=True
    ),
    transport: str = typer.Option(
        "stdio", "--transport", "-t", help="MCP transport protocol (stdio)."
    ),
) -> None:
    """Start an MCP server exposing Orbit tools over stdio to Claude and Cursor."""
    if transport != "stdio":
        console.print(
            f"[bold red]Unsupported transport '{transport}'. Only 'stdio' supported.[/bold red]"
        )
        sys.exit(1)

    from orbit.mcp import create_mcp_server

    create_mcp_server(vault_path).run(transport="stdio")


@app.command(name="mcp-config")
def mcp_config(
    vault_path: Path = typer.Argument(
        ..., help="Path to indexed vault directory.", exists=True, dir_okay=True, resolve_path=True
    ),
) -> None:
    """Generate ready-to-use MCP configuration snippets for Claude Desktop and Cursor."""
    render_mcp_config(vault_path, console)


@app.command()
def eval(
    vault_path: Optional[Path] = typer.Argument(
        None, help="Path to vault (defaults to benchmarks/vault)."
    ),
    benchmark: Optional[Path] = typer.Option(
        None, "-b", "--benchmark", help="Benchmark JSON (defaults to golden_10.json)."
    ),
    min_mrr: float = typer.Option(0.80, "--min-mrr", help="Minimum required MRR score."),
    min_recall: float = typer.Option(0.80, "--min-recall", help="Minimum required Recall@5."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON evaluation report."),
) -> None:
    """Evaluate retrieval engine accuracy against ground truth benchmarks."""
    from orbit.eval import EvaluationHarness, render_eval_report

    harness = EvaluationHarness(vault_path=vault_path, benchmark_path=benchmark)
    report = harness.run(min_mrr=min_mrr, min_recall=min_recall)

    if json_output:
        console.print_json(report.model_dump_json())
    else:
        render_eval_report(report, console, min_mrr=min_mrr, min_recall=min_recall)

    sys.exit(0 if report.passed else 1)


@app.command()
def discover(
    vault_path: Path = typer.Argument(
        ..., help="Path to indexed vault directory.", exists=True, dir_okay=True, resolve_path=True
    ),
    threshold: float = typer.Option(0.80, "--threshold", "-t", help="Cosine similarity threshold."),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum candidate pairs to classify."),
    rpm: Optional[int] = typer.Option(None, "--rpm", help="Rate limit: max requests per minute."),
    tpm: Optional[int] = typer.Option(None, "--tpm", help="Rate limit: max tokens per minute."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Scan candidates without invoking LLM."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON results."),
) -> None:
    """Discover semantic gaps between notes and infer conceptual relationships."""
    from orbit.discovery import GapDiscoveryEngine

    engine = GapDiscoveryEngine(vault_path)
    try:
        if dry_run or json_output:
            candidates, inferred, stats = engine.discover(
                similarity_threshold=threshold, limit=limit, dry_run=dry_run, rpm=rpm, tpm=tpm
            )
        else:
            with _make_progress() as progress:
                t_id = progress.add_task("[cyan]Scanning for semantic gaps...", total=limit)

                def on_prog(cur: int, tot: int, desc: str) -> None:
                    style = "yellow" if cur < 0 else "cyan"
                    progress.update(
                        t_id,
                        description=f"[{style}]{desc}[/{style}]",
                        total=max(tot, 1) if tot > 0 else limit,
                        completed=max(cur, 0),
                    )

                candidates, inferred, stats = engine.discover(
                    similarity_threshold=threshold,
                    limit=limit,
                    dry_run=dry_run,
                    rpm=rpm,
                    tpm=tpm,
                    on_progress=on_prog,
                )
    finally:
        engine.close()

    render_discovery_results(
        candidates, inferred, stats, dry_run=dry_run, json_output=json_output, console=console
    )


if __name__ == "__main__":
    app()
