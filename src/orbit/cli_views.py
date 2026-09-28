"""Rich terminal display renderers for Project Orbit CLI."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orbit import __version__
from orbit.doctor import DoctorReport
from orbit.models import IngestStats, SearchResult


def render_doctor_report(report: DoctorReport, console: Console) -> None:
    """Render system diagnostics and embedded engine checks."""
    header_text = (
        f"[bold cyan]Project Orbit[/bold cyan] v[green]{__version__}[/green] "
        "— System Health & Diagnostics"
    )
    console.print(Panel.fit(header_text, border_style="cyan"))

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
        console.print("[bold green]All systems operational. Engines ready for Orbit.[/bold green]")
    else:
        console.print("[bold red]One or more health checks failed. Check logs above.[/bold red]")


def render_ingest_report(stats: IngestStats, console: Console) -> None:
    """Render sync delta operations and graph/vector statistics."""
    header_text = (
        f"[bold cyan]Project Orbit[/bold cyan] v[green]{__version__}[/green] "
        "— Knowledge Graph Ingestion"
    )

    console.print(Panel.fit(header_text, border_style="cyan"))
    console.print(
        f"[dim]Vault:[/dim] [bold]{stats.vault_path}[/bold] "
        f"[dim]• Dialect:[/dim] [cyan]{stats.dialect}[/cyan] "
        f"[dim]• Target:[/dim] [magenta]{stats.target}[/magenta]"
    )

    delta_table = Table(title="Sync Operations", show_header=True)
    delta_table.add_column("Operation", style="bold")
    delta_table.add_column("Count", justify="right")

    delta_table.add_row("Scanned on Disk", str(stats.notes_scanned))
    delta_table.add_row("Added", f"[green]{stats.notes_added}[/green]")
    delta_table.add_row("Updated", f"[yellow]{stats.notes_updated}[/yellow]")
    delta_table.add_row("Unchanged", f"[dim]{stats.notes_unchanged}[/dim]")
    delta_table.add_row(
        "Deleted / Pruned",
        f"[red]{stats.notes_deleted}[/red]" if stats.notes_deleted > 0 else "0",
    )
    if stats.target in ("all", "vector"):
        delta_table.add_row("Chunks Created", f"[green]{stats.chunks_created}[/green]")
        delta_table.add_row("Chunks Deleted", f"[red]{stats.chunks_deleted}[/red]")
        delta_table.add_row("Total Chunks", f"[cyan]{stats.total_chunks}[/cyan]")
    console.print(delta_table)
    console.print()

    if stats.target in ("all", "graph"):
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
        graph_table.add_row("Wikilinks (:LINKS_TO)", str(stats.total_links), "Explicit links")
        graph_table.add_row("Tags (:TAGGED_WITH)", str(stats.total_tags), "Unique tags indexed")
        graph_table.add_row("Folders (:CONTAINED_IN)", str(stats.total_folders), "Folder nodes")
        console.print(graph_table)
        console.print()

    throughput = (
        stats.notes_scanned / (stats.duration_ms / 1000.0) if stats.duration_ms > 0 else 0.0
    )
    console.print(
        f"[bold green]Ingestion successful in {stats.duration_ms:.1f}ms[/bold green] "
        f"[dim]({throughput:.1f} notes/sec)[/dim]"
    )


def render_search_results(
    results: list[SearchResult],
    query: str,
    near: Optional[str],
    mode: str,
    console: Console,
) -> None:
    """Render search matches in formatted panels."""
    header = f'🔍 Search Results for: [bold yellow]"{query}"[/bold yellow] [dim]({mode})[/dim]'
    if near:
        header += f" [dim]• near:[/dim] [bold magenta]{near}[/bold magenta]"
    console.print(Panel(header, border_style="cyan"))

    if not results:
        console.print("[dim yellow]No relevant results found.[/dim yellow]")
        return

    for idx, res in enumerate(results, start=1):
        boost_info = ""
        if res.graph_boost_factor > 1.0:
            boost_info = (
                f" [magenta]⚡ Graph Boost: x{res.graph_boost_factor:.2f} "
                f"(Hop {res.hop_distance})[/magenta]"
            )

        title = (
            f"[bold green]#{idx}[/bold green] [bold cyan]{res.note_path}[/bold cyan] "
            f"[dim](Score: {res.score:.5f})[/dim]{boost_info}"
        )

        if res.heading and res.text.startswith(res.heading):
            body_part = res.text[len(res.heading) :].lstrip("\n")
            if body_part:
                content = f"[bold dim]{res.heading}[/bold dim]\n\n{body_part}"
            else:
                content = res.text
        elif res.heading:
            content = f"[bold dim]{res.heading}[/bold dim]\n\n{res.text}"
        else:
            content = res.text

        # Truncate content if very long for terminal display
        if len(content) > 600:
            content = content[:597] + "..."

        console.print(Panel(content, title=title, border_style="blue", padding=(1, 2)))
