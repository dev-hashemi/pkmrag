"""Rich terminal display renderers for PKMRAG CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkmrag import __version__
from pkmrag.doctor import DoctorReport
from pkmrag.models import (
    DiscoveryStats,
    InferredRelationship,
    IngestStats,
    SearchResult,
    SemanticGapCandidate,
)


def render_doctor_report(report: DoctorReport, console: Console) -> None:
    """Render system diagnostics and embedded engine checks."""
    header_text = (
        f"[bold cyan]PKMRAG[/bold cyan] v[green]{__version__}[/green] — System Health & Diagnostics"
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
        if check.extra.get("optional") and not check.extra.get("active"):
            status_badge = "[bold yellow]OFFLINE[/bold yellow]"
        else:
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
        console.print("[bold green]All systems operational. Engines ready for PKMRAG.[/bold green]")
    else:
        console.print("[bold red]One or more health checks failed. Check logs above.[/bold red]")


def render_ingest_report(stats: IngestStats, console: Console) -> None:
    """Render sync delta operations and graph/vector statistics."""
    header_text = (
        f"[bold cyan]PKMRAG[/bold cyan] v[green]{__version__}[/green] — Knowledge Graph Ingestion"
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


def render_discovery_results(
    candidates: list[SemanticGapCandidate],
    inferred: list[InferredRelationship],
    stats: DiscoveryStats,
    dry_run: bool,
    console: Console,
    json_output: bool = False,
) -> None:
    """Render discovery candidate scan or classified relationship results."""
    if json_output:
        dump = {
            "vault_path": stats.vault_path,
            "dry_run": dry_run,
            "candidates": [c.model_dump() for c in candidates],
            "inferred_relationships": [r.model_dump() for r in inferred],
            "stats": stats.model_dump(),
        }
        console.print_json(json.dumps(dump, indent=2))
        return

    if dry_run:
        console.print(
            f"\n[bold yellow]🔍 Semantic Gap Discovery (DRY RUN)[/bold yellow] — "
            f"Vault: [cyan]{stats.vault_path}[/cyan]\n"
        )
        if not candidates:
            console.print("[dim green]No unlinked semantic gaps found above threshold.[/dim green]")
            return

        table = Table(title=f"Discovered {len(candidates)} Semantic Gap Candidates (Unlinked)")
        table.add_column("Source Note", style="cyan")
        table.add_column("Target Note", style="cyan")
        table.add_column("Similarity", justify="center", style="magenta")
        table.add_column("Preview", style="dim")

        for c in candidates[:30]:
            preview = (
                f"{c.source_chunk_text[:50].strip()}... ↔ {c.target_chunk_text[:50].strip()}..."
            )
            table.add_row(c.source_path, c.target_path, f"{c.similarity:.4f}", preview)

        console.print(table)
        est_tokens = len(candidates) * 800
        console.print(
            f"\n[bold]Summary:[/bold] {len(candidates)} candidate pairs found in "
            f"{stats.duration_ms:.1f}ms. Estimated LLM tokens: ~{est_tokens:,}. "
            "Run without [yellow]--dry-run[/yellow] to classify."
        )
        return

    console.print(
        f"\n[bold green]💡 Semantic Gap Discovery Results[/bold green] — "
        f"Vault: [cyan]{stats.vault_path}[/cyan]\n"
    )

    if not inferred:
        console.print(
            "[dim yellow]Evaluated candidates, but no high-confidence relationships "
            "were inferred.[/dim yellow]"
        )
        return

    table = Table(title=f"Synthesized {len(inferred)} Inferred Relationships (LadybugDB)")
    table.add_column("Source Note", style="cyan")
    table.add_column("Relationship", justify="center", style="bold green")
    table.add_column("Target Note", style="cyan")
    table.add_column("Confidence", justify="center", style="magenta")
    table.add_column("Reason", style="white")

    for r in inferred:
        table.add_row(
            r.source_path,
            f"[:{r.rel_type}]",
            r.target_path,
            f"{r.confidence:.2f}",
            r.reason,
        )

    console.print(table)
    console.print(
        f"\n[bold green]✓ Done![/bold green] Inferred {len(inferred)} relationships across "
        f"{stats.total_notes_scanned} notes in {stats.duration_ms:.1f}ms."
    )


def render_mcp_config(
    vault_path: Path, console: Console, transport: str = "stdio", port: int = 3747
) -> None:
    """Render ready-to-use MCP configuration snippets for Claude and Cursor."""
    from pkmrag.mcp.views import render_mcp_config as _render

    _render(vault_path, console=console, transport=transport, port=port)
