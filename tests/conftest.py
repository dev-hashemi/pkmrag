"""Shared pytest fixtures for PKMRAG test suite."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from pkmrag.graph.store import GraphStore
from pkmrag.ingest import IngestPipeline


@pytest.fixture
def mock_vault(tmp_path: Path) -> Path:
    """Create a temporary directory structure mimicking a small linked Obsidian vault."""
    vault = tmp_path / "test_vault"
    vault.mkdir(parents=True, exist_ok=True)

    (vault / "Alpha.md").write_text(
        "# Alpha\n\nCore architecture documentation linking to [[Beta]] and [[UnresolvedNote]].\n\n"
        "#pkmrag\n",
        encoding="utf-8",
    )
    (vault / "Beta.md").write_text(
        "# Beta\n\nBeta subsystem extending Alpha concepts.\n\n#pkmrag #systems\n",
        encoding="utf-8",
    )
    (vault / "Gamma.md").write_text(
        "# Gamma\n\nIndependent reference document.\n\n#reference\n",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def empty_graph_store(tmp_path: Path) -> Generator[GraphStore, None, None]:
    """Provide an isolated, empty LadybugDB graph store instance that cleanly closes on teardown."""
    db_dir = tmp_path / "test_graph_store"
    store = GraphStore(db_dir, read_only=False)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def semantic_gap_vault(tmp_path: Path) -> Path:
    """Create and index a vault with linked, unlinked-similar, and unrelated notes."""
    vault = tmp_path / "semantic_gap_vault"
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

    IngestPipeline(vault, target="all").run()
    return vault
