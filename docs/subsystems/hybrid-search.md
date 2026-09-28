# Subsystem: Hybrid Search & Ranking

The hybrid search subsystem fuses dense semantic embeddings, sparse BM25 keyword recall, and topological graph proximity into a unified ranking pipeline.

---

## 💾 Implementation
- **Chunker:** [`src/orbit/search/chunker.py`](file:///home/ali/projects/my/project-orbit/src/orbit/search/chunker.py)
- **Fusion & Boost:** [`src/orbit/search/fusion.py`](file:///home/ali/projects/my/project-orbit/src/orbit/search/fusion.py)
- **Service:** [`src/orbit/search/service.py`](file:///home/ali/projects/my/project-orbit/src/orbit/search/service.py)

---

## 🧩 Hierarchical Heading Chunker

Instead of fixed token windows, Orbit chunks along Markdown headings (`#`–`######`):
1. **Breadcrumbs:** Tracks heading lineage (e.g. `# Arch > ## Storage > ### LanceDB`) and prepends it to chunk text for contextualized indexing.
2. **Micro-Section Merging:** Sections below 40 tokens merge into adjacent sections to prevent low-context fragments.
3. **Macro-Section Splitting:** Sections exceeding 500 tokens split on paragraph boundaries (`\n\n`), keeping breadcrumb context on each subchunk.

---

## 🔀 Reciprocal Rank Fusion (RRF)

Orbit blends dense vector ranks with sparse BM25 ranks using standard RRF ($k=60$):

$$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{60 + \text{rank}_m(d)}$$

- **Why RRF:** Rank-based combination is scale-invariant. It eliminates brittle linear score weighting ($\alpha \cdot \text{dense} + (1-\alpha) \cdot \text{sparse}$) between unbounded BM25 scores and bounded Euclidean distances.
- Documents matching both semantic intent and exact keywords naturally outrank single-stream matches.

---

## ⚡ Topological Graph Proximity Boosting

When `--near <note>` is specified, Orbit identifies the focus note's graph neighborhood in LadybugDB and applies distance multipliers:

$$\text{Score}_{\text{final}}(d) = \text{RRF}(d) \times \text{Multiplier}(\text{hop})$$

| Hop Distance | Multiplier | Meaning |
| :---: | :---: | :--- |
| **0 hops** | **$\times 1.40$** | Focus note itself |
| **1 hop** | **$\times 1.25$** | Direct neighbors (forward links or backlinks) |
| **2 hops** | **$\times 1.10$** | Secondary associative neighbors |
| **$> 2$ hops** | **$\times 1.00$** | Distant or unlinked notes |

CLI Example:
```bash
orbit search "vector retrieval" --vault /path/to/vault --near "Storage Layer"
```
