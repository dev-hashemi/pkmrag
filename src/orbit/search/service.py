"""High-level search service orchestrating vector retrieval, graph proximity, and fusion."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit.cache import CacheManager
from orbit.config import settings
from orbit.graph.store import GraphStore
from orbit.graph.traversal import get_notes_by_tag
from orbit.models import CacheStats, SearchResult
from orbit.search.embedder import EmbeddingProvider, FastEmbedProvider
from orbit.search.fusion import apply_graph_boost, build_single_mode_results, compute_rrf
from orbit.search.vector_store import VectorStore
from orbit.telemetry import trace_span


class SearchService:
    """Coordinates semantic vector search, BM25 keyword matching, and graph proximity boosting."""

    def __init__(
        self,
        vault_path: Path | str,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[EmbeddingProvider] = None,
        graph_store: Optional[GraphStore] = None,
        cache_manager: Optional[CacheManager] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.vector_store = (
            vector_store
            if vector_store is not None
            else VectorStore(settings.get_vector_dir(self.vault_path))
        )
        self.embedder: EmbeddingProvider = embedder if embedder is not None else FastEmbedProvider()
        self._graph_store = graph_store
        self._owns_graph_store = False
        self.cache_manager = (
            cache_manager if cache_manager is not None else CacheManager(self.vault_path)
        )

    def _get_graph_store(self) -> Optional[GraphStore]:
        """Lazy access or creation of GraphStore."""
        if self._graph_store is None:
            db_dir = settings.get_db_dir(self.vault_path)
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

        # 1. Fast L1 Cache Lookup (< 0.5ms on hit)
        with trace_span(
            "orbit.search",
            attributes={"query": clean_query, "mode": mode, "limit": limit, "near": near or ""},
        ) as root_span:
            with trace_span("cache.lookup") as c_span:
                cached = self.cache_manager.get(
                    query=clean_query,
                    mode=mode,
                    near=near,
                    limit=limit,
                    folder=folder,
                    tags=tags,
                )
                if cached is not None:
                    c_span.set_attribute("cache.hit", True)
                    root_span.set_attribute("cache.hit", True)
                    return cached
                c_span.set_attribute("cache.hit", False)
                root_span.set_attribute("cache.hit", False)

            has_filters = bool(folder or tags)
            search_limit = max(limit * 5, 50) if has_filters else max(limit * 3, 20)

            if mode == "hybrid":
                with trace_span(
                    "embed.query", attributes={"query.length": len(clean_query)}
                ) as e_span:
                    q_vec = self.embedder.embed_query(clean_query)
                    e_span.set_attribute("query.dim", len(q_vec))
                with trace_span("lancedb.dense_search", attributes={"limit": search_limit}):
                    dense_docs = self.vector_store.search_dense(q_vec, limit=search_limit)
                with trace_span("lancedb.sparse_search", attributes={"limit": search_limit}):
                    sparse_docs = self.vector_store.search_sparse(clean_query, limit=search_limit)
                with trace_span("rrf.fuse", attributes={"k": 60}):
                    results = compute_rrf(dense_docs, sparse_docs)
            elif mode == "dense":
                with trace_span(
                    "embed.query", attributes={"query.length": len(clean_query)}
                ) as e_span:
                    q_vec = self.embedder.embed_query(clean_query)
                    e_span.set_attribute("query.dim", len(q_vec))
                with trace_span("lancedb.dense_search", attributes={"limit": search_limit}):
                    dense_docs = self.vector_store.search_dense(q_vec, limit=search_limit)
                results = build_single_mode_results(dense_docs, mode="dense")
            elif mode == "sparse":
                with trace_span("lancedb.sparse_search", attributes={"limit": search_limit}):
                    sparse_docs = self.vector_store.search_sparse(clean_query, limit=search_limit)
                results = build_single_mode_results(sparse_docs, mode="sparse")
            else:
                msg = f"Unknown search mode '{mode}'. Choose 'hybrid', 'dense', or 'sparse'."
                raise ValueError(msg)

            # Proximity graph boost if --near specified
            if near:
                with trace_span("ladybug.proximity_boost", attributes={"near": near}):
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
                            matching_paths.update(m.path.lower() for m in matched)
                        results = [r for r in results if r.note_path.lower() in matching_paths]

            final_results = results[:limit]

            # 2. Store in L1 Cache with dependencies
            with trace_span("cache.store"):
                self.cache_manager.put(
                    query=clean_query,
                    mode=mode,
                    results=final_results,
                    near=near,
                    limit=limit,
                    folder=folder,
                    tags=tags,
                )

            return final_results

    def get_cache_stats(self) -> CacheStats:
        """Fetch current query cache statistics."""
        return self.cache_manager.get_stats()

    def clear_cache(self) -> None:
        """Purge all cached search queries."""
        self.cache_manager.invalidate_all()

    def close(self) -> None:
        """Cleanly close underlying databases and cache."""
        if self._owns_graph_store and self._graph_store is not None:
            self._graph_store.close()
        self.vector_store.close()
        self.cache_manager.close()

    def __enter__(self) -> SearchService:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
