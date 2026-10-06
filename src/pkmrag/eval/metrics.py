"""Deterministic Information Retrieval (IR) metrics calculations."""

from __future__ import annotations

from typing import Optional

from pkmrag.eval.models import EvalMetrics, QueryEvalResult


def normalize_path(path: str) -> str:
    """Normalize a note path for case-insensitive matching."""
    return path.strip().lstrip("/").lower()


def compute_reciprocal_rank(
    retrieved: list[str],
    expected: list[str],
) -> tuple[Optional[int], float]:
    """Find the 1-based rank of the first relevant note retrieved and compute 1/rank."""
    if not retrieved or not expected:
        return None, 0.0

    exp_set = {normalize_path(p) for p in expected}
    for rank, p in enumerate(retrieved, start=1):
        if normalize_path(p) in exp_set:
            return rank, 1.0 / rank

    return None, 0.0


def compute_recall_at_k(retrieved: list[str], expected: list[str]) -> float:
    """Compute fraction of expected relevant notes that were retrieved in top K."""
    if not expected:
        return 1.0
    if not retrieved:
        return 0.0

    exp_set = {normalize_path(p) for p in expected}
    ret_set = {normalize_path(p) for p in retrieved}
    hits = len(ret_set.intersection(exp_set))
    return round(hits / len(exp_set), 4)


def compute_precision_at_k(retrieved: list[str], expected: list[str]) -> float:
    """Compute fraction of retrieved notes that are relevant."""
    if not retrieved:
        return 0.0
    if not expected:
        return 0.0

    exp_set = {normalize_path(p) for p in expected}
    ret_set = {normalize_path(p) for p in retrieved}
    hits = len(ret_set.intersection(exp_set))
    return round(hits / len(retrieved), 4)


def compute_average_precision(retrieved: list[str], expected: list[str]) -> float:
    """Compute Average Precision (AP) rewarding relevant notes at higher ranks."""
    if not retrieved or not expected:
        return 0.0

    exp_set = {normalize_path(p) for p in expected}
    hits = 0
    prec_sum = 0.0

    for i, p in enumerate(retrieved, start=1):
        if normalize_path(p) in exp_set:
            hits += 1
            prec_sum += hits / i

    return round(prec_sum / len(exp_set), 4) if exp_set else 0.0


def aggregate_metrics(results: list[QueryEvalResult]) -> EvalMetrics:
    """Aggregate individual query scores into summary IR metrics."""
    if not results:
        return EvalMetrics()

    n = len(results)
    mrr = sum(r.reciprocal_rank for r in results) / n
    h1 = sum(1 for r in results if r.first_hit_rank == 1) / n
    h3 = sum(1 for r in results if r.first_hit_rank is not None and r.first_hit_rank <= 3) / n
    h5 = sum(1 for r in results if r.first_hit_rank is not None and r.first_hit_rank <= 5) / n
    recall_5 = sum(r.recall for r in results) / n
    prec_5 = sum(r.precision for r in results) / n
    map_5 = sum(r.average_precision for r in results) / n

    multi_hops = [r for r in results if r.is_multi_hop]
    mh_count = len(multi_hops)
    comp_hits = sum(1 for r in multi_hops if r.multi_hop_complete)
    mh_complete = comp_hits / mh_count if mh_count > 0 else 0.0

    return EvalMetrics(
        total_queries=n,
        mrr=round(mrr, 4),
        hits_at_1=round(h1, 4),
        hits_at_3=round(h3, 4),
        hits_at_5=round(h5, 4),
        mean_recall_at_5=round(recall_5, 4),
        mean_precision_at_5=round(prec_5, 4),
        map_at_5=round(map_5, 4),
        multi_hop_queries=mh_count,
        multi_hop_completeness=round(mh_complete, 4),
    )
