"""Tests for graph pathfinding, structural neighborhood, and vault overview queries."""

from __future__ import annotations

from pkmrag.graph.paths import (
    find_shortest_bridge,
    get_note_structural_context,
    get_vault_overview,
)
from pkmrag.graph.store import GraphStore
from pkmrag.models import HubNote, TagStat


def _populate_test_graph(store: GraphStore) -> None:
    # Nodes
    store.upsert_note("A.md", "Note A", "hA", 1.0)
    store.upsert_note("B.md", "Note B", "hB", 1.0)
    store.upsert_note("C.md", "Note C", "hC", 1.0)
    store.upsert_note("Isolated.md", "Isolated Note", "hI", 1.0)

    # Links: A -> B -> C
    store.add_links_to("A.md", "B.md")
    store.add_links_to("B.md", "C.md")

    # Tags
    store.upsert_tag("orbit")
    store.upsert_tag("deep")
    store.add_tagged_with("A.md", "orbit")
    store.add_tagged_with("B.md", "orbit")
    store.add_tagged_with("B.md", "deep")


def test_find_shortest_bridge_direct(empty_graph_store: GraphStore) -> None:
    """Verify 1-hop pathfinding between directly linked notes."""
    _populate_test_graph(empty_graph_store)

    bridge = find_shortest_bridge(empty_graph_store.conn, "A.md", "B.md")
    assert bridge.found is True
    assert bridge.hops == 1
    assert bridge.path == ["A.md", "B.md"]


def test_find_shortest_bridge_multihop(empty_graph_store: GraphStore) -> None:
    """Verify multi-hop pathfinding through intermediary notes."""
    _populate_test_graph(empty_graph_store)

    bridge = find_shortest_bridge(empty_graph_store.conn, "A.md", "C.md", max_hops=3)
    assert bridge.found is True
    assert bridge.hops == 2
    assert bridge.path == ["A.md", "B.md", "C.md"]


def test_find_shortest_bridge_self(empty_graph_store: GraphStore) -> None:
    """Verify pathfinding to the same note returns 0 hops."""
    _populate_test_graph(empty_graph_store)

    bridge = find_shortest_bridge(empty_graph_store.conn, "A.md", "A.md")
    assert bridge.found is True
    assert bridge.hops == 0
    assert bridge.path == ["A.md"]


def test_find_shortest_bridge_disconnected(empty_graph_store: GraphStore) -> None:
    """Verify disconnected notes return found=False and hops=-1."""
    _populate_test_graph(empty_graph_store)

    bridge = find_shortest_bridge(empty_graph_store.conn, "A.md", "Isolated.md")
    assert bridge.found is False
    assert bridge.hops == -1
    assert bridge.path == []


def test_find_shortest_bridge_nonexistent(empty_graph_store: GraphStore) -> None:
    """Verify querying nonexistent notes returns found=False without error."""
    _populate_test_graph(empty_graph_store)

    bridge = find_shortest_bridge(empty_graph_store.conn, "A.md", "Missing.md")
    assert bridge.found is False
    assert bridge.hops == -1


def test_get_note_structural_context(empty_graph_store: GraphStore) -> None:
    """Verify structural context aggregation for a note."""
    _populate_test_graph(empty_graph_store)

    context = get_note_structural_context(empty_graph_store.conn, "B.md")
    assert context is not None
    assert context.path == "B.md"
    assert "A.md" in context.backlinks
    assert "C.md" in context.outgoing_links
    assert "orbit" in context.tags
    assert "deep" in context.tags

    # Nonexistent note returns None
    assert get_note_structural_context(empty_graph_store.conn, "Missing.md") is None


def test_get_vault_overview_typed_models(empty_graph_store: GraphStore) -> None:
    """Verify vault overview returns typed HubNote and TagStat instances."""
    _populate_test_graph(empty_graph_store)

    overview = get_vault_overview(empty_graph_store.conn, limit=10)
    assert overview.total_notes == 4
    assert overview.total_links == 2
    assert overview.total_tags == 2

    # Hub notes must be instances of HubNote
    assert len(overview.hub_notes) >= 1
    assert all(isinstance(h, HubNote) for h in overview.hub_notes)
    # B.md has in-degree 1 from A.md
    hub_paths = [h.path for h in overview.hub_notes]
    assert "B.md" in hub_paths

    # Top tags must be instances of TagStat
    assert len(overview.top_tags) >= 1
    assert all(isinstance(t, TagStat) for t in overview.top_tags)
    tag_names = [t.tag for t in overview.top_tags]
    assert "orbit" in tag_names
