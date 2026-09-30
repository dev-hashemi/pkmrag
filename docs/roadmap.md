# Project Orbit — Engineering Roadmap

This document outlines the phased milestone progression of Project Orbit from core storage validation to advanced agentic knowledge graph synthesis.

---

## 🗺️ Milestone Progression Overview

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9
Storage     Graph       Hybrid      MCP         Semantic    Caching &   Evals       Tracing     Local       Obsidian
Doctor      Backbone    Search      Server      Gaps        Mutations   Harness     OTel        Models      Plugin
v0.0.1      v0.1.0      v0.2.0      v0.3.0      v0.4.0      v0.5.0      v0.6.0      v0.7.0      v0.8.0      v0.9.0
✅ Done     ✅ Done     ✅ Done     ✅ Done     🎯 Current  Planned     Planned     Planned     Planned     Optional
```

---

## 🏁 Completed Phases

### Phase 0: Storage Engine Validation (`v0.0.1`) ✅
- Validated in-process storage pairing: **LadybugDB** (graph) + **LanceDB** (Arrow vectors).
- Built `orbit doctor` health check with Rich terminal diagnostics.

### Phase 1: Deterministic Graph Backbone (`v0.1.0`) ✅
- Implemented pluggable [`KnowledgeDialect`](subsystems/ingestion.md) system (Obsidian, CommonMark).
- AST parsing of wikilinks, tags, and directory trees into LadybugDB property graph.
- SHA-256 incremental sync and ghost note reconciliation for dangling links.

### Phase 2: Hybrid Semantic Retrieval (`v0.2.0`) ✅
- Implemented `HierarchicalMarkdownChunker` preserving heading breadcrumbs.
- Built FastEmbed ONNX local CPU vector embeddings (`BAAI/bge-small-en-v1.5`, 384-dim).
- LanceDB vector ANN search + native Tantivy BM25 keyword search fused via Reciprocal Rank Fusion ($k=60$).
- Graph proximity boosting (`--near <note>`) with hop distance weighting (0, 1, 2 hops).

### Phase 3: Model Context Protocol (MCP) Server (`v0.3.0`) ✅
- Implemented FastMCP server over `stdio` with strict logging isolation to `stderr`.
- Exposed 9 read-only tools: `query_vault`, `read_note` (with composite graph context), `list_notes`, `list_tags`, `search_by_tag`, `get_outline`, `get_note_context`, `find_bridges`, `vault_overview`.
- Added `orbit serve` and `orbit mcp-config` with one-line registration for Claude Code, Cursor, and OpenCode CLI.
- Extended dialect support to `.markdown` and `.mdx` with PKM internal folder ignore rules.

---

## 🎯 Current Milestone

### Phase 4: Semantic Gap Detection (`v0.4.0`)
- **Core Feature:** `orbit discover <path>` CLI command and MCP tool.
- **Algorithm:**
  1. Dense ANN search in LanceDB to find high-similarity pairs ($\text{cosine similarity} \ge 0.80$).
  2. LadybugDB hop check to filter out pairs already connected within $\le 2$ hops.
  3. Send remaining candidate pairs to a structured `InferenceProvider` to classify relationship.
- **Schema Separation:** Write AI relationships to `INFERRED_REL` table in LadybugDB (`rel_type`, `confidence`, `reason`, `model`, `created_at`). Never pollute human ground-truth `LINKS_TO`.
- **Classification Enum:** `EXTENDS`, `CONTRADICTS`, `SUPPORTS`, `PREREQUISITE_FOR`, `REFINES`, plus `NONE` (to eliminate forced-choice hallucinations).
- **Architecture Abstraction:** Define `InferenceProvider` protocol upfront for painless local model drop-in during Phase 8.

---

## 🔮 Upcoming Milestones

### Phase 5: Caching & Mutation Lifecycle (`v0.5.0`)
- **Two-Layer Query Cache:**
  - **L1 (Exact):** SQLite hash lookup for identical query text ($< 1\text{ms}$).
  - **L2 (Semantic):** LanceDB query vector lookup for semantically identical intent ($\ge 0.96$ similarity, $< 5\text{ms}$).
- **Constrained Agent Mutation Tools:** Expose safe write operations via MCP (`append_to_note`, `create_note`) without unrestricted filesystem overwrite capabilities.
- **Mutation Invalidation Lifecycle:** Atomic disk write $\to$ incremental LadybugDB/LanceDB re-index $\to$ cache eviction.

### Phase 6: Automated Evaluation Harness (`v0.6.0`)
- **Core Feature:** `orbit eval` testing retrieval accuracy against curated golden questions.
- **Metrics Tracked:** Context Recall, Context Precision, Mean Reciprocal Rank (MRR).
- **CI Integration:** Automated evaluation regression gate in GitHub Actions blocking regressions on PRs.

### Phase 7: Observability & Tracing (`v0.7.0`)
- **Distributed Tracing:** OpenTelemetry spans wrapping each step of `query_vault` and `orbit discover` (cache lookup, embedding, LanceDB search, LadybugDB traversal, fusion).
- **Token & Cost Auditing:** Track prompt/completion token consumption and latency metrics per query.

### Phase 8: Local Model Inference (`v0.8.0`)
- **Local Fallback:** Implement `OllamaProvider` adhering to Phase 4's `InferenceProvider` protocol.
- **Offline Privacy:** Run relationship classification on-device (`llama3.2`, `qwen2.5`) with constrained JSON decoding and validation retries.

### Phase 9: Obsidian Plugin (`v0.9.0` — Optional)
- **Editor Integration:** Lightweight TypeScript desktop plugin connecting to Orbit via HTTP/SSE.
- **Human-in-the-Loop:** Displays suggested connections and contradiction warnings as diffs for human approval.

---

## 🚫 Explicit Non-Goals (What NOT to Build)

| Temptation | Why Skipped |
| :--- | :--- |
| **Custom Chat UI** | Frontier AI tools (Claude, Cursor, OpenCode) handle UI better via MCP. |
| **Multi-User / Auth** | Local-first architecture; added multi-tenant overhead is wasted complexity. |
| **Background File Watcher** | On-demand incremental sync (`orbit ingest`) is fast and eliminates daemon leaks. |
| **Binary Formats (PDF/DOCX)** | Orbit's superpower is linked PKM knowledge graphs. |
| **Custom Model Fine-Tuning** | Off-the-shelf embedding and instruction models with structural prompts are sufficient. |

---

## 🏷️ Release & Git Strategy

- **Semantic Versioning:** `v0.0.1` $\to$ `v0.1.0` $\to \dots \to$ `v0.9.0`.
- **Conventional Commits:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`.
- **Strict Quality Gating:** `uv run pytest`, `uv run mypy src tests`, and `uv run ruff check .` must pass on every commit.
