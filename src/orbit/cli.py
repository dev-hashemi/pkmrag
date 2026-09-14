"""Command Line Interface for Project Orbit."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orbit import __version__
from orbit.doctor import run_diagnostics

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
    """Verify system requirements and embedded in-process storage engines (Kùzu & LanceDB)."""
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


if __name__ == "__main__":
    app()
