# Project Orbit — Engineering Roadmap

This document outlines the phased milestone progression of Project Orbit from core storage validation to advanced agentic knowledge graph synthesis.

---

## 🗺️ Milestone Progression Overview

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9
Storage     Graph       Hybrid      MCP         Semantic    Caching &   Evals       Tracing     Local       Obsidian
Doctor      Backbone    Search      Server      Gaps        Digestion   Harness     OTel        Models      Plugin
v0.0.1      v0.1.0      v0.2.0      v0.3.0      v0.4.0      v0.5.0      v0.6.0      v0.7.0      v0.8.0      v0.9.0
✅ Done     ✅ Done     ✅ Done     ✅ Done     ✅ Done     ✅ Done     ✅ Done     🎯 Current  Planned     Optional
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

### Phase 4: Semantic Gap Detection (`v0.4.0`) ✅
- **Core Feature:** `orbit discover <path>` CLI command and MCP tool.
- Dense ANN search in LanceDB ($\text{similarity} \ge 0.80$) + LadybugDB 2-hop graph distance filter.
- Inferred edges written to `[:INFERRED_REL]` table with confidence, model name, and reasoning.

### Phase 5: Caching & On-Demand Digestion Lifecycle (`v0.5.0`) ✅
- **High-Performance L1 Query Cache (< 0.5ms):** SQLite WAL store, composite parameter hashing, inverted note dependency tracking (`cache_dependencies`), and LRU pruning.
- **Sub-40ms Targeted Reindexer:** Incremental single-note AST + LanceDB vector updating without full vault scans.
- **On-Demand MCP Digestion Tools:** Added `reindex_note` and `sync_vault` to synchronize external edits from Claude Code, Cursor, or Obsidian in real time.
- **LadybugDB Concurrency Guard:** Unified Read-Write `GraphStore` with in-process write mutex preventing transaction errors and stale snapshots.

### Phase 6: Automated Evaluation Harness (`v0.6.0`) ✅
- **In-Process Deterministic IR Evaluation:** `orbit eval` testing retrieval accuracy against curated golden benchmarks with zero LLM API dependency.
- **Metrics Tracked:** Mean Reciprocal Rank (MRR), Context Recall@K, Context Precision@K, MAP@K, Hits@K, and Multi-Hop Completeness.
- **In-Repo Golden Benchmark:** 12-note reference vault with multi-hop wikilinks and golden queries in `benchmarks/`.
- **CI Quality Gating:** Integrated into GitHub Actions workflow blocking regressions on pull requests (`MRR >= 0.80`, `Recall@5 >= 0.80`).

### Phase 7: Observability & Tracing (`v0.7.0`) ✅
- **Distributed Tracing:** OpenTelemetry spans wrapping each step of `query_vault`, `orbit search`, and `orbit discover` (cache lookup, embedding, LanceDB search, LadybugDB traversal, fusion).
- **In-Terminal Visual Breakdown:** `orbit search --trace` renders a color-coded Rich waterfall tree with latency thresholds and attribute badges.
- **Token & Cost Auditing:** Track prompt/completion token consumption per inference call and quantify context tokens saved by graph topology pruning (`tokens_saved_by_graph`).
- **Zero-Daemon Local Inspection:** In-memory span recording with zero background process overhead; optional OTLP HTTP export to Langfuse/Jaeger.

---

### Phase 8: Local Model Inference (`v0.8.0`) ✅
- **Local Fallback:** Implemented `OllamaProvider` adhering to Phase 4's `InferenceProvider` protocol with OpenAI-compatible endpoint auto-normalization.
- **Offline Privacy:** Run relationship classification completely on-device (`llama3.2`, `qwen2.5`) with zero telemetry or network calls.
- **Conversational Validation Feedback:** Multi-turn retry loop catching Pydantic validation failures on edge 3B/7B models and supplying error feedback for autonomous correction.
- **Zero-Throttling Execution:** Local providers bypass token-bucket rate limits (`is_local=True`) to maximize local hardware throughput.
- **Health Verification:** `orbit doctor` probes Ollama connectivity and lists active local models without blocking CI or offline usage.

---

### Phase 9a: HTTP/SSE Server Transport & REST API (`v0.9.0`) ✅
- **Dual Protocol Plane:** `orbit serve --transport http` hosting both Model Context Protocol SSE (`/sse`, `/messages/`) and direct REST endpoints (`/api/v1/*`).
- **Obsidian-Ready REST APIs:** Structured endpoints for note context, semantic gaps, hybrid search, incremental reindexing, and delta synchronization.
- **Zero-Config Token Security:** Automatically persists owner-only token (`0o600`) to `.orbit/server_token` in the vault, defended against DNS rebinding via loopback binding (`127.0.0.1`).
- **Reactive Event Stream:** Server-Sent Events stream (`/api/v1/events`) pushing live reindex/sync updates to connected editor tabs.

---

### Phase 9b: Obsidian Plugin MVP (`v0.9.1`) ✅
- **Editor Integration:** Native TypeScript desktop plugin connecting to Orbit's HTTP/SSE daemon.
- **"Orbit Insights" Sidebar Panel:** Cards for missing links, contradiction warnings with LLM quotes, and structural note context.
- **Human-in-the-Loop:** `[+ Link]` writes wikilinks at active cursor; never mutates notes silently.
- **Zero-Config Token Discovery:** Auto-reads `.orbit/server_token` from active vault filesystem.
- **Auto-Sync on File Save:** Obsidian `vault.on('modify')` hook triggering debounced (1500ms) background reindexing (< 40ms).

---

## 🎯 Current Milestone

### Phase 9c: Obsidian Plugin Polish (`v0.9.2` — Optional)
- **Editor Gutter Icons:** Subtle inline markers next to headings with unlinked semantic connections.
- **Dismissed Suggestion Memory:** Negative feedback cache preventing dismissed links from reappearing.

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
