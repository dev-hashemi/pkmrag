"""Command Line Interface for Project Orbit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from orbit import __version__
from orbit.doctor import run_diagnostics
from orbit.ingest import IngestPipeline

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


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show Orbit version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Project Orbit CLI root callback."""


@app.command()
def doctor(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output diagnostics in raw JSON format.",
    ),
) -> None:
    """Verify system requirements and embedded in-process storage engines (LadybugDB & LanceDB)."""
    with console.status("[bold blue]Running Project Orbit diagnostics...[/bold blue]"):
        report = run_diagnostics()

    if json_output:
        console.print_json(report.model_dump_json())
        sys.exit(0 if report.all_passed else 1)

    header_text = (
        f"[bold cyan]Project Orbit[/bold cyan] v[green]{__version__}[/green] "
        "— System Health & Diagnostics"
    )
    console.print(Panel.fit(header_text, border_style="cyan"))

    # System Environment Table
    sys_table = Table(title="Environment Details", show_header=False, box=None)
    sys_table.add_column("Key", style="bold dim")
    sys_table.add_column("Value", style="cyan")

    sys_table.add_row("Operating System", report.system_info["os"])
    sys_table.add_row("Architecture", report.system_info["arch"])
    sys_table.add_row("Python Version", report.system_info["python"])
    sys_table.add_row("Python Path", report.system_info["python_path"])
    sys_table.add_row("Virtual Environment", report.system_info["virtual_env"])
    console.print(sys_table)
    console.print()

    # Engine Diagnostic Table
    engine_table = Table(title="In-Process Data Plane Verification")
    engine_table.add_column("Component", style="bold")
    engine_table.add_column("Status", justify="center")
    engine_table.add_column("Version", justify="center", style="dim")
    engine_table.add_column("Latency", justify="right")
    engine_table.add_column("Verification Details")

    for check in report.checks:
        status_badge = (
            "[bold green]PASS[/bold green]" if check.passed else "[bold red]FAIL[/bold red]"
        )
        engine_table.add_row(
            check.name,
            status_badge,
            check.version,
            f"{check.latency_ms:.1f}ms",
            check.details,
        )

    console.print(engine_table)
    console.print()

    if report.all_passed:
        console.print(
            "[bold green]All systems operational. Engines ready for Phase 1.[/bold green]"
        )
        sys.exit(0)
    else:
        console.print("[bold red]One or more health checks failed. Check logs above.[/bold red]")
        sys.exit(1)


@app.command()
def ingest(
    vault_path: Path = typer.Argument(
        ...,
        help="Path to the Obsidian vault directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    db_dir: Optional[Path] = typer.Option(
        None,
        "--db-dir",
        "-d",
        help="Custom LadybugDB database directory. Defaults to <vault>/.orbit/graph.",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="Rebuild the entire graph from scratch, clearing existing data.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output ingestion metrics in raw JSON format.",
    ),
) -> None:
    """Ingest markdown notes, wikilinks, tags, and folders from an Obsidian vault into LadybugDB."""
    pipeline = IngestPipeline(vault_path=vault_path, db_path=db_dir, rebuild=rebuild)

    if json_output:
        stats = pipeline.run()
        console.print_json(stats.model_dump_json())
        sys.exit(0)

    header_text = (
        f"[bold cyan]Project Orbit[/bold cyan] v[green]{__version__}[/green] "
        "— Vault Graph Ingestion"
    )
    console.print(Panel.fit(header_text, border_style="cyan"))
    console.print(f"[dim]Vault:[/dim] [bold]{vault_path}[/bold]")
    if rebuild:
        console.print("[yellow]Rebuild mode enabled: existing graph data wiped.[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]Ingesting vault...", total=100)

        def on_progress(phase: str, current: int, total: int) -> None:
            progress.update(
                task_id,
                description=f"[cyan]{phase}...",
                total=max(total, 1),
                completed=current,
            )

        stats = pipeline.run(progress_callback=on_progress)
        progress.update(task_id, description="[bold green]Ingestion complete!")

    # Ingestion Delta Table
    delta_table = Table(title="Sync Operations", show_header=True)
    delta_table.add_column("Operation", style="bold")
    delta_table.add_column("Notes", justify="right")

    delta_table.add_row("Scanned on Disk", str(stats.notes_scanned))
    delta_table.add_row("Added", f"[green]{stats.notes_added}[/green]")
    delta_table.add_row("Updated", f"[yellow]{stats.notes_updated}[/yellow]")
    delta_table.add_row("Unchanged", f"[dim]{stats.notes_unchanged}[/dim]")
    delta_table.add_row(
        "Deleted / Pruned",
        f"[red]{stats.notes_deleted}[/red]" if stats.notes_deleted > 0 else "0",
    )
    console.print(delta_table)
    console.print()

    # Graph Topology Table
    graph_table = Table(title="LadybugDB Graph Topology")
    graph_table.add_column("Entity / Relationship", style="bold")
    graph_table.add_column("Count", justify="right", style="cyan")
    graph_table.add_column("Details", style="dim")

    resolved_notes = stats.total_notes - stats.unresolved_notes
    graph_table.add_row("Notes (Resolved)", str(resolved_notes), "Notes existing on disk")
    graph_table.add_row(
        "Notes (Ghost / Unresolved)",
        f"[magenta]{stats.unresolved_notes}[/magenta]",
        "Targeted by wikilinks but not yet created",
    )
    graph_table.add_row("Total Notes", str(stats.total_notes), "All note vertices")
    graph_table.add_row(
        "Wikilinks (:LINKS_TO)",
        str(stats.total_links),
        "Explicit note-to-note connections",
    )
    graph_table.add_row("Tags (:TAGGED_WITH)", str(stats.total_tags), "Unique tags indexed")
    graph_table.add_row(
        "Folders (:CONTAINED_IN)",
        str(stats.total_folders),
        "Hierarchical folder nodes",
    )

    console.print(graph_table)
    console.print()

    throughput = (
        stats.notes_scanned / (stats.duration_ms / 1000.0) if stats.duration_ms > 0 else 0.0
    )
    console.print(
        f"[bold green]Ingestion successful in {stats.duration_ms:.1f}ms[/bold green] "
        f"[dim]({throughput:.1f} notes/sec)[/dim]"
    )


if __name__ == "__main__":
    app()
