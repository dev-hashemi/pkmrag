"""Comprehensive unit and integration tests for vault graph ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pkmrag.cli import app
from pkmrag.graph.store import GraphStore
from pkmrag.ingest.pipeline import IngestPipeline
from pkmrag.models import Wikilink
from pkmrag.parser.indexer import VaultIndexer
from pkmrag.parser.markdown import (
    extract_tags,
    extract_wikilinks,
    parse_frontmatter,
    strip_code_blocks,
)

runner = CliRunner()


def test_markdown_frontmatter_extraction() -> None:
    """Verify robust YAML frontmatter extraction."""
    content = """---
title: Test Note
aliases: ["Alias 1", Alias 2]
tags: [tag1, tag2/sub]
---
# Test Note Body
Here is the text.
"""
    fm, body = parse_frontmatter(content)
    assert fm["title"] == "Test Note"
    assert fm["aliases"] == ["Alias 1", "Alias 2"]
    assert fm["tags"] == ["tag1", "tag2/sub"]
    assert "# Test Note Body" in body


def test_markdown_code_block_masking() -> None:
    """Verify that fenced and inline code blocks are masked out."""
    content = """
# Real Header
Real link: [[RealTarget]]
Real tag: #realtag

```python
# code tag: #notatag
def foo():
    # [[CodeLinkIgnored]]
    return True
```

Inline `[[InlineIgnored]]` and inline `#inlinetag_ignored`.
"""
    stripped = strip_code_blocks(content)
    assert "RealTarget" in stripped
    assert "#realtag" in stripped
    assert "CodeLinkIgnored" not in stripped
    assert "#notatag" not in stripped
    assert "InlineIgnored" not in stripped
    assert "#inlinetag_ignored" not in stripped


def test_markdown_wikilink_and_tag_extraction() -> None:
    """Verify extraction of diverse wikilinks, markdown links, and tags."""
    content = """
