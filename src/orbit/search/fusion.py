"""Reciprocal Rank Fusion (RRF) and graph proximity boosting algorithms."""

from __future__ import annotations

from typing import Any, Optional

from orbit.models import SearchResult

# Graph proximity multipliers based on undirected hop distance from focus note
HOP_MULTIPLIERS: dict[int, float] = {
    0: 1.40,  # Focus note itself
    1: 1.25,  # Direct 1-hop neighbor
    2: 1.10,  # 2-hop neighbor
}
DEFAULT_MULTIPLIER: float = 1.00


def compute_rrf(
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    k: int = 60,
) -> list[SearchResult]:
    """Combine dense and sparse search rankings using Reciprocal Rank Fusion."""
    chunk_meta: dict[str, dict[str, Any]] = {}
    dense_scores: dict[str, float] = {}
    sparse_scores: dict[str, float] = {}
    rrf_scores: dict[str, float] = {}

    # 1. Process dense results (ordered by distance ascending)
    for rank, doc in enumerate(dense_results, start=1):
        cid = str(doc["id"])
        chunk_meta[cid] = doc
        dense_scores[cid] = float(doc.get("_distance", 0.0))
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + rank))

    # 2. Process sparse results (ordered by BM25 score descending)
    for rank, doc in enumerate(sparse_results, start=1):
        cid = str(doc["id"])
        if cid not in chunk_meta:
            chunk_meta[cid] = doc
        sparse_scores[cid] = float(doc.get("_score", 0.0))
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + rank))

    # 3. Construct SearchResult objects
    results: list[SearchResult] = []
    for cid, base_score in rrf_scores.items():
        doc = chunk_meta[cid]
        results.append(
            SearchResult(
                chunk_id=cid,
                note_path=str(doc.get("note_path", "")),
                note_title=str(doc.get("note_title", "")),
                heading=str(doc.get("heading", "")),
                text=str(doc.get("text", "")),
                score=round(base_score, 6),
                dense_score=dense_scores.get(cid),
                sparse_score=sparse_scores.get(cid),
                graph_boost_factor=1.0,
                hop_distance=None,
            )
        )

    # Sort descending by fused RRF score
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def build_single_mode_results(
    raw_results: list[dict[str, Any]],
    mode: str,
) -> list[SearchResult]:
    """Convert raw dense or sparse retrieval records into SearchResult objects."""
    results: list[SearchResult] = []
    for rank, doc in enumerate(raw_results, start=1):
        cid = str(doc["id"])
        d_score: Optional[float] = None
        s_score: Optional[float] = None

        if mode == "dense":
            dist = float(doc.get("_distance", 0.0))
            d_score = dist
            # Invert distance for descending score ranking: 1 / (1 + dist)
            score = 1.0 / (1.0 + dist)
        else:
            bm25 = float(doc.get("_score", 0.0))
            s_score = bm25
            score = bm25

        results.append(
            SearchResult(
                chunk_id=cid,
                note_path=str(doc.get("note_path", "")),
                note_title=str(doc.get("note_title", "")),
                heading=str(doc.get("heading", "")),
                text=str(doc.get("text", "")),
                score=round(score, 6),
                dense_score=d_score,
                sparse_score=s_score,
                graph_boost_factor=1.0,
                hop_distance=None,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def apply_graph_boost(
    results: list[SearchResult],
    neighbor_hops: dict[str, int],
) -> list[SearchResult]:
    """Boost search result scores according to graph proximity to a focus note."""
    if not neighbor_hops:
        return results

    boosted: list[SearchResult] = []
    for item in results:
        hop = neighbor_hops.get(item.note_path)
        multiplier = (
            HOP_MULTIPLIERS.get(hop, DEFAULT_MULTIPLIER) if hop is not None else DEFAULT_MULTIPLIER
        )
        new_score = round(item.score * multiplier, 6)

        boosted.append(
            item.model_copy(
                update={
                    "score": new_score,
                    "graph_boost_factor": multiplier,
                    "hop_distance": hop,
                }
            )
        )

    boosted.sort(key=lambda r: r.score, reverse=True)
    return boosted
