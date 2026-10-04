"""Shared pytest fixtures for Project Orbit test suite."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from orbit.graph.store import GraphStore


@pytest.fixture
def mock_vault(tmp_path: Path) -> Path:
    """Create a temporary directory structure mimicking a small linked Obsidian vault."""
    vault = tmp_path / "test_vault"
    vault.mkdir(parents=True, exist_ok=True)

    (vault / "Alpha.md").write_text(
        "# Alpha\n\nCore architecture documentation linking to [[Beta]] and [[UnresolvedNote]].\n\n"
        "#orbit\n",
        encoding="utf-8",
    )
    (vault / "Beta.md").write_text(
        "# Beta\n\nBeta subsystem extending Alpha concepts.\n\n#orbit #systems\n",
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
