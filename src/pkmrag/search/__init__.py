"""Search package: hierarchical chunking, vector embeddings, and hybrid fusion."""

from __future__ import annotations

from pkmrag.models import SearchResult
from pkmrag.search.chunker import HierarchicalMarkdownChunker
from pkmrag.search.embedder import EmbeddingProvider, FastEmbedProvider
from pkmrag.search.fusion import apply_graph_boost, compute_rrf
from pkmrag.search.service import SearchService
from pkmrag.search.vector_store import VectorStore

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
