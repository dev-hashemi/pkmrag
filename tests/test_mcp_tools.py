"""Unit tests for Project Orbit MCP tools and security boundaries."""

from __future__ import annotations

from pathlib import Path

from pkmrag.graph.store import GraphStore
from pkmrag.mcp.tools import (
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
    """Verify read_note automatically finds file if suffix was omitted (.md, .markdown, .mdx)."""
    note = tmp_path / "Architecture.md"
    note.write_text("System architecture details.", encoding="utf-8")

    result = execute_read_note(tmp_path, "Architecture")
    assert "System architecture details." in result

    # Also verify .markdown and .mdx
    note2 = tmp_path / "Draft.markdown"
    note2.write_text("Draft content.", encoding="utf-8")
    assert "Draft content." in execute_read_note(tmp_path, "Draft")

    note3 = tmp_path / "Component.mdx"
    note3.write_text("Component content.", encoding="utf-8")
    assert "Component content." in execute_read_note(tmp_path, "Component")


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


def test_execute_read_note_with_graph_context(tmp_path: Path) -> None:
    """Verify read_note enriches output with tags and links when graph store is provided."""
    note = tmp_path / "NoteA.md"
    note.write_text("Note A content.", encoding="utf-8")

    db_dir = tmp_path / "graph"
    db_dir.mkdir()
    store = GraphStore(db_dir)

    create_note = (
        "CREATE (n:Note {path: $p, title: $t, hash: $h, mtime: 1.0, is_unresolved: false});"
    )
    store.conn.execute(create_note, {"p": "NoteA.md", "t": "Note A", "h": "h1"})
    store.conn.execute(create_note, {"p": "NoteB.md", "t": "Note B", "h": "h2"})
    store.conn.execute("CREATE (t:Tag {name: 'guide'});")
    store.conn.execute(
        "MATCH (a:Note {path: 'NoteA.md'}), (b:Note {path: 'NoteB.md'}) "
        "CREATE (a)-[:LINKS_TO]->(b);"
    )
    store.conn.execute(
        "MATCH (a:Note {path: 'NoteA.md'}), (t:Tag {name: 'guide'}) CREATE (a)-[:TAGGED_WITH]->(t);"
    )

    res = execute_read_note(tmp_path, "NoteA.md", graph_store=store)
    assert "**Context**:" in res
    assert "`#guide`" in res
    assert "Outgoing (1): `NoteB.md`" in res
    store.close()


def test_execute_list_notes(tmp_path: Path) -> None:
    """Verify list_notes browsing, folder filtering, and pattern matching."""
    from pkmrag.mcp.tools_vault import execute_list_notes

    (tmp_path / "Root.md").write_text("Root note", encoding="utf-8")
    (tmp_path / "Post.markdown").write_text("Markdown post", encoding="utf-8")
    sub = tmp_path / "Guides"
    sub.mkdir()
    (sub / "Setup.md").write_text("Setup guide", encoding="utf-8")
    (sub / "Config.md").write_text("Config guide", encoding="utf-8")
    hidden = tmp_path / ".obsidian"
    hidden.mkdir()
    (hidden / "workspace.md").write_text("Should be ignored", encoding="utf-8")
    logseq_dir = tmp_path / "logseq"
    logseq_dir.mkdir()
    (logseq_dir / "metadata.md").write_text("Logseq internal note", encoding="utf-8")

    # List all
    all_res = execute_list_notes(tmp_path)
    assert "Root.md" in all_res
    assert "Post.markdown" in all_res
    assert "Guides/Setup.md" in all_res
    assert ".obsidian" not in all_res
    assert "logseq" not in all_res

    # List with folder filter
    folder_res = execute_list_notes(tmp_path, folder="Guides")
    assert "Guides/Setup.md" in folder_res
    assert "Root.md" not in folder_res

    # List with pattern
    pattern_res = execute_list_notes(tmp_path, pattern="*config*")
    assert "Guides/Config.md" in pattern_res
    assert "Setup.md" not in pattern_res

    # List nonexistent folder
    error_res = execute_list_notes(tmp_path, folder="NoSuchFolder")
    assert "does not exist" in error_res


def test_execute_tags_tools(tmp_path: Path) -> None:
    """Verify list_tags and search_by_tag MCP tools."""
    from pkmrag.mcp.tools_vault import execute_list_tags, execute_search_by_tag

    db_dir = tmp_path / "graph"
    db_dir.mkdir()
    store = GraphStore(db_dir)

    create_note = (
        "CREATE (n:Note {path: $p, title: $t, hash: $h, mtime: 1.0, is_unresolved: false});"
    )
    store.conn.execute(create_note, {"p": "Note1.md", "t": "First Note", "h": "h1"})
    store.conn.execute(create_note, {"p": "Note2.md", "t": "Second Note", "h": "h2"})
    store.conn.execute("CREATE (t:Tag {name: 'orbit'});")
    store.conn.execute(
        "MATCH (a:Note {path: 'Note1.md'}), (t:Tag {name: 'orbit'}) CREATE (a)-[:TAGGED_WITH]->(t);"
    )
    store.conn.execute(
        "MATCH (a:Note {path: 'Note2.md'}), (t:Tag {name: 'orbit'}) CREATE (a)-[:TAGGED_WITH]->(t);"
    )

    tags_res = execute_list_tags(store)
    assert "`#orbit`" in tags_res
    assert "| 2 |" in tags_res

    search_res = execute_search_by_tag(store, "orbit")
    assert "Note1.md" in search_res
    assert "Note2.md" in search_res

    not_found = execute_search_by_tag(store, "nonexistent")
    assert "No notes found with tag `#nonexistent`" in not_found
    store.close()


def test_execute_get_outline(tmp_path: Path) -> None:
    """Verify get_outline extracts headings and line numbers."""
    from pkmrag.mcp.tools_vault import execute_get_outline

    doc = (
        "# Main Title\n\nIntro text.\n\n"
        "## Sub Heading\n\nBody paragraph.\n\n"
        "### Deep Section\n\nMore details."
    )
    note = tmp_path / "Document.md"
    note.write_text(doc, encoding="utf-8")

    outline = execute_get_outline(tmp_path, "Document.md")
    assert "# Outline: Document.md" in outline
    assert "- Main Title (line 1)" in outline
    assert "  - Sub Heading (line 5)" in outline
    assert "    - Deep Section (line 9)" in outline
