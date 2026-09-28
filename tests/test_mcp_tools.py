"""Unit tests for Project Orbit MCP tools and security boundaries."""

from __future__ import annotations

from pathlib import Path

from orbit.graph.store import GraphStore
from orbit.mcp.tools import (
    execute_find_bridges,
    execute_get_note_context,
    execute_query_vault,
    execute_read_note,
    execute_vault_overview,
)


def test_execute_read_note_valid(tmp_path: Path) -> None:
    """Verify read_note successfully reads file content."""
    note = tmp_path / "Guide.md"
    note.write_text("# Guide\nThis is a test note content.", encoding="utf-8")

    result = execute_read_note(tmp_path, "Guide.md")
    assert "# Note: Guide.md" in result
    assert "This is a test note content." in result


def test_execute_read_note_auto_append_md(tmp_path: Path) -> None:
    """Verify read_note automatically finds file if .md suffix was omitted."""
    note = tmp_path / "Architecture.md"
    note.write_text("System architecture details.", encoding="utf-8")

    result = execute_read_note(tmp_path, "Architecture")
    assert "System architecture details." in result


def test_execute_read_note_path_traversal_blocked(tmp_path: Path) -> None:
    """Verify directory traversal attacks are blocked by vault containment boundary."""
    vault = tmp_path / "my_vault"
    vault.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("SUPER_SECRET_TOKEN", encoding="utf-8")

    result = execute_read_note(vault, "../secret.txt")
    assert "Access denied" in result
    assert "SUPER_SECRET_TOKEN" not in result

    root_escape = execute_read_note(vault, "/etc/passwd")
    assert "outside vault boundaries" in root_escape or "Access denied" in root_escape


def test_execute_read_note_pagination(tmp_path: Path) -> None:
    """Verify read_note supports pagination with max_chars and offset."""
    note = tmp_path / "Long.md"
    long_text = "ABCDEFGHIJ" * 20  # 200 chars
    note.write_text(long_text, encoding="utf-8")

    res_part1 = execute_read_note(tmp_path, "Long.md", max_chars=100, offset=0)
    assert "[Truncated: showing chars 0..100 of 200" in res_part1
    assert "ABCDEFGHIJ" in res_part1

    res_part2 = execute_read_note(tmp_path, "Long.md", max_chars=100, offset=100)
    assert "Truncated" not in res_part2


def test_execute_read_note_nonexistent(tmp_path: Path) -> None:
    """Verify clean error message when reading a non-existent note."""
    result = execute_read_note(tmp_path, "Ghost.md")
    assert "does not exist on disk" in result


def test_execute_query_vault_empty() -> None:
    """Verify empty search query validation."""

    # We can pass a dummy search service since empty query returns early
    class DummySearchService:
        pass

    res = execute_query_vault(DummySearchService(), "   ")  # type: ignore[arg-type]
    assert "cannot be empty" in res


def test_execute_tools_with_graph(tmp_path: Path) -> None:
    """Verify get_note_context, find_bridges, and vault_overview with LadybugDB."""
    db_dir = tmp_path / "graph"
    db_dir.mkdir()
    store = GraphStore(db_dir)

    # Insert test graph topology: A -> B -> C
    create_note = (
        "CREATE (n:Note {path: $p, title: $t, hash: $h, mtime: 1.0, is_unresolved: false});"
    )
    store.conn.execute(create_note, {"p": "A.md", "t": "Note A", "h": "h1"})
    store.conn.execute(create_note, {"p": "B.md", "t": "Note B", "h": "h2"})
    store.conn.execute(create_note, {"p": "C.md", "t": "Note C", "h": "h3"})
    store.conn.execute("CREATE (t:Tag {name: 'important'});")
    store.conn.execute(
        "MATCH (a:Note {path: 'A.md'}), (b:Note {path: 'B.md'}) CREATE (a)-[:LINKS_TO]->(b);"
    )
    store.conn.execute(
        "MATCH (b:Note {path: 'B.md'}), (c:Note {path: 'C.md'}) CREATE (b)-[:LINKS_TO]->(c);"
    )
    store.conn.execute(
        "MATCH (b:Note {path: 'B.md'}), (t:Tag {name: 'important'}) CREATE (b)-[:TAGGED_WITH]->(t);"
    )

    # 1. Test get_note_context on B.md
    ctx_b = execute_get_note_context(store, "B.md")
    assert "# Graph Context: Note B" in ctx_b
    assert "`#important`" in ctx_b
    assert "Outgoing Links (1)" in ctx_b
    assert "`C.md`" in ctx_b
    assert "Backlinks / Cited By (1)" in ctx_b
    assert "`A.md`" in ctx_b

    # 2. Test find_bridges between A and C
    bridge = execute_find_bridges(store, "A.md", "C.md", max_hops=4)
    assert "# Shortest Bridge: A.md ↔ C.md" in bridge
    assert "Distance**: 2 hops" in bridge
    assert "`A.md` ➔ `B.md` ➔ `C.md`" in bridge

    # 3. Test find_bridges self-path
    self_bridge = execute_find_bridges(store, "A.md", "A.md")
    assert "exact same note" in self_bridge

    # 4. Test vault_overview
    overview = execute_vault_overview(store)
    assert "# Vault Knowledge Graph Overview" in overview
    assert "Total Notes**: 3" in overview
    assert "Total Wikilinks**: 2" in overview
    assert "`B.md`" in overview  # Hub note with in-degree 1
    assert "`#important`" in overview

    store.close()
