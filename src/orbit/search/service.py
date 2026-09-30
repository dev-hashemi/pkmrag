"""High-level search service orchestrating vector retrieval, graph proximity, and fusion."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit.config import get_default_db_dir, get_default_vector_dir
from orbit.graph.store import GraphStore
from orbit.graph.traversal import get_notes_by_tag
from orbit.models import SearchResult
from orbit.search.embedder import EmbeddingProvider, FastEmbedProvider
from orbit.search.fusion import apply_graph_boost, build_single_mode_results, compute_rrf
from orbit.search.vector_store import VectorStore


class SearchService:
    """Coordinates semantic vector search, BM25 keyword matching, and graph proximity boosting."""

    def __init__(
        self,
        vault_path: Path | str,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[EmbeddingProvider] = None,
        graph_store: Optional[GraphStore] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.vector_store = (
            vector_store
            if vector_store is not None
            else VectorStore(get_default_vector_dir(self.vault_path))
        )
        self.embedder: EmbeddingProvider = embedder if embedder is not None else FastEmbedProvider()
        self._graph_store = graph_store
        self._owns_graph_store = False

    def _get_graph_store(self) -> Optional[GraphStore]:
        """Lazy access or creation of GraphStore."""
        if self._graph_store is None:
            db_dir = get_default_db_dir(self.vault_path)
            if db_dir.exists():
                try:
                    self._graph_store = GraphStore(db_dir, read_only=True)
                    self._owns_graph_store = True
                except Exception:
                    self._graph_store = None
        return self._graph_store

    def search(
        self,
        query: str,
        near: Optional[str] = None,
        mode: str = "hybrid",
        limit: int = 5,
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Execute search with specified mode, optional graph proximity boosting, and limit."""
        clean_query = query.strip()
        if not clean_query:
            return []

        has_filters = bool(folder or tags)
        search_limit = max(limit * 5, 50) if has_filters else max(limit * 3, 20)

        if mode == "hybrid":
            q_vec = self.embedder.embed_query(clean_query)
            dense_docs = self.vector_store.search_dense(q_vec, limit=search_limit)
            sparse_docs = self.vector_store.search_sparse(clean_query, limit=search_limit)
            results = compute_rrf(dense_docs, sparse_docs)
        elif mode == "dense":
            q_vec = self.embedder.embed_query(clean_query)
            dense_docs = self.vector_store.search_dense(q_vec, limit=search_limit)
            results = build_single_mode_results(dense_docs, mode="dense")
        elif mode == "sparse":
            sparse_docs = self.vector_store.search_sparse(clean_query, limit=search_limit)
            results = build_single_mode_results(sparse_docs, mode="sparse")
        else:
            msg = f"Unknown search mode '{mode}'. Choose 'hybrid', 'dense', or 'sparse'."
            raise ValueError(msg)

        # Proximity graph boost if --near specified
        if near:
            gstore = self._get_graph_store()
            if gstore is not None:
                hops = gstore.get_neighbor_hops(near, max_hops=2)
                if hops:
                    results = apply_graph_boost(results, hops)

        # Folder filtering
        if folder:
            clean_folder = folder.strip("/").lower()
            results = [
                r
                for r in results
                if r.note_path.lower() == clean_folder
                or r.note_path.lower().startswith(f"{clean_folder}/")
            ]

        # Tag filtering
        if tags:
            gstore = self._get_graph_store()
            if gstore is not None:
                clean_tags = [t.strip().lstrip("#").lower() for t in tags if t.strip()]
                if clean_tags:
                    matching_paths: set[str] = set()
                    for t in clean_tags:
                        matched = get_notes_by_tag(gstore.conn, t, limit=500)
                        matching_paths.update(m["path"].lower() for m in matched)
                    results = [r for r in results if r.note_path.lower() in matching_paths]

        return results[:limit]

    def close(self) -> None:
        """Cleanly close underlying databases."""
        if self._owns_graph_store and self._graph_store is not None:
            self._graph_store.close()
        self.vector_store.close()

    def __enter__(self) -> SearchService:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
