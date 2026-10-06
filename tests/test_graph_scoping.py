"""Tests verifying ground-truth link isolation from inferred relationships."""

from __future__ import annotations

from pathlib import Path

from pkmrag.graph import GraphStore
from pkmrag.graph.paths import find_shortest_bridge
from pkmrag.graph.traversal import (
    add_inferred_relationship,
    get_inferred_relationships,
    get_neighbor_hops,
)
from pkmrag.models import InferredRelationship


def test_inferred_relationship_does_not_bleed_into_links_to_traversals(
    tmp_path: Path,
) -> None:
    """Verify that INFERRED_REL edges are excluded from LINKS_TO graph traversals and paths."""
    db_path = tmp_path / "test_graph"
    store = GraphStore(db_path, read_only=False)

    # 1. Add three notes: A, B, and C
    # Only A -> C has an explicit LINKS_TO edge
    store.upsert_note(
        path="NoteA.md",
        title="Note A",
        content_hash="hashA",
        mtime=1.0,
    )
    store.upsert_note(
        path="NoteB.md",
        title="Note B",
        content_hash="hashB",
        mtime=1.0,
    )
    store.upsert_note(
        path="NoteC.md",
        title="Note C",
        content_hash="hashC",
        mtime=1.0,
    )
    store.add_links_to(from_path="NoteA.md", to_path="NoteC.md")

    # 2. Add an INFERRED_REL between Note A and Note B (AI discovered)
    add_inferred_relationship(
        store.conn,
        InferredRelationship(
            source_path="NoteA.md",
            target_path="NoteB.md",
            rel_type="EXTENDS",
            confidence=0.92,
            reason="Note B extends Note A",
            model="test-model",
        ),
    )

    # 3. Verify get_inferred_relationships retrieves it
    inferred = get_inferred_relationships(store.conn, "NoteA.md")
    assert len(inferred) == 1
    assert inferred[0].target_path == "NoteB.md"
    assert inferred[0].rel_type == "EXTENDS"

    # 4. Verify get_neighbor_hops for NoteA DOES NOT include NoteB
    # Hop 1 should ONLY include NoteC and NoteA
    hop_dict = get_neighbor_hops(store.conn, "NoteA.md", max_hops=2)
    assert "NoteC.md" in hop_dict
    assert hop_dict["NoteC.md"] == 1
    assert "NoteB.md" not in hop_dict

    # 5. Verify find_shortest_bridge between NoteA and NoteB returns NO path
    bridge = find_shortest_bridge(store.conn, "NoteA.md", "NoteB.md", max_hops=3)
    assert not bridge.found
    assert bridge.hops == -1

    store.close()
