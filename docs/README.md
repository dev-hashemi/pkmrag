# Project Orbit Technical Documentation

Welcome to the internal engineering documentation for **Project Orbit**, an embedded, local-first Hybrid GraphRAG retrieval engine and MCP server designed for linked Markdown knowledge bases (such as Obsidian vaults).

---

## 🧭 Documentation Index

This documentation provides an end-to-end technical breakdown of the architecture, storage engines, data pipelines, and ranking algorithms powering Orbit:

1. [**System Architecture & Design Decisions**](architecture.md)
   - 3-tier discovery pipeline
   - In-process, zero-daemon philosophy
   - Markdown dialect extensibility model
2. [**Dual In-Process Storage Engines**](storage_engines.md)
   - LadybugDB: OpenCypher property graph schema & traversal mechanics
   - LanceDB: Apache Arrow columnar vectors & native BM25 FTS index
3. [**Ingestion Pipeline & Chunking Engine**](ingestion_pipeline.md)
   - Incremental change detection (SHA-256 + mtime)
   - AST hierarchical heading chunker with breadcrumb preservation
   - Ghost note reconciliation lifecycle
4. [**Retrieval, RRF Fusion & Graph Proximity Boosting**](retrieval_and_ranking.md)
   - Dense semantic vector search + sparse BM25 retrieval
   - Reciprocal Rank Fusion ($k=60$) mathematics & design rationale
   - OpenCypher topological proximity multipliers ($\times 1.40$, $\times 1.25$, $\times 1.10$)

---

## 🗺️ System Component Map

```
src/orbit/
├── cli.py             # Thin Typer CLI controller (doctor, ingest, search)
├── cli_views.py       # Rich terminal view renderers and panel formatters
├── config.py          # Directory resolution, environment overrides, constants
├── doctor.py          # Diagnostic health checks for LadybugDB & LanceDB
├── models.py          # Strict Pydantic domain models crossing subpackage boundaries
├── dialects/          # Knowledge base parser strategies
│   ├── base.py        # KnowledgeDialect protocol and LinkExtractionResult
│   ├── obsidian.py    # Obsidian dialect ([[wikilinks]], #tags, YAML frontmatter)
│   ├── commonmark.py  # Standard CommonMark dialect ([links](target.md))
│   └── registry.py    # Auto-detection and dialect registry
├── parser/            # Vault indexing and AST markdown inspection
│   ├── indexer.py     # Filesystem discovery, path normalization, link resolution
│   └── markdown.py    # Common AST markdown parsing utilities
├── graph/             # Embedded LadybugDB property graph layer
│   ├── schema.py      # Node/Rel table DDL statements
│   ├── store.py       # GraphStore connection management, upserts, lifecycle
│   └── traversal.py   # OpenCypher hop traversal & proximity queries
├── search/            # Embedded LanceDB hybrid search plane
│   ├── chunker.py     # Hierarchical heading chunker with breadcrumb stacking
│   ├── embedder.py    # FastEmbed ONNX BGE-small embedding provider
│   ├── vector_store.py# LanceDB Arrow table operations, FTS index, dense ANN
│   ├── fusion.py      # Reciprocal Rank Fusion (RRF) & graph proximity boost
│   └── service.py     # SearchService orchestrator
└── ingest/            # Pipeline orchestration
    └── pipeline.py    # Multi-target (all/graph/vector) incremental synchronization
```
