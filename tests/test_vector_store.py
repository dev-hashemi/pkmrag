"""Unit tests for LanceDB VectorStore."""

from __future__ import annotations

from pathlib import Path

from pkmrag.models import ChunkMetadata
from pkmrag.search.vector_store import VectorStore


def test_vector_store_lifecycle_and_search(tmp_path: Path) -> None:
    """Verify VectorStore upsert, dense vector search, and sparse BM25 search."""
    store_dir = tmp_path / "vectors"
    dimension = 4

    chunks_a = [
        ChunkMetadata(
            chunk_id="notes/graph.md#chunk_0",
            note_path="notes/graph.md",
            note_title="Graph Notes",
            heading="# Graph Notes",
            text="LadybugDB provides graph traversal and query capabilities.",
            chunk_index=0,
            token_count=8,
        )
    ]
    vecs_a = [[1.0, 0.0, 0.0, 0.0]]

    chunks_b = [
        ChunkMetadata(
            chunk_id="notes/vector.md#chunk_0",
            note_path="notes/vector.md",
            note_title="Vector Notes",
            heading="# Vector Notes",
            text="LanceDB is an embedded columnar vector database.",
            chunk_index=0,
            token_count=7,
        )
    ]
    vecs_b = [[0.0, 1.0, 0.0, 0.0]]

    with VectorStore(store_dir, dimension=dimension) as store:
        store.upsert_chunks("notes/graph.md", chunks_a, vecs_a, mtime=100.0)
        store.upsert_chunks("notes/vector.md", chunks_b, vecs_b, mtime=105.0)

        assert store.get_total_chunks() == 2
        tracked = store.get_tracked_notes()
        assert tracked["notes/graph.md"] == 100.0
        assert tracked["notes/vector.md"] == 105.0

        # Dense search close to vector A
        dense_hits = store.search_dense([0.9, 0.1, 0.0, 0.0], limit=2)
        assert len(dense_hits) >= 1
        assert dense_hits[0]["note_path"] == "notes/graph.md"

        # Sparse BM25 search
        sparse_hits = store.search_sparse("LanceDB", limit=2)
        assert len(sparse_hits) >= 1
        assert sparse_hits[0]["note_path"] == "notes/vector.md"

        # Delete note chunks
        store.delete_note_chunks("notes/graph.md")
        assert store.get_total_chunks() == 1
        assert "notes/graph.md" not in store.get_tracked_notes()
