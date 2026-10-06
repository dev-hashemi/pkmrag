"""Rich terminal renderers for OpenTelemetry execution traces."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from pkmrag.telemetry.collector import RecordedSpan


def _format_duration(ms: float) -> str:
    """Format duration in milliseconds with color-coded latency thresholds."""
    if ms < 10.0:
        return f"[bold green]{ms:>6.2f}ms[/bold green]"
    if ms < 50.0:
        return f"[cyan]{ms:>6.2f}ms[/cyan]"
    if ms < 150.0:
        return f"[yellow]{ms:>6.2f}ms[/yellow]"
    return f"[bold red]{ms:>6.2f}ms[/bold red]"


def _format_attributes(attrs: dict[str, object]) -> str:
    """Extract and format high-value span attributes into readable badges."""
    badges: list[str] = []

    if "cache.hit" in attrs:
        hit = attrs["cache.hit"]
        badges.append("[bold green]HIT[/bold green]" if hit else "[dim]MISS[/dim]")

    if "mode" in attrs:
        badges.append(f"[blue]{attrs['mode']}[/blue]")

    if "query.dim" in attrs:
        badges.append(f"[dim]{attrs['query.dim']}-dim[/dim]")

    if "near" in attrs and attrs["near"]:
        badges.append(f"[magenta]near: {attrs['near']}[/magenta]")

    if "candidates.count" in attrs:
        badges.append(f"[dim]{attrs['candidates.count']} candidates[/dim]")

    if "tokens.total" in attrs:
        badges.append(f"[yellow]{attrs['tokens.total']} tok[/yellow]")

    if "pruned_by_graph" in attrs:
        badges.append(f"[green]pruned: {attrs['pruned_by_graph']}[/green]")

    return f" ({', '.join(badges)})" if badges else ""


def _add_children(
    tree_node: Tree,
    parent_span_id: str,
    spans_by_parent: dict[str, list[RecordedSpan]],
) -> None:
    """Recursively append child spans to the Rich tree node."""
    children = spans_by_parent.get(parent_span_id, [])
    for child in children:
        dur_str = _format_duration(child.duration_ms)
        attr_str = _format_attributes(child.attributes)
        label = f"[white]{child.name}[/white]  {dur_str}{attr_str}"
        child_node = tree_node.add(label)
        _add_children(child_node, child.span_id, spans_by_parent)


def render_trace_tree(spans: list[RecordedSpan], console: Optional[Console] = None) -> None:
    """Render a hierarchical execution timeline tree from recorded spans."""
    c = console or Console()
    if not spans:
        c.print("[yellow]No execution trace recorded.[/yellow]")
        return

    # Group by parent_span_id
    spans_by_parent: dict[str, list[RecordedSpan]] = {}
    all_span_ids = {s.span_id for s in spans}
    root_spans: list[RecordedSpan] = []

    for s in spans:
        if s.parent_span_id is None or s.parent_span_id not in all_span_ids:
            root_spans.append(s)
        else:
            spans_by_parent.setdefault(s.parent_span_id, []).append(s)

    for root in root_spans:
        dur_str = _format_duration(root.duration_ms)
        attr_str = _format_attributes(root.attributes)
        header = f"[bold cyan]🛰️ Trace: {root.name}[/bold cyan]  {dur_str}{attr_str}"
        tree = Tree(header)
        _add_children(tree, root.span_id, spans_by_parent)

        c.print()
        c.print(
            Panel(
                tree,
                title=f"[dim]Trace ID: {root.trace_id[:16]}...[/dim]",
                border_style="cyan",
                expand=False,
            )
        )
