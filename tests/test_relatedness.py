"""Unit tests for calibrated document and section relatedness scoring."""

from __future__ import annotations

import numpy as np

from pkmrag.discovery.relatedness import ChunkInput, score_note_chunks


def _make_unit_vector(rng: np.random.Generator, dim: int = 384) -> list[float]:
    v = rng.normal(size=dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return [float(x) for x in v]


def _make_blended_vector(base: list[float], mix: float, rng: np.random.Generator) -> list[float]:
    noise = np.array(_make_unit_vector(rng), dtype=np.float32)
    b = np.array(base, dtype=np.float32)
    v = (1.0 - mix) * noise + mix * b
    v /= np.linalg.norm(v)
    return [float(x) for x in v]


def test_40x30_shared_topics_classified_as_deep_overlap() -> None:
    """Verifies that large notes sharing multiple topics are not penalized by length."""
    rng = np.random.default_rng(42)
    shared_topics = [_make_unit_vector(rng) for _ in range(10)]

    chunks_a = [
        ChunkInput(
            chunk_id=f"a_{i}",
            heading=f"# A > ## Sec {i}",
            text="Detailed paragraph on architecture and distributed systems. " * 5,
            vector=_make_blended_vector(shared_topics[i], 0.90, rng)
            if i < 10
            else _make_unit_vector(rng),
        )
        for i in range(40)
    ]
    chunks_b = [
        ChunkInput(
            chunk_id=f"b_{j}",
            heading=f"# B > ## Sec {j}",
            text="Corresponding discussion of architectural design trade-offs. " * 5,
            vector=_make_blended_vector(shared_topics[j], 0.90, rng)
            if j < 10
            else _make_unit_vector(rng),
        )
        for j in range(30)
    ]

    result = score_note_chunks(chunks_a, chunks_b)
    assert result.relationship_type == "DEEP_OVERLAP"
    assert result.final_score >= 0.40
    assert result.resemblance >= 0.25
    # All 10 shared sections should be captured as evidence, not truncated to 5!
    assert len(result.matched_chunks) == 10
    assert "Covers" in result.ui_summary


def test_atomic_note_inside_large_note_classified_as_containment() -> None:
    """Verifies that a short 1-chunk note matching a section in a 35-chunk note gets CONTAINMENT."""
    rng = np.random.default_rng(101)
    shared_concept = _make_unit_vector(rng)

    chunk_atomic = [
        ChunkInput(
            chunk_id="atomic_0",
            heading="# Cognitive Load",
            text="Working memory capacity limits the information processed simultaneously.",
            vector=shared_concept,
        )
    ]

    chunks_hub = [
        ChunkInput(
            chunk_id=f"hub_{j}",
            heading=f"# Learning Guide > ## Section {j}",
            text="Comprehensive educational psychology and learning theory material. " * 8,
            vector=shared_concept if j == 3 else _make_unit_vector(rng),
        )
        for j in range(35)
    ]

    result = score_note_chunks(chunk_atomic, chunks_hub)
    assert result.relationship_type == "CONTAINMENT"
    assert result.containment >= 0.70
    assert result.final_score >= 0.30
    assert len(result.matched_chunks) == 1
    assert result.matched_chunks[0].target_heading == "# Learning Guide > ## Section 3"
    assert "this note" in result.ui_summary


def test_single_strong_passage_classified_as_shared_concept() -> None:
    """Verifies that notes with different overall scope but one strong link get SHARED_CONCEPT."""
    rng = np.random.default_rng(202)
    shared_concept = _make_unit_vector(rng)

    chunks_a = [
        ChunkInput(
            chunk_id=f"a_{i}",
            heading=f"# Note A > ## Sec {i}",
            text="General body text for note A. " * 6,
            vector=shared_concept if i == 0 else _make_unit_vector(rng),
        )
        for i in range(12)
    ]
    chunks_b = [
        ChunkInput(
            chunk_id=f"b_{j}",
            heading=f"# Note B > ## Sec {j}",
            text="General body text for note B. " * 6,
            vector=shared_concept if j == 5 else _make_unit_vector(rng),
        )
        for j in range(15)
    ]

    result = score_note_chunks(chunks_a, chunks_b)
    assert result.relationship_type == "SHARED_CONCEPT"
    assert result.best_similarity >= 0.95
    assert len(result.matched_chunks) == 1
    assert "Strong shared section" in result.ui_summary


def test_unrelated_notes_produce_zero_score() -> None:
    """Verifies that unrelated notes with noise similarities are filtered out."""
    rng = np.random.default_rng(303)
    chunks_a = [
        ChunkInput(
            chunk_id=f"a_{i}",
            heading=f"# A > ## Sec {i}",
            text="Random topic A content",
            vector=_make_unit_vector(rng),
        )
        for i in range(10)
    ]
    chunks_b = [
        ChunkInput(
            chunk_id=f"b_{j}",
            heading=f"# B > ## Sec {j}",
            text="Completely different topic B content",
            vector=_make_unit_vector(rng),
        )
        for j in range(10)
    ]

    result = score_note_chunks(chunks_a, chunks_b)
    # Cosine between two random 384-d vectors is near 0.0 (well below 0.65 floor)
    assert result.final_score == 0.0
    assert result.relationship_type == "WEAK_OVERLAP"
    assert len(result.matched_chunks) == 0


def test_duplicate_chunk_in_same_note_is_discounted() -> None:
    """Verifies that copy-pasting the same matching paragraph 5x does not inflate coverage."""
    rng = np.random.default_rng(404)
    shared_vec = _make_unit_vector(rng)

    # Note A has 1 match + 4 unrelated
    chunks_single = [ChunkInput("s_0", "# H", "Matching paragraph text", shared_vec)] + [
        ChunkInput(f"s_{i}", "# H", "Other paragraph", _make_unit_vector(rng)) for i in range(1, 5)
    ]

    # Note A-cloned duplicates the matching paragraph 5 times (8 chunks total)
    chunks_cloned = [
        ChunkInput(f"c_{k}", "# H", "Matching paragraph text", shared_vec) for k in range(5)
    ] + [
        ChunkInput(f"c_o_{i}", "# H", "Other paragraph", _make_unit_vector(rng))
        for i in range(1, 4)
    ]

    chunks_target = [ChunkInput("t_0", "# H", "Target matching paragraph text", shared_vec)] + [
        ChunkInput(f"t_{j}", "# H", "Target other paragraph", _make_unit_vector(rng))
        for j in range(1, 5)
    ]

    res_single = score_note_chunks(chunks_single, chunks_target)
    res_cloned = score_note_chunks(chunks_cloned, chunks_target)

    # Cloned note should not inflate resemblance substantially (claimed chunk discounted)
    assert abs(res_cloned.resemblance - res_single.resemblance) < 0.10
