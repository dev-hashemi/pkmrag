"""Unit tests for deterministic IR metrics calculations."""

from __future__ import annotations

from orbit.eval.metrics import (
    aggregate_metrics,
    compute_average_precision,
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
    normalize_path,
)
from orbit.eval.models import QueryEvalResult


def test_normalize_path() -> None:
    """Verify path normalization handles slashes, whitespace, and case."""
    assert normalize_path("Projects/Storage.md") == "projects/storage.md"
    assert normalize_path("/Projects/Storage.md ") == "projects/storage.md"
    assert normalize_path("  Note.md  ") == "note.md"


def test_compute_reciprocal_rank_empty() -> None:
    """Verify reciprocal rank with empty lists."""
    assert compute_reciprocal_rank([], ["a.md"]) == (None, 0.0)
    assert compute_reciprocal_rank(["a.md"], []) == (None, 0.0)


def test_compute_reciprocal_rank_matches() -> None:
    """Verify reciprocal rank calculation at various hit positions."""
    # Rank 1 hit
    rank, rr = compute_reciprocal_rank(["A.md", "B.md"], ["a.md"])
    assert rank == 1
    assert rr == 1.0

    # Rank 2 hit
    rank, rr = compute_reciprocal_rank(["C.md", "A.md", "B.md"], ["a.md"])
    assert rank == 2
    assert rr == 0.5

    # Rank 4 hit
    rank, rr = compute_reciprocal_rank(["1.md", "2.md", "3.md", "4.md"], ["4.md"])
    assert rank == 4
    assert rr == 0.25

    # No match
    rank, rr = compute_reciprocal_rank(["X.md", "Y.md"], ["Z.md"])
    assert rank is None
    assert rr == 0.0


def test_compute_recall_at_k() -> None:
    """Verify recall computation with single and multi-target queries."""
    # Empty cases
    assert compute_recall_at_k([], ["a.md"]) == 0.0
    assert compute_recall_at_k(["a.md"], []) == 1.0

    # Full recall (single target)
    assert compute_recall_at_k(["a.md", "b.md"], ["a.md"]) == 1.0

    # Full recall (multi-target)
    assert compute_recall_at_k(["b.md", "a.md", "c.md"], ["a.md", "b.md"]) == 1.0

    # Partial recall (1 out of 2)
    assert compute_recall_at_k(["a.md", "c.md"], ["a.md", "b.md"]) == 0.5

    # Zero recall
    assert compute_recall_at_k(["x.md", "y.md"], ["a.md", "b.md"]) == 0.0


def test_compute_precision_at_k() -> None:
    """Verify precision computation at K."""
    assert compute_precision_at_k([], ["a.md"]) == 0.0
    assert compute_precision_at_k(["a.md"], []) == 0.0

    # 1 relevant out of 5 retrieved
    assert compute_precision_at_k(["a.md", "b.md", "c.md", "d.md", "e.md"], ["a.md"]) == 0.2

    # 2 relevant out of 5 retrieved
    assert compute_precision_at_k(["a.md", "b.md", "c.md", "d.md", "e.md"], ["a.md", "b.md"]) == 0.4

    # 0 relevant
    assert compute_precision_at_k(["x.md", "y.md"], ["a.md"]) == 0.0


def test_compute_average_precision() -> None:
    """Verify Average Precision (AP) calculation."""
    assert compute_average_precision([], ["a.md"]) == 0.0
    assert compute_average_precision(["a.md"], []) == 0.0

    # Hit at rank 1 of 1 expected -> AP = 1.0
    assert compute_average_precision(["a.md", "b.md"], ["a.md"]) == 1.0

    # Hit at rank 2 of 1 expected -> AP = (1/2) / 1 = 0.5
    assert compute_average_precision(["b.md", "a.md"], ["a.md"]) == 0.5

    # Hits at rank 1 and 2 for 2 expected -> AP = ((1/1) + (2/2)) / 2 = 1.0
    assert compute_average_precision(["a.md", "b.md"], ["a.md", "b.md"]) == 1.0

    # Hits at rank 1 and 3 for 2 expected -> AP = ((1/1) + (2/3)) / 2 = (1 + 0.6667)/2 = 0.8333
    assert compute_average_precision(["a.md", "c.md", "b.md"], ["a.md", "b.md"]) == 0.8333


def test_aggregate_metrics_empty() -> None:
    """Verify aggregation handles empty result list."""
    metrics = aggregate_metrics([])
    assert metrics.total_queries == 0
    assert metrics.mrr == 0.0


def test_aggregate_metrics_computation() -> None:
    """Verify aggregation correctly computes MRR, recall, hits, and multi-hop stats."""
    results = [
        QueryEvalResult(
            query_id="q1",
            query="Q1",
            expected_notes=["a.md"],
            retrieved_notes=["a.md", "b.md"],
            first_hit_rank=1,
            reciprocal_rank=1.0,
            recall=1.0,
            precision=0.5,
            average_precision=1.0,
            is_multi_hop=False,
            multi_hop_complete=False,
        ),
        QueryEvalResult(
            query_id="q2",
            query="Q2",
            expected_notes=["b.md", "c.md"],
            retrieved_notes=["x.md", "b.md", "c.md"],
            first_hit_rank=2,
            reciprocal_rank=0.5,
            recall=1.0,
            precision=0.6667,
            average_precision=0.5833,
            is_multi_hop=True,
            multi_hop_complete=True,
        ),
        QueryEvalResult(
            query_id="q3",
            query="Q3",
            expected_notes=["d.md", "e.md"],
            retrieved_notes=["x.md", "d.md"],
            first_hit_rank=2,
            reciprocal_rank=0.5,
            recall=0.5,
            precision=0.5,
            average_precision=0.25,
            is_multi_hop=True,
            multi_hop_complete=False,
        ),
    ]

    metrics = aggregate_metrics(results)
    assert metrics.total_queries == 3
    # MRR: (1.0 + 0.5 + 0.5) / 3 = 0.6667
    assert metrics.mrr == 0.6667
    # Hits: rank 1 = 1/3 (0.3333), rank <= 3 = 3/3 (1.0)
    assert metrics.hits_at_1 == 0.3333
    assert metrics.hits_at_3 == 1.0
    assert metrics.hits_at_5 == 1.0
    # Mean recall: (1.0 + 1.0 + 0.5) / 3 = 0.8333
    assert metrics.mean_recall_at_5 == 0.8333
    # Multi-hop: 2 queries, 1 complete -> 50%
    assert metrics.multi_hop_queries == 2
    assert metrics.multi_hop_completeness == 0.5
