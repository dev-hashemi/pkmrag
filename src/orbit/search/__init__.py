"""Search package: hierarchical chunking, vector embeddings, and hybrid fusion."""

from __future__ import annotations

from orbit.models import SearchResult
from orbit.search.chunker import HierarchicalMarkdownChunker
from orbit.search.embedder import EmbeddingProvider, FastEmbedProvider
from orbit.search.fusion import apply_graph_boost, compute_rrf
from orbit.search.service import SearchService
from orbit.search.vector_store import VectorStore

__all__ = [
    "EmbeddingProvider",
    "FastEmbedProvider",
    "HierarchicalMarkdownChunker",
    "SearchResult",
    "SearchService",
    "VectorStore",
    "apply_graph_boost",
    "compute_rrf",
]
