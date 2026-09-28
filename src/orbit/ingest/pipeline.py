"""Orchestration pipeline for incremental vault ingestion into LadybugDB."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Optional

from orbit.config import get_default_db_dir
from orbit.dialects import KnowledgeDialect, get_default_registry
from orbit.graph.store import GraphStore
from orbit.models import IngestStats
from orbit.parser.indexer import VaultIndexer


class IngestPipeline:
    """Coordinates indexing, delta change detection, and graph population."""

    def __init__(
        self,
        vault_path: Path | str,
        db_path: Optional[Path | str] = None,
        rebuild: bool = False,
        dialect: str | KnowledgeDialect = "auto",
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            raise FileNotFoundError(f"Vault directory does not exist: {self.vault_path}")

        self.db_path = Path(db_path) if db_path else get_default_db_dir(self.vault_path)
        self.rebuild = rebuild

        registry = get_default_registry()
        if isinstance(dialect, str):
            self.dialect = registry.detect(self.vault_path, preferred=dialect)
        else:
            self.dialect = dialect

        self.indexer = VaultIndexer(self.vault_path, dialect=self.dialect)

    def run(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> IngestStats:
        """Execute the ingestion pipeline and return summary metrics."""
        start_time = time.perf_counter()

        # Step 1: Scan vault filesystem & index paths
        if progress_callback:
            progress_callback("Scanning vault files", 0, 1)

        discovered = self.indexer.scan_vault_structure()
        self.indexer.index_vault_files(discovered)

        # Step 2: Open GraphStore and determine incremental delta
        with GraphStore(self.db_path, rebuild=self.rebuild) as store:
            existing_notes = store.get_all_notes()

            added_paths: list[str] = []
            modified_paths: list[str] = []
            unchanged_paths: list[str] = []
            deleted_paths: list[str] = []

            # Identify additions, modifications, and unchanged notes
            for rel_path in discovered:
                file_hash = self.indexer.file_hashes.get(rel_path, "")
                if rel_path not in existing_notes:
                    added_paths.append(rel_path)
                elif existing_notes[rel_path]["is_unresolved"]:
                    # Previously unresolved ghost note, now realized on disk
                    added_paths.append(rel_path)
                elif existing_notes[rel_path]["hash"] != file_hash:
                    modified_paths.append(rel_path)
                else:
                    unchanged_paths.append(rel_path)

            # Identify deletions
            for existing_path, meta in existing_notes.items():
                if not meta["is_unresolved"] and existing_path not in discovered:
                    deleted_paths.append(existing_path)

            # Step 3: Prune deleted notes
            for del_path in deleted_paths:
                store.handle_deleted_note(del_path)

            # Step 4: Ingest added and modified files
            to_process = added_paths + modified_paths
            total_items = len(to_process)

            for idx, rel_path in enumerate(to_process, start=1):
                if progress_callback:
                    progress_callback("Ingesting notes & links", idx, total_items)

                # If modified, prune prior outgoing relationships
                if rel_path in modified_paths:
                    store.delete_outgoing_edges(rel_path)

                abs_path = discovered[rel_path]
                note_meta = self.indexer.parse_note(rel_path, abs_path)

                # Upsert note node
                store.upsert_note(
                    path=rel_path,
                    title=note_meta.title,
                    content_hash=note_meta.hash,
                    mtime=note_meta.mtime,
                    is_unresolved=False,
                )

                # Reconcile previously unresolved ghost notes matching this new note
                if rel_path in added_paths:
                    store.reconcile_ghost_notes(rel_path)

                # Folder hierarchy containment
                parent_folder = str(PurePosixPath(rel_path).parent)
                if parent_folder and parent_folder != ".":
                    store.add_note_contained_in(rel_path, parent_folder)

                # Tags
                for tag in note_meta.tags:
                    store.add_tagged_with(rel_path, tag)

                # Wikilinks and markdown links
                for link in note_meta.links:
                    resolved_path, is_ghost = self.indexer.resolve_link(rel_path, link)
                    store.add_links_to(
                        from_path=rel_path,
                        to_path=resolved_path,
                        anchor=link.anchor,
                        alias=link.alias,
                        is_embed=link.is_embed,
                    )

            # Step 5: Clean up any tags left orphan by modifications/deletions
            store.cleanup_orphaned_tags()

            # Step 6: Compute final graph statistics
            graph_stats = store.get_stats()
            duration_ms = (time.perf_counter() - start_time) * 1000

            return IngestStats(
                vault_path=str(self.vault_path),
                dialect=self.dialect.name,
                notes_scanned=len(discovered),
                notes_added=len(added_paths),
                notes_updated=len(modified_paths),
                notes_unchanged=len(unchanged_paths),
                notes_deleted=len(deleted_paths),
                unresolved_notes=graph_stats.get("unresolved_notes", 0),
                total_notes=graph_stats.get("notes", 0),
                total_links=graph_stats.get("links", 0),
                total_tags=graph_stats.get("tags", 0),
                total_folders=graph_stats.get("folders", 0),
                duration_ms=round(duration_ms, 2),
            )
