"""Calibrated document and section relatedness scoring engine."""

from __future__ import annotations

from typing import NamedTuple, Sequence

import numpy as np

from pkmrag.models import ChunkPairMatch

# Dead zone: cross-note chunk pairs below this cosine threshold are treated as noise.
CHUNK_DEAD_ZONE_FLOOR = 0.65
REUSE_DISCOUNT = 0.50


class ChunkInput(NamedTuple):
    """Chunk representation passed into the relatedness scorer."""

    chunk_id: str
    heading: str
    text: str
    vector: Sequence[float]


class NotePairScore(NamedTuple):
    """Result of scoring two notes via their chunk cross-similarity matrix."""

    final_score: float
    resemblance: float
    containment: float
    best_similarity: float
    relationship_type: str
    ui_summary: str
    cover_a: float
    cover_b: float
    matched_chunks: list[ChunkPairMatch]


def _estimate_words(text: str) -> int:
    return max(1, len(text.split()))


def _greedy_dedup_row_max(
    g_matrix: np.ndarray,
    reuse_discount: float = REUSE_DISCOUNT,
) -> np.ndarray:
    """Discount repeated claims on the same target chunk to avoid star-graph collapse."""
    m, n = g_matrix.shape
    row_best = g_matrix.max(axis=1)
    row_argmax = g_matrix.argmax(axis=1)

    order = np.argsort(row_best)[::-1]
    col_claims = np.zeros(n, dtype=np.int32)
    adjusted = np.zeros(m, dtype=np.float32)

    for r in order:
        val = float(row_best[r])
        if val <= 0.0:
            break
        c = int(row_argmax[r])
        adjusted[r] = val * (reuse_discount ** int(col_claims[c]))
        col_claims[c] += 1

    return adjusted


def score_note_chunks(
    chunks_a: list[ChunkInput],
    chunks_b: list[ChunkInput],
    min_evidence_floor: float = CHUNK_DEAD_ZONE_FLOOR,
) -> NotePairScore:
    """Compute exact chunk cross-similarity matrix and classify note relationship."""
    m, n = len(chunks_a), len(chunks_b)
    if m == 0 or n == 0:
        return NotePairScore(
            final_score=0.0,
            resemblance=0.0,
            containment=0.0,
            best_similarity=0.0,
            relationship_type="WEAK_OVERLAP",
            ui_summary="No content to compare",
            cover_a=0.0,
            cover_b=0.0,
            matched_chunks=[],
        )

    # 1. Compute full raw cosine matrix
    va = np.array([c.vector for c in chunks_a], dtype=np.float32)
    vb = np.array([c.vector for c in chunks_b], dtype=np.float32)
    s_raw = va @ vb.T
    best_raw_cos = float(np.max(s_raw))

    if best_raw_cos < min_evidence_floor:
        return NotePairScore(
            final_score=0.0,
            resemblance=0.0,
            containment=0.0,
            best_similarity=best_raw_cos,
            relationship_type="WEAK_OVERLAP",
            ui_summary="Below significance floor",
            cover_a=0.0,
            cover_b=0.0,
            matched_chunks=[],
        )

    # 2. Dead zone: zero out noise below threshold
    g = np.where(s_raw >= CHUNK_DEAD_ZONE_FLOOR, s_raw, 0.0).astype(np.float32)

    # 3. Sublinear length weights
    wa = np.array([np.sqrt(np.clip(_estimate_words(c.text), 15.0, 400.0)) for c in chunks_a])
    wb = np.array([np.sqrt(np.clip(_estimate_words(c.text), 15.0, 400.0)) for c in chunks_b])
    sum_wa = float(wa.sum())
    sum_wb = float(wb.sum())

    # 4. Bidirectional discounted coverage
    g_a_to_b = _greedy_dedup_row_max(g, reuse_discount=REUSE_DISCOUNT)
    g_b_to_a = _greedy_dedup_row_max(g.T, reuse_discount=REUSE_DISCOUNT)

    cover_a = float(np.sum(wa * g_a_to_b) / max(sum_wa, 1e-6))
    cover_b = float(np.sum(wb * g_b_to_a) / max(sum_wb, 1e-6))

    resemblance = (
        (2.0 * cover_a * cover_b / (cover_a + cover_b)) if (cover_a + cover_b) > 0 else 0.0
    )
    containment = max(cover_a, cover_b)

    # 5. Extract all qualified 1-to-1 non-overlapping chunk evidence
    flat_indices = np.argsort(s_raw.ravel())[::-1]
    used_a: set[int] = set()
    used_b: set[int] = set()
    matched_chunks: list[ChunkPairMatch] = []

    for flat_idx in flat_indices:
        i, j = int(flat_idx // n), int(flat_idx % n)
        sim = float(s_raw[i, j])
        if sim < min_evidence_floor:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        matched_chunks.append(
            ChunkPairMatch(
                source_chunk_id=chunks_a[i].chunk_id,
                target_chunk_id=chunks_b[j].chunk_id,
                source_chunk_text=chunks_a[i].text,
                target_chunk_text=chunks_b[j].text,
                similarity=round(sim, 4),
                source_heading=chunks_a[i].heading,
                target_heading=chunks_b[j].heading,
            )
        )

    # 6. Classify relationship type and compute balanced score
    num_matches = len(matched_chunks)

    # If one note is small (<= 2 chunks) or heavily asymmetric, classify as CONTAINMENT
    if containment >= 0.50 and (min(m, n) <= 2 or containment >= 1.8 * max(resemblance, 1e-4)):
        rel_type = "CONTAINMENT"
        smaller_label = "this note" if cover_a >= cover_b else "target note"
        ui_summary = f"Covers {int(round(containment * 100))}% of {smaller_label}"
    elif (resemblance >= 0.18 and min(cover_a, cover_b) >= 0.12) or (
        num_matches >= 3 and resemblance >= 0.14
    ):
        rel_type = "DEEP_OVERLAP"
        ui_summary = (
            f"Covers {int(round(cover_a * 100))}% of this note · "
            f"{int(round(cover_b * 100))}% of target"
        )
    elif best_raw_cos >= 0.72:
        rel_type = "SHARED_CONCEPT"
        ui_summary = f"Strong shared section ({int(round(best_raw_cos * 100))}% match)"
    else:
        rel_type = "WEAK_OVERLAP"
        ui_summary = f"Partial match ({int(round(best_raw_cos * 100))}% peak)"

    final_score = min(0.99, best_raw_cos * (0.30 + 0.70 * min(cover_a, cover_b)))

    return NotePairScore(
        final_score=round(final_score, 4),
        resemblance=round(resemblance, 4),
        containment=round(containment, 4),
        best_similarity=round(best_raw_cos, 4),
        relationship_type=rel_type,
        ui_summary=ui_summary,
        cover_a=round(cover_a, 4),
        cover_b=round(cover_b, 4),
        matched_chunks=matched_chunks,
    )
