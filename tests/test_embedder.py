"""Unit tests for EmbeddingProvider and FastEmbedProvider."""

from __future__ import annotations

from orbit.search.embedder import EmbeddingProvider, FastEmbedProvider


def test_embedder_protocol_and_dimensions() -> None:
    """Verify FastEmbedProvider implements EmbeddingProvider with 384 dimensions."""
    provider = FastEmbedProvider()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 384
    assert provider.model_name == "BAAI/bge-small-en-v1.5"


def test_embedder_single_query_and_batch() -> None:
    """Verify single query and batch embedding inference."""
    provider = FastEmbedProvider()

    # Query embedding
    q_vec = provider.embed_query("LadybugDB graph storage")
    assert isinstance(q_vec, list)
    assert len(q_vec) == 384
    assert all(isinstance(v, float) for v in q_vec)

    # Batch embedding
    texts = [
        "First document chunk about semantic search.",
        "Second document chunk about Obsidian wikilinks.",
    ]
    doc_vecs = provider.embed_texts(texts)
    assert len(doc_vecs) == 2
    assert len(doc_vecs[0]) == 384
    assert len(doc_vecs[1]) == 384

    # Empty input handling
    assert provider.embed_texts([]) == []
