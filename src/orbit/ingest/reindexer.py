"""Targeted single-note and delta synchronization pipeline for LadybugDB & LanceDB."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Optional

from orbit.cache import CacheManager
from orbit.config import settings
from orbit.dialects import KnowledgeDialect, get_default_registry
from orbit.graph.store import GraphStore
from orbit.models import SourceIndex, SyncResult
from orbit.parser.indexer import VaultIndexer
from orbit.search.chunker import HierarchicalMarkdownChunker
from orbit.search.embedder import EmbeddingProvider, FastEmbedProvider
from orbit.search.vector_store import VectorStore


class SingleNoteReindexer:
    """Incrementally indexes single notes or vault deltas into LadybugDB & LanceDB."""

    def __init__(
        self,
        vault_path: Path | str,
        graph_store: Optional[GraphStore] = None,
        vector_store: Optional[VectorStore] = None,
        cache_manager: Optional[CacheManager] = None,
        embedder: Optional[EmbeddingProvider] = None,
        dialect: Optional[KnowledgeDialect] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            raise FileNotFoundError(f"Vault directory does not exist: {self.vault_path}")

        self.db_dir = settings.get_db_dir(self.vault_path)
        self.vector_dir = settings.get_vector_dir(self.vault_path)
        self._graph_store = graph_store
        self._owns_graph_store = False
        self._vector_store = vector_store
        self._owns_vector_store = False
        self.cache_manager = cache_manager or CacheManager(self.vault_path)
        self.embedder = embedder or FastEmbedProvider()
        self.chunker = HierarchicalMarkdownChunker()

        registry = get_default_registry()
        self.dialect = dialect or registry.detect(self.vault_path)
        self.indexer = VaultIndexer(self.vault_path, dialect=self.dialect)
        self._write_lock = threading.Lock()

    def _get_graph_store(self) -> GraphStore:
        if self._graph_store is None:
            self._graph_store = GraphStore(self.db_dir, read_only=False)
            self._owns_graph_store = True
        return self._graph_store

    def _get_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = VectorStore(self.vector_dir)
            self._owns_vector_store = True
        return self._vector_store

    def _build_source_index(self, existing_notes: dict[str, dict[str, object]]) -> SourceIndex:
        """Construct an in-memory SourceIndex from graph notes for link resolution."""
        src_index = SourceIndex()
        for p in existing_notes:
            src_index.paths_set.add(p)
            src_index.lower_path_to_path[p.lower()] = p
            stem = PurePosixPath(p).stem.lower()
            src_index.basename_to_paths.setdefault(stem, []).append(p)
        return src_index

    def reindex_note(self, rel_path: str) -> SyncResult:
        """Targeted, sub-40ms incremental re-index of a single note."""
        t0 = time.perf_counter()
        clean = rel_path.strip().lstrip("/")
        if not clean:
            return SyncResult(path="", status="error", error_message="Note path cannot be empty.")

        abs_path = (self.vault_path / clean).resolve()
        if not abs_path.is_relative_to(self.vault_path):
            return SyncResult(
                path=clean, status="error", error_message=f"Path '{clean}' is outside vault."
            )

        norm_rel = abs_path.relative_to(self.vault_path).as_posix()
        if any(
            part.startswith(".") or part.lower() in settings.ignored_dirs
            for part in abs_path.relative_to(self.vault_path).parts
        ):
            return SyncResult(
                path=norm_rel,
                status="error",
                error_message=f"Path '{norm_rel}' is in a protected or ignored directory.",
            )

        gstore = self._get_graph_store()
        vstore = self._get_vector_store()

        with self._write_lock:
            existing_notes = gstore.get_all_notes()
            is_unres = bool(existing_notes.get(norm_rel, {}).get("is_unresolved", False))
            was_new = norm_rel not in existing_notes or is_unres

            # Handle deletion
            if not abs_path.is_file():
                if norm_rel in existing_notes:
                    gstore.handle_deleted_note(norm_rel)
                    vstore.delete_note_chunks(norm_rel)
                    evicted = self.cache_manager.invalidate_notes([norm_rel])
                    duration = round((time.perf_counter() - t0) * 1000, 2)
                    return SyncResult(
                        path=norm_rel,
                        status="deleted",
                        cache_entries_evicted=evicted,
                        duration_ms=duration,
                    )
                return SyncResult(
                    path=norm_rel,
                    status="error",
                    error_message=f"File '{norm_rel}' does not exist on disk.",
                )

            # Parse content and AST
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                mtime = abs_path.stat().st_mtime
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                note_meta = self.dialect.extract_document(norm_rel, content, mtime, content_hash)
            except Exception as e:
                return SyncResult(
                    path=norm_rel,
                    status="error",
                    error_message=f"Failed to read/parse note '{norm_rel}': {e}",
                )

            # 1. Update LadybugDB Graph
            gstore.delete_outgoing_edges(norm_rel)
            gstore.upsert_note(
                norm_rel,
                note_meta.title,
                note_meta.hash,
                note_meta.mtime,
                is_unresolved=False,
            )
            if was_new:
                gstore.reconcile_ghost_notes(norm_rel)

            parent = str(PurePosixPath(norm_rel).parent)
            if parent and parent != ".":
                gstore.add_note_contained_in(norm_rel, parent)

            for tag in note_meta.tags:
                gstore.add_tagged_with(norm_rel, tag)

            src_index = self._build_source_index(existing_notes)
            src_index.paths_set.add(norm_rel)
            src_index.lower_path_to_path[norm_rel.lower()] = norm_rel
            src_index.basename_to_paths.setdefault(PurePosixPath(norm_rel).stem.lower(), []).append(
                norm_rel
            )

            for link in note_meta.links:
                res_link = self.dialect.resolve_link(norm_rel, link, src_index)
                gstore.add_links_to(
                    norm_rel,
                    res_link.target_path,
                    res_link.anchor,
                    res_link.alias,
                    res_link.is_embed,
                )

            # 2. Update LanceDB Chunks
            chunks = self.chunker.chunk_document(norm_rel, note_meta.title, content)
            chunks_created = 0
            if chunks:
                texts = [c.text for c in chunks]
                vectors = self.embedder.embed_texts(texts)
                vstore.upsert_chunks(norm_rel, chunks, vectors, mtime=note_meta.mtime)
                chunks_created = len(chunks)
            else:
                vstore.delete_note_chunks(norm_rel)

            # 3. Cache Eviction
            if was_new:
                self.cache_manager.invalidate_all()
                evicted = 0
            else:
                evicted = self.cache_manager.invalidate_notes([norm_rel])

        duration = round((time.perf_counter() - t0) * 1000, 2)
        return SyncResult(
            path=norm_rel,
            status="indexed",
            chunks_count=chunks_created,
            links_count=len(note_meta.links),
            tags_count=len(note_meta.tags),
            ghosts_reconciled=1 if was_new else 0,
            cache_entries_evicted=evicted,
            duration_ms=duration,
        )

    def sync_vault_delta(self) -> list[SyncResult]:
        """Scan vault files and reindex any modified, newly added, or deleted files."""
        gstore = self._get_graph_store()
        existing_notes = gstore.get_all_notes()
        results: list[SyncResult] = []

        discovered: dict[str, Path] = {}
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not self.dialect.should_ignore_dir(d)]
            for f in files:
                if self.dialect.should_ignore_file(f):
                    continue
                file_path = Path(root) / f
                rel = file_path.relative_to(self.vault_path).as_posix()
                discovered[rel] = file_path

        # 1. Deleted notes
        for note_path, meta in existing_notes.items():
            if not meta.get("is_unresolved") and note_path not in discovered:
                res = self.reindex_note(note_path)
                results.append(res)

        # 2. Added or modified notes
        for rel, abs_path in discovered.items():
            st = abs_path.stat()
            needs_sync = False
            if rel not in existing_notes or existing_notes[rel].get("is_unresolved"):
                needs_sync = True
            elif existing_notes[rel].get("mtime", 0.0) != st.st_mtime:
                needs_sync = True

            if needs_sync:
                res = self.reindex_note(rel)
                results.append(res)

        return results

    def close(self) -> None:
        """Close opened resources."""
        if self._owns_graph_store and self._graph_store is not None:
            self._graph_store.close()
        if self._owns_vector_store and self._vector_store is not None:
            self._vector_store.close()
        self.cache_manager.close()
