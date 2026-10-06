<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/pkmrag-logo-text-dark.svg">
    <img alt="PKMRAG" src="../assets/pkmrag-logo-text.svg" width="400">
  </picture>
</p>

# System Architecture

PKMRAG is an embedded, local-first Hybrid GraphRAG retrieval engine and MCP server designed for linked Markdown knowledge bases.

---

## 🏛️ 3-Tier Discovery Pipeline

PKMRAG eliminates costly brute-force LLM triple extraction by structuring discovery into three distinct tiers:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'background': 'transparent', 'mainBkg': '#1e293b', 'primaryColor': '#1e293b', 'primaryBorderColor': '#3b82f6', 'primaryTextColor': '#f8fafc', 'lineColor': '#38bdf8', 'edgeLabelBackground': '#1e293b' }}}%%
flowchart TD
    Vault["📂 Markdown Knowledge Base"]

    subgraph T1["Tier 1: Deterministic Graph Backbone ($0 Cost)"]
        Parser["AST Markdown Parser\n(Dialect System)"]
        Ladybug[("LadybugDB Graph\n• (:Note)-[:LINKS_TO]->(:Note)\n• (:Note)-[:TAGGED_WITH]->(:Tag)\n• (:Note)-[:NOTE_CONTAINED_IN]->(:Folder)")]
        Parser --> Ladybug
    end

    subgraph T2["Tier 2: Hybrid Semantic Retrieval"]
        Chunker["Hierarchical Heading Chunker\n(Breadcrumb Preserving)"]
        Embedder["FastEmbed ONNX CPU\n(BAAI/bge-small-en-v1.5)"]
        Lance[("LanceDB Vector & FTS\n• Dense 384-dim Vectors\n• Sparse BM25 Inverted Index")]
        Chunker --> Embedder --> Lance
        Chunker --> Lance
    end

    subgraph T3["Tier 3: Targeted Semantic Gap Detector"]
        Filter["Topology Gap Filter\n(High Vector Sim + Graph Hop ≥ 3)"]
        LLM["Targeted LLM Tripler\n(Classify Missing Bridge Edges)"]
        Inferred[("Inferred Relationship Table\n`[:INFERRED_REL]`")]
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

1. **Tier 1 (Deterministic Graph Backbone):** Extracts explicit wikilinks, tags, and directory hierarchies into LadybugDB with zero LLM API calls.
2. **Tier 2 (Hybrid Semantic Search):** Splits notes along headings, indexes dense embeddings and native BM25 in LanceDB, and fuses them via Reciprocal Rank Fusion (RRF) with graph proximity boosting.
3. **Tier 3 (Semantic Gap Detector):** Targets unlinked note pairs exhibiting high semantic similarity but graph distance $\ge 3$, applying targeted LLM inference to uncover missing relationships.

---

## 🗺️ Subsystems Directory

- [**Graph Engine**](subsystems/graph-engine.md): LadybugDB OpenCypher schema and undirected hop traversal.
- [**Search Engine**](subsystems/search-engine.md): LanceDB Arrow dataset, FastEmbed ONNX inference, and native BM25 full-text search.
- [**Ingestion Pipeline**](subsystems/ingestion.md): Markdown dialect strategies, SHA-256/mtime incremental sync, and ghost note reconciliation.
- [**Hybrid Search & Ranking**](subsystems/hybrid-search.md): Hierarchical heading chunker, Reciprocal Rank Fusion ($k=60$), and graph proximity multipliers.
- [**MCP Server**](subsystems/mcp.md): Model Context Protocol stdio server, tool definitions, and client configuration.
- [**Caching & On-Demand Digestion**](subsystems/caching.md): SQLite L1 query cache with composite hashing, dependency invalidation, and sub-40ms single-note reindexing.
- [**Observability & Tracing**](subsystems/observability.md): OpenTelemetry span hierarchy, visual terminal waterfall trees, and token auditing.
- [**Local Model Inference**](subsystems/local-inference.md): Offline relationship classification with Ollama, conversational validation retry, and token-bucket bypass.
- [**HTTP & SSE Server Transport**](subsystems/http-transport.md): Dual-protocol Starlette server hosting MCP SSE, REST APIs, Bearer auth, and live event broadcasting.
- [**Obsidian Desktop Plugin**](subsystems/obsidian-plugin.md): Native companion plugin surfacing AI gaps, contradiction warnings, and debounced save synchronization.
- [**Benchmarks**](subsystems/benchmarks.md): Golden 10 and Obsidian Help 50 ground truth datasets and evaluation metrics.
- [**Architecture Decision Records (ADRs)**](adr/): Historical design decisions and rationale.

