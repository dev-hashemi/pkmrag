"""Unit tests for HierarchicalMarkdownChunker."""

from __future__ import annotations

from orbit.search.chunker import HierarchicalMarkdownChunker


def test_chunker_basic_hierarchy() -> None:
    """Verify heading breadcrumbs and section splitting."""
    content = """---
tags: [test]
---
# System Architecture

The high-level architecture of Orbit.

## Storage Layer

Orbit uses embedded databases for local-first storage.

### LadybugDB

Graph engine for deterministic traversal.

### LanceDB

Vector engine for semantic search.
"""
    chunker = HierarchicalMarkdownChunker(min_tokens=5, max_tokens=100)
    chunks = chunker.chunk_document("system.md", "System Architecture", content)

    assert len(chunks) >= 3
    # Check breadcrumb formatting
    headings = [c.heading for c in chunks]
    assert any("# System Architecture > ## Storage Layer > ### LadybugDB" in h for h in headings)
    assert any("# System Architecture > ## Storage Layer > ### LanceDB" in h for h in headings)


def test_chunker_micro_section_merging() -> None:
    """Verify micro-sections below min_tokens threshold get merged."""
    content = """# Overview

Intro text.

## Tiny A

One word.

## Tiny B

Another small bit.

## Normal Section

This is a much longer section that has plenty of tokens to stand on its own
without needing to be merged with any adjacent sections whatsoever.
"""

    chunker = HierarchicalMarkdownChunker(min_tokens=20, max_tokens=100)
    chunks = chunker.chunk_document("micro.md", "Micro Test", content)

    # Tiny sections should have been merged together
    assert len(chunks) < 4


def test_chunker_large_section_splitting() -> None:
    """Verify large sections exceeding max_tokens are split on paragraph boundaries."""
    para1 = "Paragraph one with repeated text. " * 30
    para2 = "Paragraph two with different text. " * 30
    content = f"# Deep Note\n\n## Big Section\n\n{para1}\n\n{para2}"

    chunker = HierarchicalMarkdownChunker(min_tokens=10, max_tokens=50)
    chunks = chunker.chunk_document("deep.md", "Deep Note", content)

    assert len(chunks) >= 2
    for c in chunks:
        assert "# Deep Note > ## Big Section" in c.heading
        assert c.chunk_id.startswith("deep.md#chunk_")


def test_chunker_empty_and_no_heading() -> None:
    """Verify empty document and text without explicit headings."""
    chunker = HierarchicalMarkdownChunker()
    assert chunker.chunk_document("empty.md", "Empty", "") == []
    assert chunker.chunk_document("whitespace.md", "Empty", "   \n\n  ") == []

    # Note without headings
    raw_text = "Just some standalone thoughts without any markdown headers."
    chunks = chunker.chunk_document("thoughts.md", "Thoughts", raw_text)
    assert len(chunks) == 1
    assert chunks[0].heading == "# Thoughts"
    assert "standalone thoughts" in chunks[0].text
