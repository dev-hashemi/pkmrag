"""MCP tool execution handlers for note and vault synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pkmrag.cache import CacheManager
from pkmrag.graph.store import GraphStore
from pkmrag.ingest.reindexer import SingleNoteReindexer
from pkmrag.search.vector_store import VectorStore


def execute_reindex_note(
    vault_path: Path,
    note_path: str,
    graph_store: Optional[GraphStore] = None,
    vector_store: Optional[VectorStore] = None,
    cache_manager: Optional[CacheManager] = None,
) -> str:
    """Re-index a single note into LadybugDB & LanceDB and invalidate stale cache entries."""
    clean = note_path.strip()
    if not clean:
        return "Note path cannot be empty."

    reindexer = SingleNoteReindexer(
        vault_path=vault_path,
        graph_store=graph_store,
        vector_store=vector_store,
        cache_manager=cache_manager,
    )

    result = reindexer.reindex_note(clean)
    if result.status == "error":
        return f"Error syncing note '{clean}': {result.error_message}"

    if result.status == "deleted":
        return (
            f"# Synchronized Deletion: `{result.path}`\n"
            f"- **Status**: Successfully purged from graph and vector indices\n"
            f"- **Cache Evicted**: {result.cache_entries_evicted} stale queries evicted\n"
            f"- **Duration**: {result.duration_ms:.1f}ms"
        )

    ghost_msg = (
        f" (reconciled {result.ghosts_reconciled} ghost note links)"
        if result.ghosts_reconciled
        else ""
    )
    return (
        f"# Synchronized Note: `{result.path}`\n"
        f"- **Status**: Successfully indexed in {result.duration_ms:.1f}ms{ghost_msg}\n"
        f"- **Chunks**: {result.chunks_count} vector snippets indexed\n"
        f"- **Wikilinks**: {result.links_count} graph connections\n"
        f"- **Tags**: {result.tags_count}\n"
        f"- **Cache Evicted**: {result.cache_entries_evicted} stale queries evicted"
    )


def execute_sync_vault(
    vault_path: Path,
    graph_store: Optional[GraphStore] = None,
    vector_store: Optional[VectorStore] = None,
    cache_manager: Optional[CacheManager] = None,
) -> str:
    """Perform delta synchronization across all modified or newly created vault files."""
    reindexer = SingleNoteReindexer(
        vault_path=vault_path,
        graph_store=graph_store,
        vector_store=vector_store,
        cache_manager=cache_manager,
    )

    results = reindexer.sync_vault_delta()
    if not results:
        return "Vault index is already up to date. No modified notes detected."

    lines: list[str] = [f"# Vault Synchronized ({len(results)} notes updated):\n"]
    lines.append("| Note Path | Status | Chunks | Links | Duration |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")

    for r in results:
        dur = f"{r.duration_ms:.1f}ms" if r.duration_ms > 0 else "-"
        lines.append(f"| `{r.path}` | {r.status} | {r.chunks_count} | {r.links_count} | {dur} |")

    total_chunks = sum(r.chunks_count for r in results)
    total_evicted = sum(r.cache_entries_evicted for r in results)
    lines.append(
        f"\n*Summary: {total_chunks} total chunks indexed, "
        f"{total_evicted} stale cache entries evicted.*"
    )
    return "\n".join(lines)
