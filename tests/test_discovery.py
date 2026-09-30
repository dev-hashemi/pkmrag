"""Tests for semantic gap discovery engine."""

from __future__ import annotations

from pathlib import Path

from orbit.discovery.engine import GapDiscoveryEngine
from orbit.graph import GraphStore
from orbit.graph.traversal import get_inferred_relationships
from orbit.inference.base import InferredRelationshipResult
from orbit.inference.provider import MockInferenceProvider
from orbit.ingest import IngestPipeline


def _setup_test_vault(vault: Path) -> None:
    """Create a synthetic vault with linked and unlinked semantically similar notes."""
    vault.mkdir(parents=True, exist_ok=True)

    # Note A and Note B are unlinked but both about distributed lock managers
    (vault / "DistributedLocks.md").write_text(
        "# Distributed Lock Managers\n\n"
        "Distributed locks provide mutual exclusion across networked nodes.\n"
        "They rely on leases, fencing tokens, and distributed consensus mechanisms.\n"
        "See also [[ConsensusProtocols]].\n"
    )
    (vault / "RedlockAlgorithm.md").write_text(
        "# Redis Redlock Algorithm\n\n"
        "Redlock is a distributed locking algorithm for Redis clusters.\n"
        "It uses multiple independent Redis masters to achieve fault-tolerant locks.\n"
    )
    # Note C is explicitly linked to Note A (distance = 1)
    (vault / "ConsensusProtocols.md").write_text(
        "# Consensus Protocols\n\n"
        "Consensus protocols like Raft and Paxos allow nodes to agree on values.\n"
        "Distributed lock managers often build upon consensus primitives.\n"
    )
    # Note D is completely unrelated
    (vault / "SourdoughBread.md").write_text(
        "# Sourdough Bread\n\n"
        "Flour, water, wild yeast starter, and salt fermented over 24 hours.\n"
        "Bake in a Dutch oven at 230C with steam.\n"
    )

    pipeline = IngestPipeline(vault, target="all")
    pipeline.run()


def test_gap_discovery_finds_unlinked_notes(tmp_path: Path) -> None:
    """Verify that unlinked semantically similar notes are discovered and classified."""
    vault = tmp_path / "vault"
    _setup_test_vault(vault)

    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="EXTENDS",
            confidence=0.91,
            reason="Redlock extends general distributed locking concepts to Redis clusters.",
        )
    )

    engine = GapDiscoveryEngine(vault, inference_provider=mock_provider)
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
    graph = GraphStore(vault / ".orbit" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) >= 1
    assert stored[0].rel_type == "EXTENDS"


def test_gap_discovery_dry_run(tmp_path: Path) -> None:
    """Verify dry-run returns candidates without calling LLM or writing to database."""
    vault = tmp_path / "vault"
    _setup_test_vault(vault)

    mock_provider = MockInferenceProvider()
    engine = GapDiscoveryEngine(vault, inference_provider=mock_provider)
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
    graph = GraphStore(vault / ".orbit" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) == 0


def test_gap_discovery_none_classification_discarded(tmp_path: Path) -> None:
    """Verify that relationship classified as NONE is not stored in the database."""
    vault = tmp_path / "vault"
    _setup_test_vault(vault)

    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="NONE",
            confidence=0.2,
            reason="Notes share vocabulary but have no conceptual relationship.",
        )
    )

    engine = GapDiscoveryEngine(vault, inference_provider=mock_provider)
    try:
        candidates, inferred, stats = engine.discover(similarity_threshold=0.50, limit=10)
    finally:
        engine.close()

    assert len(candidates) >= 1
    assert len(inferred) == 0

    graph = GraphStore(vault / ".orbit" / "graph")
    stored = get_inferred_relationships(graph.conn, "DistributedLocks.md")
    graph.close()
    assert len(stored) == 0


def test_gap_discovery_skips_already_inferred(tmp_path: Path) -> None:
    """Verify that existing inferred relationships are skipped on repeated runs."""
    vault = tmp_path / "vault"
    _setup_test_vault(vault)

    mock_provider = MockInferenceProvider(
        default_rel=InferredRelationshipResult(
            rel_type="EXTENDS",
            confidence=0.88,
            reason="Test relationship",
        )
    )

    engine = GapDiscoveryEngine(vault, inference_provider=mock_provider)
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
