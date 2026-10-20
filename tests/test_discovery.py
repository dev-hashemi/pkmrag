"""Tests for semantic gap discovery and LLM classification."""

from __future__ import annotations

from pathlib import Path

from pkmrag.discovery.engine import GapDiscoveryEngine
from pkmrag.graph import GraphStore
from pkmrag.graph.traversal import get_inferred_relationships
from pkmrag.inference.base import InferredRelationshipResult
from pkmrag.inference.provider import MockInferenceProvider


def test_gap_discovery_finds_unlinked_notes(semantic_gap_vault: Path) -> None:
    """Verify that unlinked semantically similar notes are discovered and classified."""
    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="EXTENDS",
            confidence=0.91,
            reason="Redlock extends general distributed locking concepts to Redis clusters.",
        )
    )

    engine = GapDiscoveryEngine(semantic_gap_vault, inference_provider=mock_provider)
    try:
        candidates, inferred, stats = engine.discover(similarity_threshold=0.50, limit=10)
    finally:
        engine.close()

    # Candidates should include DistributedLocks and RedlockAlgorithm
    candidate_pairs = {(c.source_path, c.target_path) for c in candidates}
    assert ("DistributedLocks.md", "RedlockAlgorithm.md") in candidate_pairs or (
        "RedlockAlgorithm.md",
        "DistributedLocks.md",
    ) in candidate_pairs

    # Linked pair (DistributedLocks, ConsensusProtocols) should NOT be in candidates
    assert ("DistributedLocks.md", "ConsensusProtocols.md") not in candidate_pairs
    assert ("ConsensusProtocols.md", "DistributedLocks.md") not in candidate_pairs

    # Sourdough should NOT be paired with DistributedLocks
    assert ("DistributedLocks.md", "SourdoughBread.md") not in candidate_pairs

    # Inferred relationship should be created
    assert len(inferred) >= 1
    rel = inferred[0]
    assert rel.rel_type == "EXTENDS"
    assert rel.confidence == 0.91
    assert "Redlock" in rel.reason

    # Verify persistence in LadybugDB
    graph = GraphStore(semantic_gap_vault / ".pkmrag" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) >= 1
    assert stored[0].rel_type == "EXTENDS"


def test_gap_discovery_dry_run(semantic_gap_vault: Path) -> None:
    """Verify dry-run returns candidates without calling LLM or writing to database."""
    mock_provider = MockInferenceProvider()
    engine = GapDiscoveryEngine(semantic_gap_vault, inference_provider=mock_provider)
    try:
        candidates, inferred, stats = engine.discover(
            similarity_threshold=0.50, limit=10, dry_run=True
        )
    finally:
        engine.close()

    assert len(candidates) >= 1
    assert len(inferred) == 0
    assert len(mock_provider.calls) == 0

    # Verify nothing was persisted
    graph = GraphStore(semantic_gap_vault / ".pkmrag" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) == 0


def test_gap_discovery_none_classification_discarded(semantic_gap_vault: Path) -> None:
    """Verify that relationship classified as NONE is not stored in the database."""
    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="NONE",
            confidence=0.2,
            reason="Notes share vocabulary but have no conceptual relationship.",
        )
    )

    engine = GapDiscoveryEngine(semantic_gap_vault, inference_provider=mock_provider)
    try:
        candidates, inferred, stats = engine.discover(similarity_threshold=0.50, limit=10)
    finally:
        engine.close()

    assert len(candidates) >= 1
    assert len(inferred) == 0

    graph = GraphStore(semantic_gap_vault / ".pkmrag" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) == 0


def test_gap_discovery_skips_already_inferred(semantic_gap_vault: Path) -> None:
    """Verify that existing inferred relationships are skipped on repeated runs."""
    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="EXTENDS",
            confidence=0.88,
            reason="Test relationship",
        )
    )

    engine = GapDiscoveryEngine(semantic_gap_vault, inference_provider=mock_provider)
    try:
        _, inferred1, _ = engine.discover(similarity_threshold=0.50, limit=10)
        assert len(inferred1) >= 1
        initial_calls = len(mock_provider.calls)

        # Second run should skip already inferred relationship
        _, inferred2, _ = engine.discover(similarity_threshold=0.50, limit=10)
        assert len(inferred2) == 0
        assert len(mock_provider.calls) == initial_calls
    finally:
        engine.close()
