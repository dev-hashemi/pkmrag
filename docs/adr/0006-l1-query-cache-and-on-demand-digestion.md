# 6. L1 Query Cache and On-Demand Digestion Architecture

- **Status:** Accepted
- **Date:** 2026-10-04
- **Deciders:** Orbit Core Team

---

## Context
Phase 5 originally proposed adding file mutation tools (`append_to_note`, `create_note`) and a two-tier L1 exact + L2 semantic query cache to Orbit.

During architectural analysis, two core tensions emerged:
1. **Scope Tension (File Editing vs. Digestion Engine):** Frontier AI tools (Claude Code, Cursor) and humans (Obsidian) already possess mature, diff-aware, git-integrated file editors. Adding text editing tools to Orbit would introduce redundant, fragile editing primitives prone to corrupting YAML frontmatter and formatting, while failing to catch human edits in Obsidian.
2. **Semantic Cache Risk (Drift vs. Speedup):** Empirical testing on `BAAI/bge-small-en-v1.5` embeddings revealed that paraphrases (`"how does caching work?"` vs `"explain the caching mechanism"`) produced $0.9129$ cosine similarity (missing a $\ge 0.96$ threshold), while opposite queries (`"created yesterday"` vs `"created today"`) produced $0.9571$ (high false-positive risk). Meanwhile, L1 exact SQLite caching yields a **100x speedup (< 0.5ms vs 22.9ms)** with zero semantic drift.

---

## Decision

1. **Option A — Pure Digestion & Fast On-Demand Synchronization:**
   - Orbit does **not** implement file editing or text replacement tools. External clients edit notes natively.
   - Orbit provides on-demand digestion tools (`reindex_note` and `sync_vault`) to synchronize modified files on disk into LadybugDB and LanceDB in **< 40ms**.
2. **L1 SQLite Query Cache as Primary Tier:**
   - Implemented in embedded SQLite with WAL mode (`PRAGMA journal_mode = WAL;`).
   - Uses parameter-aware composite hashing (`compute_key`) to eliminate filter cross-talk across `mode`, `near`, `limit`, `folder`, and `tags`.
   - Maintains an inverted dependency index (`cache_dependencies`) to enable granular invalidation when notes are modified.
   - Includes automatic LRU capacity pruning and graceful degradation on error.
3. **Unified In-Process Read-Write GraphStore:**
   - The MCP server maintains a single shared Read-Write `GraphStore` guarded by an in-process write mutex (`threading.Lock`), resolving LadybugDB's point-in-time snapshot stale-read trap and single-writer transaction constraint.

---

## Consequences

### Positive
- Sub-millisecond (< 0.5ms) response times for repeated queries.
- Zero risk of note corruption from Orbit.
- Sub-40ms targeted re-indexing closes the feedback loop between external edits and GraphRAG retrieval.
- Codebase remains strictly modular, lightweight, and well below the 300-line hard limit.

### Negative
- Pure-chat MCP clients lacking local file access (e.g., standard Claude Desktop without filesystem tools) cannot create new notes via Orbit; they rely on native filesystem MCP servers or external editing.
