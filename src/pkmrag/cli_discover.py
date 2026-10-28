"""Implementation of the `pkmrag discover` command."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pkmrag.discovery.engine import GapDiscoveryEngine
from pkmrag.graph.store import GraphStoreLockedError
from pkmrag.models import DiscoveryStats, InferredRelationship, SemanticGapCandidate

LOCKED_DATABASE_MESSAGE = (
    "[bold red]The vault database is locked by another PKMRAG process.[/bold red]\n"
    "Stop the background daemon (or use the Obsidian plugin's ⚡ Discover button) "
    "and retry. Read-only commands such as [cyan]pkmrag search[/cyan] still work."
)


class VaultDatabaseLockedError(RuntimeError):
    """Raised when another PKMRAG process holds the vault database."""


def run_gap_discovery(
    vault_path: Path,
    *,
    threshold: float,
    limit: int,
    provider: Optional[str],
    model: Optional[str],
    rpm: Optional[int],
    tpm: Optional[int],
    dry_run: bool,
    note: Optional[str] = None,
    on_progress: Optional[Callable[[int, int, str], None]],
) -> tuple[list[SemanticGapCandidate], list[InferredRelationship], DiscoveryStats]:
    """Discover semantic gaps, raising VaultDatabaseLockedError when the database is busy."""
    try:
        # A dry run only reads, so it can run while the daemon holds the vault database.
        engine = GapDiscoveryEngine(vault_path, read_only=dry_run)
    except GraphStoreLockedError as exc:
        raise VaultDatabaseLockedError(str(exc)) from exc

    try:
        return engine.discover(
            similarity_threshold=threshold,
            limit=limit,
            dry_run=dry_run,
            provider_type=provider,
            model=model,
            rpm=rpm,
            tpm=tpm,
            enrich=dry_run,
            focus_path=note,
            on_progress=on_progress,
        )
    finally:
        engine.close()