Here are links:
- [[TargetNote]]
- [[TargetNote#Section Anchor]]
- [[TargetNote|Display Alias]]
- [[TargetNote#Heading|Full Combo]]
- ![[EmbeddedImage.png]]
- [Markdown Link](relative/doc.md#intro)
- [[#Local Section]]

Tags:
#architecture #graph/rag (#nested_paren)
Pure number: #123 (should be ignored)
URL: https://example.com#anchor (ignored)
"""
    body_no_code = strip_code_blocks(content)
    links = extract_wikilinks(body_no_code)

    assert len(links) == 7
    assert links[0].target == "TargetNote"
    assert links[1].anchor == "Section Anchor"
    assert links[2].alias == "Display Alias"
    assert links[3].anchor == "Heading" and links[3].alias == "Full Combo"
    assert links[4].is_embed is True and links[4].target == "EmbeddedImage.png"
    assert links[5].target == "relative/doc.md" and links[5].anchor == "intro"
    assert links[6].target == "" and links[6].anchor == "Local Section"

    tags = extract_tags(body_no_code)
    assert "architecture" in tags
    assert "graph/rag" in tags
    assert "nested_paren" in tags
    assert "123" not in tags
    assert "Local Section" not in tags
    assert "Section Anchor" not in tags


def test_vault_indexer_resolution(tmp_path: Path) -> None:
    """Verify Obsidian path, basename, alias, and ghost resolution."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "work").mkdir()
    (vault / "personal").mkdir()

    (vault / "work" / "api.md").write_text("# Work API")
    (vault / "personal" / "api.md").write_text("# Personal API")
    (vault / "caching.md").write_text("""---
aliases: [FastCache, Cache Layer]
---
# Caching
""")

    indexer = VaultIndexer(vault)
    discovered = indexer.scan_vault_structure()
    indexer.index_vault_files(discovered)

    # Same folder match
    res1, ghost1 = indexer.resolve_link("work/dashboard.md", Wikilink(target="api"))
    assert res1 == "work/api.md"
    assert ghost1 is False

    res2, ghost2 = indexer.resolve_link("personal/notes.md", Wikilink(target="api"))
    assert res2 == "personal/api.md"
    assert ghost2 is False

    # Alias match
    res3, ghost3 = indexer.resolve_link("work/api.md", Wikilink(target="FastCache"))
    assert res3 == "caching.md"
    assert ghost3 is False

    # Case-insensitive stem match
    res4, ghost4 = indexer.resolve_link("work/api.md", Wikilink(target="Caching"))
    assert res4 == "caching.md"
    assert ghost4 is False

    # Unresolved ghost note (scoped to source folder)
    res5, ghost5 = indexer.resolve_link("work/api.md", Wikilink(target="Future Roadmap"))
    assert res5 == "work/Future Roadmap.md"
    assert ghost5 is True

    # Unresolved ghost note from vault root
    res6, ghost6 = indexer.resolve_link("caching.md", Wikilink(target="Root Ghost"))
    assert res6 == "Root Ghost.md"
    assert ghost6 is True


def test_graph_store_crud(tmp_path: Path) -> None:
    """Verify GraphStore node/relationship lifecycle and persistence."""
    db_dir = tmp_path / "test_graph"
    with GraphStore(db_dir) as store:
        store.upsert_note("note1.md", "Note 1", "hash1", 100.0, False)
        store.upsert_folder_hierarchy("projects/orbit")
        store.add_note_contained_in("note1.md", "projects/orbit")
        store.add_tagged_with("note1.md", "#graphrag")
        store.add_links_to("note1.md", "note2.md", anchor="arch", alias="Link 2")

        stats = store.get_stats()
        assert stats["notes"] == 2
        assert stats["unresolved_notes"] == 1
        assert stats["folders"] == 2
        assert stats["tags"] == 1
        assert stats["links"] == 1

    # Reopen database to verify persistence
    with GraphStore(db_dir) as store2:
        stats2 = store2.get_stats()
        assert stats2["notes"] == 2
        assert stats2["links"] == 1


def test_ingest_pipeline_incremental_sync(tmp_path: Path) -> None:
    """Verify incremental change detection: additions, modifications, and deletions."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "notes").mkdir()

    file_a = vault / "notes" / "a.md"
    file_b = vault / "notes" / "b.md"

    file_a.write_text("# Note A\nLinks to [[b]] and [[c]]. #tagA")
    file_b.write_text("# Note B\n#tagB")

    pipeline = IngestPipeline(vault)

    # 1. Initial Ingestion
    s1 = pipeline.run()
    assert s1.notes_scanned == 2
    assert s1.notes_added == 2
    assert s1.notes_updated == 0
    assert s1.notes_unchanged == 0
    assert s1.unresolved_notes == 1  # Note c is ghost
    assert s1.total_notes == 3
    assert s1.total_links == 2

    # 2. Re-ingest unchanged vault
    s2 = pipeline.run()
    assert s2.notes_scanned == 2
    assert s2.notes_added == 0
    assert s2.notes_updated == 0
    assert s2.notes_unchanged == 2
    assert s2.notes_deleted == 0

    # 3. Create Note C on disk (resolving ghost note)
    file_c = vault / "notes" / "c.md"
    file_c.write_text("# Note C\nReal note now!")
    s3 = pipeline.run()
    assert s3.notes_added == 1
    assert s3.unresolved_notes == 0
    assert s3.total_notes == 3

    # 4. Modify Note A (drop link to b, add tagX)
    file_a.write_text("# Note A\nLinks only to [[c]]. #tagX")
    s4 = pipeline.run()
    assert s4.notes_updated == 1
    assert s4.total_links == 1

    # 5. Delete Note C (Note A still links to C, so C should become ghost note)
    file_c.unlink()
    s5 = pipeline.run()
    assert s5.notes_deleted == 1
    assert s5.unresolved_notes == 1
    assert s5.total_notes == 3


def test_cli_ingest_commands(tmp_path: Path) -> None:
    """Verify CLI execution of orbit ingest and orbit ingest --json."""
    vault = tmp_path / "cli_vault"
    vault.mkdir()
    (vault / "readme.md").write_text("# Readme\nWelcome to [[Architecture]]. #docs")

    # Standard run
    res = runner.invoke(app, ["ingest", str(vault)])
    assert res.exit_code == 0
    assert "Graph Ingestion" in res.stdout
    assert "LadybugDB Graph Topology" in res.stdout

    # JSON output
    res_json = runner.invoke(app, ["ingest", str(vault), "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert data["notes_scanned"] == 1
    assert data["unresolved_notes"] == 1
    assert data["total_links"] == 1

    # Rebuild mode
    res_rebuild = runner.invoke(app, ["ingest", str(vault), "--rebuild"])
    assert res_rebuild.exit_code == 0
    assert "Rebuild mode enabled" in res_rebuild.stdout
