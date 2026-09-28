"""Unit tests for RRF fusion and graph proximity boosting."""

from __future__ import annotations

from orbit.models import SearchResult
from orbit.search.fusion import apply_graph_boost, build_single_mode_results, compute_rrf


def test_rrf_scoring_and_ranking() -> None:
    """Verify reciprocal rank fusion ranks items present in both streams higher."""
    dense = [
        {"id": "c1", "note_path": "a.md", "note_title": "A", "text": "text a", "_distance": 0.1},
        {"id": "c2", "note_path": "b.md", "note_title": "B", "text": "text b", "_distance": 0.2},
    ]
    sparse = [
        {"id": "c2", "note_path": "b.md", "note_title": "B", "text": "text b", "_score": 5.0},
        {"id": "c3", "note_path": "c.md", "note_title": "C", "text": "text c", "_score": 3.0},
    ]

    fused = compute_rrf(dense, sparse, k=60)
    assert len(fused) == 3
    # c2 appears in both streams (rank 2 in dense, rank 1 in sparse) -> should rank #1
    assert fused[0].chunk_id == "c2"
    assert fused[0].score > fused[1].score


def test_graph_proximity_boost() -> None:
    """Verify graph proximity multipliers elevate close nodes."""
    results = [
        SearchResult(
            chunk_id="c1",
            note_path="far.md",
            note_title="Far",
            text="text far",
            score=0.030,
        ),
        SearchResult(
            chunk_id="c2",
            note_path="near.md",
            note_title="Near",
            text="text near",
            score=0.026,
        ),
    ]

    # near.md is 1 hop away (x1.25), far.md is not linked (x1.00)
    # near.md boosted: 0.026 * 1.25 = 0.0325 > 0.030
    hops = {"focus.md": 0, "near.md": 1}
    boosted = apply_graph_boost(results, hops)

    assert boosted[0].chunk_id == "c2"
    assert boosted[0].graph_boost_factor == 1.25
    assert boosted[0].hop_distance == 1
    assert boosted[1].chunk_id == "c1"
    assert boosted[1].graph_boost_factor == 1.00


def test_single_mode_conversions() -> None:
    """Verify single-mode results conversion for dense and sparse."""
    dense_docs = [
        {"id": "c1", "note_path": "a.md", "note_title": "A", "text": "t", "_distance": 0.0},
        {"id": "c2", "note_path": "b.md", "note_title": "B", "text": "t", "_distance": 1.0},
    ]
    res_dense = build_single_mode_results(dense_docs, mode="dense")
    assert res_dense[0].score == 1.0  # 1 / (1 + 0)
    assert res_dense[1].score == 0.5  # 1 / (1 + 1)

    sparse_docs = [
        {"id": "c1", "note_path": "a.md", "note_title": "A", "text": "t", "_score": 10.5},
    ]
    res_sparse = build_single_mode_results(sparse_docs, mode="sparse")
    assert res_sparse[0].score == 10.5
