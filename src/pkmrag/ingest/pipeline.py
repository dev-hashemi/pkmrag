"""Orchestration pipeline for incremental vault ingestion into LadybugDB & LanceDB."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Optional

from pkmrag.config import settings
from pkmrag.dialects import KnowledgeDialect, get_default_registry
from pkmrag.graph.store import GraphStore
from pkmrag.models import IngestStats
from pkmrag.parser.indexer import VaultIndexer
from pkmrag.search.chunker import HierarchicalMarkdownChunker
from pkmrag.search.embedder import EmbeddingProvider, FastEmbedProvider
from pkmrag.search.vector_store import VectorStore
from pkmrag.telemetry import trace_span


class IngestPipeline:
    """Coordinates indexing, delta change detection, graph and vector population."""

    def __init__(
        self,
        vault_path: Path | str,
        db_path: Optional[Path | str] = None,
        vector_dir: Optional[Path | str] = None,
        rebuild: bool = False,
        dialect: str | KnowledgeDialect = "auto",
        target: str = "all",
        embedder: Optional[EmbeddingProvider] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            raise FileNotFoundError(f"Vault directory does not exist: {self.vault_path}")

        self.db_path = Path(db_path) if db_path else settings.get_db_dir(self.vault_path)
        self.vector_dir = (
            Path(vector_dir) if vector_dir else settings.get_vector_dir(self.vault_path)
        )
        self.rebuild = rebuild
        self.target = target
        self.embedder = embedder or FastEmbedProvider()

        registry = get_default_registry()
        if isinstance(dialect, str):
            self.dialect = registry.detect(self.vault_path, preferred=dialect)
        else:
            self.dialect = dialect

        self.indexer = VaultIndexer(self.vault_path, dialect=self.dialect)
        self.chunker = HierarchicalMarkdownChunker()

    def run(
        self,
        target: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> IngestStats:
        """Execute the ingestion pipeline for graph, vector, or all targets."""
        start_time = time.perf_counter()
        chosen_target = target or self.target
        if chosen_target not in ("all", "graph", "vector"):
            msg = f"Invalid target '{chosen_target}'. Must be 'all', 'graph', or 'vector'."
            raise ValueError(msg)

        with trace_span("pkmrag.ingest", attributes={"target": chosen_target}) as span:
            if progress_callback:
                progress_callback("Scanning vault files", 0, 1)

            with trace_span("ingest.scan_files"):
                discovered = self.indexer.scan_vault_structure()
                self.indexer.index_vault_files(discovered)

            span.set_attribute("notes.scanned", len(discovered))

            # Statistics accumulators
            notes_added, notes_updated, notes_unchanged, notes_deleted = 0, 0, 0, 0
            chunks_created, chunks_deleted, total_chunks = 0, 0, 0
            graph_stats: dict[str, int] = {}

            # 1. LadybugDB Graph Ingestion
            if chosen_target in ("all", "graph"):
                with trace_span("ingest.graph_sync"):
                    g_add, g_upd, g_unc, g_del, graph_stats = self._run_graph_ingest(
                        discovered, progress_callback
                    )
                    notes_added, notes_updated, notes_unchanged, notes_deleted = (
                        g_add,
                        g_upd,
                        g_unc,
                        g_del,
                    )

            # 2. LanceDB Vector Ingestion
            if chosen_target in ("all", "vector"):
                with trace_span("ingest.vector_sync"):
                    v_created, v_deleted, total_chunks = self._run_vector_ingest(
                        discovered, progress_callback
                    )
                    chunks_created, chunks_deleted = v_created, v_deleted
                    if chosen_target == "vector":
                        notes_added = len(discovered)

            duration_ms = (time.perf_counter() - start_time) * 1000

        return IngestStats(
            vault_path=str(self.vault_path),
            dialect=self.dialect.name,
            target=chosen_target,
            notes_scanned=len(discovered),
            notes_added=notes_added,
            notes_updated=notes_updated,
            notes_unchanged=notes_unchanged,
            notes_deleted=notes_deleted,
            unresolved_notes=graph_stats.get("unresolved_notes", 0),
            total_notes=graph_stats.get("notes", len(discovered)),
            total_links=graph_stats.get("links", 0),
            total_tags=graph_stats.get("tags", 0),
            total_folders=graph_stats.get("folders", 0),
            chunks_created=chunks_created,
            chunks_deleted=chunks_deleted,
            total_chunks=total_chunks,
            duration_ms=round(duration_ms, 2),
        )

    def _run_graph_ingest(
        self,
        discovered: dict[str, Path],
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> tuple[int, int, int, int, dict[str, int]]:
        with GraphStore(self.db_path, rebuild=self.rebuild) as store:
            existing = store.get_all_notes()
            added_paths: list[str] = []
            modified_paths: list[str] = []
            unchanged_paths: list[str] = []
            deleted_paths: list[str] = []

            for rel_path in discovered:
                file_hash = self.indexer.file_hashes.get(rel_path, "")
                if rel_path not in existing or existing[rel_path]["is_unresolved"]:
                    added_paths.append(rel_path)
                elif existing[rel_path]["hash"] != file_hash:
                    modified_paths.append(rel_path)
                else:
                    unchanged_paths.append(rel_path)

            for p, meta in existing.items():
                if not meta["is_unresolved"] and p not in discovered:
                    deleted_paths.append(p)

            for del_path in deleted_paths:
                store.handle_deleted_note(del_path)

            to_process = added_paths + modified_paths
            total = len(to_process)
            for idx, rel_path in enumerate(to_process, start=1):
                if progress_callback:
                    progress_callback("Ingesting graph notes", idx, total)
                if rel_path in modified_paths:
                    store.delete_outgoing_edges(rel_path)

                note_meta = self.indexer.parse_note(rel_path, discovered[rel_path])
                store.upsert_note(
                    rel_path, note_meta.title, note_meta.hash, note_meta.mtime, is_unresolved=False
                )
                if rel_path in added_paths:
                    store.reconcile_ghost_notes(rel_path)

                parent = str(PurePosixPath(rel_path).parent)
                if parent and parent != ".":
                    store.add_note_contained_in(rel_path, parent)
                for tag in note_meta.tags:
                    store.add_tagged_with(rel_path, tag)
                for link in note_meta.links:
                    res_path, _ = self.indexer.resolve_link(rel_path, link)
                    store.add_links_to(rel_path, res_path, link.anchor, link.alias, link.is_embed)

            store.cleanup_orphaned_tags()
            return (
                len(added_paths),
                len(modified_paths),
                len(unchanged_paths),
                len(deleted_paths),
                store.get_stats(),
            )

    def _run_vector_ingest(
        self,
        discovered: dict[str, Path],
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> tuple[int, int, int]:
        with VectorStore(self.vector_dir, rebuild=self.rebuild) as vstore:
            tracked = vstore.get_tracked_notes()
            to_embed: list[str] = []
            deleted: list[str] = [p for p in tracked if p not in discovered]

            for rel_path, abs_path in discovered.items():
                mtime = self.indexer.file_mtimes.get(rel_path, 0.0)
                if rel_path not in tracked or tracked[rel_path] != mtime:
                    to_embed.append(rel_path)

            for del_path in deleted:
                vstore.delete_note_chunks(del_path)

            chunks_created = 0
            total_items = len(to_embed)

            for idx, rel_path in enumerate(to_embed, start=1):
                if progress_callback:
                    progress_callback("Vectorizing chunks", idx, total_items)
                abs_path = discovered[rel_path]
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                title = PurePosixPath(rel_path).stem
                chunks = self.chunker.chunk_document(rel_path, title, content)
                if chunks:
                    texts = [c.text for c in chunks]
                    vectors = self.embedder.embed_texts(texts)
                    mtime = self.indexer.file_mtimes.get(rel_path, 0.0)
                    vstore.upsert_chunks(rel_path, chunks, vectors, mtime=mtime)
                    chunks_created += len(chunks)
                else:
                    vstore.delete_note_chunks(rel_path)

            if to_embed or deleted:
                vstore.create_fts_index()

            return chunks_created, len(deleted), vstore.get_total_chunks()
