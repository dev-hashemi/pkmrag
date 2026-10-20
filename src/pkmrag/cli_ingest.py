"""Implementation of the `pkmrag ingest` command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from pkmrag.cli_progress import make_progress
from pkmrag.cli_views import display_trace_if_active, render_ingest_report
from pkmrag.ingest import IngestPipeline
from pkmrag.models import IngestProgress


def register_ingest_command(app: typer.Typer, console: Console) -> None:
    """Register the `pkmrag ingest` command on the CLI app."""

    @app.command()
    def ingest(
        vault_path: Path = typer.Argument(
            ..., help="Path to vault.", exists=True, resolve_path=True
        ),
        target: str = typer.Option("all", "--target", "-t", help="Target: all, graph, or vector."),
        db_dir: Optional[Path] = typer.Option(None, "--db-dir", "-d", help="Custom LadybugDB dir."),
        vector_dir: Optional[Path] = typer.Option(None, "--vector-dir", help="Custom LanceDB dir."),
        rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild indices from scratch."),
        clear_cache: bool = typer.Option(
            False, "--clear-cache", help="Purge cached search queries."
        ),
        dialect: str = typer.Option(
            "auto", "--dialect", "-m", help="Source dialect (auto, obsidian)."
        ),
        trace: bool = typer.Option(False, "--trace", help="Display visual execution trace tree."),
        json_output: bool = typer.Option(
            False, "--json", help="Output metrics in raw JSON format."
        ),
    ) -> None:
        """Ingest notes, links, tags, and semantic vectors from a knowledge base."""
        if trace:
            from pkmrag.telemetry import setup_telemetry

            setup_telemetry(enable_memory_collector=True)

        if rebuild or clear_cache:
            from pkmrag.cache import CacheManager

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
            console.print_json(pipeline.run().model_dump_json())
            sys.exit(0)

        if rebuild:
            console.print(
                "[yellow]Rebuild mode enabled: existing indices and cache wiped.[/yellow]"
            )

        with make_progress(console) as progress:
            task_id = progress.add_task("[cyan]Ingesting vault...", total=100)

            def on_prog(update: IngestProgress) -> None:
                progress.update(
                    task_id,
                    description=f"[cyan]{update.phase}...",
                    total=max(update.total, 1),
                    completed=update.cur,
                )

            stats = pipeline.run(progress_callback=on_prog)
            progress.update(task_id, description="[bold green]Ingestion complete!")

        render_ingest_report(stats, console)

        if trace:
            display_trace_if_active(console)
