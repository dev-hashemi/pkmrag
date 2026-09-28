# System Architecture & Design Decisions

This document details the architectural foundation, core design decisions, and system boundaries of Project Orbit.

---

## 🏛️ The Problem: Why Traditional GraphRAG Fails on Personal Vaults

Traditional GraphRAG solutions (e.g., Microsoft GraphRAG) extract knowledge graphs from uncurated text by prompting Large Language Models to discover entity-relation-entity triples:
$$\text{Document Chunk} \xrightarrow{\text{LLM Prompt}} (\text{Subject}, \text{Predicate}, \text{Object})$$

While suitable for unstructured corporate dumps, applying this to personal research vaults (like Obsidian) introduces severe failure modes:
1. **Excessive Cost & Latency:** Vaults containing thousands of notes require millions of input tokens, costing \$50–\$200+ per full indexing run and taking hours.
2. **Ontological Hallucination:** LLMs invent arbitrary, synonymous relation types (`[:RELATES_TO]`, `[:ASSOCIATED_WITH]`, `[:CONNECTS_TO]`) causing graph noise.
3. **Ignoring Human Effort:** Note-takers have already spent hundreds of hours explicitly connecting notes via wikilinks (`[[Note B]]`), folder hierarchies, and tags.

---

## 🛰️ Orbit's 3-Tier Discovery Model

Orbit replaces unconstrained triple extraction with a **deterministic-first, targeted discovery pipeline**:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'background': 'transparent', 'mainBkg': '#1e293b', 'primaryColor': '#1e293b', 'primaryBorderColor': '#3b82f6', 'primaryTextColor': '#f8fafc', 'lineColor': '#38bdf8', 'edgeLabelBackground': '#1e293b' }}}%%
flowchart TD
    Vault["📂 Markdown Knowledge Base"]

    subgraph T1["Tier 1: Deterministic Graph Backbone ($0 Cost)"]
        Parser["AST Markdown Parser\n(Dialect System)"]
        Ladybug[("LadybugDB Embedded Graph\n• (:Note)-[:LINKS_TO]->(:Note)\n• (:Note)-[:TAGGED_WITH]->(:Tag)\n• (:Note)-[:NOTE_CONTAINED_IN]->(:Folder)")]
        Parser --> Ladybug
    end

    subgraph T2["Tier 2: Hybrid Semantic Indexing"]
        Chunker["Hierarchical Heading Chunker\n(Breadcrumb Preserving)"]
        Embedder["FastEmbed ONNX CPU\n(BAAI/bge-small-en-v1.5)"]
        Lance[("LanceDB Vector & FTS\n• Dense 384-dim Vectors\n• Sparse BM25 Inverted Index")]
        Chunker --> Embedder --> Lance
        Chunker --> Lance
    end

    subgraph T3["Tier 3: Targeted Semantic Gap Detector (Phase 3)"]
        Filter["Topology Gap Filter\n(High Vector Sim + Graph Hop ≥ 3)"]
        LLM["Targeted LLM Tripler\n(Classify Missing Bridge Edges)"]
        Inferred[("Inferred Relationship Table\n`[:INFERRED_REL {confidence, model}]`")]
        Ladybug -.-> Filter
        Lance -.-> Filter
        Filter --> LLM --> Inferred
    end

    Vault --> Parser
    Vault --> Chunker

    style T1 fill:#0f172a,stroke:#3b82f6,color:#e2e8f0
    style T2 fill:#0f172a,stroke:#8b5cf6,color:#e2e8f0
    style T3 fill:#7c2d12,stroke:#f97316,color:#e2e8f0
    linkStyle default stroke:#38bdf8,stroke-width:2px;
```

1. **Tier 1 (Deterministic Structural Backbone):** Parses explicit wikilinks, tags, and directory trees into LadybugDB with zero LLM API calls.
2. **Tier 2 (Hybrid Semantic Search):** Splits notes along Markdown headings into context-preserved chunks, indexes them into LanceDB with dense embeddings and native BM25 full-text search, and fuses results using Reciprocal Rank Fusion (RRF).
3. **Tier 3 (Targeted Semantic Gap Detector):** Identifies pairs of notes that have high semantic similarity (e.g., cosine similarity $> 0.82$) but no topological connection in the graph ($\text{hops} \ge 3$). Only these pairs are passed to an LLM to discover missing conceptual links.

---

## 📐 Architecture Decision Records (ADRs)

### ADR 1: Embedded In-Process Storage vs. Client-Server Databases
- **Decision:** Use **LadybugDB** (embedded C++ OpenCypher property graph) and **LanceDB** (embedded Apache Arrow columnar vector engine).
- **Rationale:**
  - Zero deployment friction: No Docker, no background daemon services, no TCP connection overhead.
  - Sub-millisecond latency: Queries execute in-process within shared memory space.
  - Portable storage: Graph and vector indices live locally in `<vault>/.orbit/` alongside note files.

### ADR 2: Dialect Strategy Pattern for Markdown Formats
- **Decision:** Decouple format-specific parsing into pluggable dialect strategies via [`KnowledgeDialect`](../src/orbit/dialects/base.py).
- **Rationale:**
  - Obsidian uses double bracket syntax (`[[Note Title|Alias]]`, `![[Image.png]]`), block references (`^block`), and hashtag metadata.
  - Other tools (CommonMark, Logseq, Foam, Roam Research) use standard Markdown links (`[text](url)`), page properties, or outline bullets.
  - The core indexing pipeline remains format-agnostic. New vault types only require a single new dialect class registered with `DialectRegistry`.

### ADR 3: Pure Model Context Protocol (MCP) Interface
- **Decision:** Expose Orbit capabilities strictly as an MCP server (stdio and SSE) rather than building a custom chat frontend or GUI.
- **Rationale:**
  - Frontier AI reasoning environments (Cursor, Claude Code, Windsurf, Claude Desktop) already provide superior chat interfaces and code editing workflows.
  - Orbit functions as a retrieval substrate for these agents, exposing deterministic tools (`query_vault`, `read_note`, `find_bridges`).

### ADR 4: Segregation of Ground Truth and Inferred Knowledge
- **Decision:** Inferred AI relationships are stored in separate edge tables with metadata (`confidence: float`, `model: str`, `timestamp: float`).
- **Rationale:**
  - Human-curated notes are authoritative ground truth.
  - Graph traversals default to explicit edges unless proximity expansion explicitly permits inferred links.
  - Allows easy retraction or recalculation of AI links when switching embedding or LLM models without altering human data.
