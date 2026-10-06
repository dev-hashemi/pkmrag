# 2. Pluggable Dialect Strategy for Markdown Formats

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** Orbit Core Team

---

## Context
While Project Orbit is primarily designed for Obsidian vaults, different tools format note-to-note links and metadata differently:
- Obsidian: `[[Note|Alias]]`, `![[embed]]`, `#tag`.
- CommonMark: `[text](target.md)`.
- Other tools (Logseq, Roam, Foam): Outliner bullets, page properties, or block references.

Hardcoding Obsidian parsing rules directly into the core indexer couples storage logic to formatting quirks.

---

## Decision
Implement a **Dialect Strategy Pattern** governed by the `KnowledgeDialect` protocol:
- Format-specific parsing logic lives in `src/pkmrag/dialects/<format>.py`.
- The core indexer and ingestion pipeline operate strictly on normalized `RawLink`, `NoteMetadata`, and `Wikilink` entities.
- A `DialectRegistry` inspects vault structure to auto-detect the appropriate dialect or accepts an explicit `--dialect` CLI argument.

---

## Consequences

### Positive
- App-agnostic core pipeline.
- New knowledge base formats (Logseq, Dendron, etc.) can be introduced simply by creating a new dialect file without touching database or indexing logic.

### Negative
- Minor abstraction overhead (protocol enforcement and dynamic dispatch via registry).
