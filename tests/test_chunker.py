"""Unit tests for HierarchicalMarkdownChunker."""

from __future__ import annotations

from pkmrag.search.chunker import HierarchicalMarkdownChunker


def test_chunker_basic_hierarchy() -> None:
    """Verify heading breadcrumbs and section splitting."""
    content = """---
tags: [test]
---
# System Architecture

The high-level architecture of PKMRAG.

## Storage Layer

PKMRAG uses embedded databases for local-first storage.

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


def test_chunker_default_tokens_and_overlap() -> None:
    """Verify default max_tokens=320 and paragraph overlap carryover."""
    chunker = HierarchicalMarkdownChunker()
    assert chunker.max_tokens == 320
    assert chunker.overlap_tokens == 30

    short_overlap_para = "Short summary paragraph. " * 4  # ~16 tokens <= 30
    long_para_1 = "Main body content of section one. " * 35  # ~175 tokens
    long_para_2 = "Main body content of section two. " * 35  # ~175 tokens

    content = f"# Title\n\n## Section\n\n{long_para_1}\n\n{short_overlap_para}\n\n{long_para_2}"
    chunks = chunker.chunk_document("test.md", "Title", content)

    # 175 + 16 + 175 = 366 words > 320 words, so it should split
    assert len(chunks) >= 2
    # The short paragraph should be in chunk 0 and carried over into chunk 1 as overlap
    assert "Short summary paragraph." in chunks[0].text
    assert "Short summary paragraph." in chunks[1].text
