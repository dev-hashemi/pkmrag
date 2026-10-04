"""Rich terminal display renderers for evaluation reports."""

from __future__ import annotations

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orbit.eval.models import EvalReport


def render_eval_report(
    report: EvalReport,
    console: Console,
    min_mrr: float = 0.80,
    min_recall: float = 0.80,
    verbose: bool = True,
) -> None:
    """Render structured, color-coded evaluation results to the terminal."""
    m = report.metrics

    # 1. Summary Metrics Table
    summary_table = Table(
        title="🎯 Retrieval Evaluation Summary",
        box=ROUNDED,
        header_style="bold cyan",
        show_lines=True,
    )
    summary_table.add_column("Metric", style="bold white")
    summary_table.add_column("Target", justify="center")
    summary_table.add_column("Score", justify="right")
    summary_table.add_column("Status", justify="center")

    mrr_pass = m.mrr >= min_mrr
    mrr_status = "[bold green]PASS[/bold green]" if mrr_pass else "[bold red]FAIL[/bold red]"
    summary_table.add_row(
        "Mean Reciprocal Rank (MRR)", f"≥ {min_mrr:.2f}", f"{m.mrr:.3f}", mrr_status
    )

    rec_pass = m.mean_recall_at_5 >= min_recall
    rec_status = "[bold green]PASS[/bold green]" if rec_pass else "[bold red]FAIL[/bold red]"
    summary_table.add_row(
        "Context Recall@5", f"≥ {min_recall:.2f}", f"{m.mean_recall_at_5:.3f}", rec_status
    )
    summary_table.add_row("Context Precision@5", "-", f"{m.mean_precision_at_5:.3f}", "—")
    summary_table.add_row("Mean Average Precision (MAP@5)", "-", f"{m.map_at_5:.3f}", "—")
    summary_table.add_row("Hits@1 (Top-1 Accuracy)", "-", f"{m.hits_at_1 * 100:.1f}%", "—")
    summary_table.add_row("Hits@3", "-", f"{m.hits_at_3 * 100:.1f}%", "—")
    summary_table.add_row("Hits@5", "-", f"{m.hits_at_5 * 100:.1f}%", "—")
    summary_table.add_row(
        "Multi-Hop Completeness",
        "-",
        f"{m.multi_hop_completeness * 100:.1f}% ({m.multi_hop_queries} queries)",
        "—",
    )

    console.print()
    console.print(summary_table)

    # 2. Detailed Query Breakdown Table
    if verbose and report.results:
        detail_table = Table(
            title="📋 Individual Query Performance",
            box=ROUNDED,
            header_style="bold magenta",
        )
        detail_table.add_column("ID", style="dim", justify="center", width=5)
        detail_table.add_column("Query", style="white", min_width=25)
        detail_table.add_column("Expected", style="cyan", min_width=20)
        detail_table.add_column("Top Retrieved", style="dim white", min_width=20)
        detail_table.add_column("Rank", justify="center", width=8)
        detail_table.add_column("Recall", justify="right", width=8)

        for r in report.results:
            expected_short = ", ".join(p.rsplit("/", 1)[-1] for p in r.expected_notes)
            retrieved_short = (
                ", ".join(p.rsplit("/", 1)[-1] for p in r.retrieved_notes[:2])
                if r.retrieved_notes
                else "None"
            )

            if r.first_hit_rank == 1:
                rank_str = "[bold green]1[/bold green]"
            elif r.first_hit_rank and r.first_hit_rank <= 3:
                rank_str = f"[yellow]{r.first_hit_rank}[/yellow]"
            elif r.first_hit_rank:
                rank_str = f"[dim]{r.first_hit_rank}[/dim]"
            else:
                rank_str = "[bold red]MISS[/bold red]"

            rec_color = "green" if r.recall >= 1.0 else ("yellow" if r.recall > 0 else "red")
            rec_str = f"[{rec_color}]{r.recall:.2f}[/{rec_color}]"

            detail_table.add_row(
                r.query_id,
                r.query,
                expected_short,
                retrieved_short,
                rank_str,
                rec_str,
            )

        console.print()
        console.print(detail_table)

    # 3. Final Gate Verdict Banner
    console.print()
    if report.passed:
        console.print(
            Panel(
                f"[bold green]✔ All quality gates passed[/bold green] "
                f"({m.total_queries} queries evaluated in {report.duration_ms:.1f}ms)",
                border_style="green",
            )
        )
    else:
        err_msg = "\n".join(f"• {reason}" for reason in report.failure_reasons)
        console.print(
            Panel(
                f"[bold red]✖ Retrieval regression detected:[/bold red]\n{err_msg}",
                border_style="red",
            )
        )
