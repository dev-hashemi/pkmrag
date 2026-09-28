# Retrieval, RRF Fusion & Graph Proximity Boosting

This document details the search and ranking algorithms implemented in Project Orbit ([`src/orbit/search/`](file:///home/ali/projects/my/project-orbit/src/orbit/search/)), including dense vector retrieval, lexical BM25, Reciprocal Rank Fusion, and LadybugDB topological proximity boosting.

---

## 🔍 The Need for Hybrid Retrieval

Production retrieval systems face two complementary search challenges:

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     Dense Semantic Retrieval    │       │     Sparse Lexical Retrieval    │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ • Understands latent intent     │       │ • Exact token & keyword matches │
│ • Robust to paraphrasing        │       │ • Matches rare entities & IDs   │
│ • Handles cross-lingual concept │       │ • Preserves symbols & versions  │
│                                 │       │                                 │
│ ❌ Fails on exact code symbols  │       │ ❌ Fails on synonyms & concept  │
│ ❌ Fuzzy on version numbers     │       │ ❌ Vocabulary mismatch problem  │
└─────────────────────────────────┘       └─────────────────────────────────┘
```

Orbit unites both modalities into a single in-process pipeline:
- **Dense Vector Search:** FastEmbed (`BAAI/bge-small-en-v1.5`, 384 dimensions) + LanceDB ANN index.
- **Sparse BM25 Search:** LanceDB native Tantivy-backed inverted full-text search index.

---

## 🔀 Reciprocal Rank Fusion (RRF)

### Why Not Linear Score Weighting?
A naive approach combines normalized scores linearly:
$$Score_{\text{linear}}(d) = \alpha \cdot Score_{\text{dense}}(d) + (1 - \alpha) \cdot Score_{\text{sparse}}(d)$$

In practice, linear score combination is brittle:
1. **Unbounded BM25 Range:** BM25 scores range from $0$ to $+\infty$, varying heavily depending on term frequency and document length.
2. **Distance vs. Similarity:** L2 Euclidean distance requires non-linear transforms ($1 / (1 + \text{dist})$) that distort score distributions.
3. **Hyperparameter Fragility:** A static $\alpha$ optimal for conceptual queries will degrade performance for identifier queries.

### The RRF Formulation
Orbit uses **Reciprocal Rank Fusion (RRF)** ([Cormack et al., 2009](https://dl.acm.org/doi/10.1145/1571941.1572014)), a rank-based fusion algorithm:

$$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + \text{rank}_m(d)}$$

Where:
- $m$: Retrieval modality (dense vector or sparse BM25).
- $\text{rank}_m(d) \in \{1, 2, 3, \dots\}$: 1-indexed rank position of document $d$ in system $m$.
- $k$: Smoothing constant, set to **$60$** (the standard empirical optimum in IR literature).

### Mathematical Behavior of RRF ($k=60$)
- If a document is ranked **#1 in both** dense and sparse:
  $$\text{RRF}(d) = \frac{1}{60 + 1} + \frac{1}{60 + 1} = \frac{2}{61} \approx 0.03278$$
- If a document is ranked **#1 in dense only** (absent from top sparse):
  $$\text{RRF}(d) = \frac{1}{60 + 1} = \frac{1}{61} \approx 0.01639$$
- If a document is ranked **#2 in dense and #3 in sparse**:
  $$\text{RRF}(d) = \frac{1}{62} + \frac{1}{63} \approx 0.01613 + 0.01587 = 0.03200$$

Documents corroborated by **both** modalities naturally leapfrog documents that score high in only one.

---

## ⚡ Graph Proximity Boosting

Standard vector retrieval ignores the structural topology of the user's knowledge graph. When exploring notes around a specific topic, concepts physically linked to that note are significantly more relevant.

Orbit introduces **Topological Proximity Boosting** ([`fusion.py`](file:///home/ali/projects/my/project-orbit/src/orbit/search/fusion.py)):

### 1. Neighborhood Traversal
When the `--near <note>` option is supplied, Orbit resolves the target note path and queries LadybugDB for all undirected neighbors within 2 hops:
$$\text{dist}(u, v) = \text{shortest undirected path distance in } G$$

### 2. Multiplier Schedule
Each candidate chunk $d$ belongs to a parent note $N(d)$. The fused RRF score is boosted based on $N(d)$'s graph distance to the focus note:

$$\text{Score}_{\text{final}}(d) = \text{RRF}(d) \times \text{Multiplier}\Big(\text{dist}\big(N(d), \text{Focus}\big)\Big)$$

| Hop Distance | Multiplier | Rationale |
| :---: | :---: | :--- |
| **0 hops** | **$\times 1.40$** | Content within the focus note itself receives top priority |
| **1 hop** | **$\times 1.25$** | Directly linked notes (forward links or inbound backlinks) |
| **2 hops** | **$\times 1.10$** | Secondary associative neighbors (friends of friends) |
| **$> 2$ hops / unlinked** | **$\times 1.00$** | Distant or unlinked notes receive baseline RRF score |

### 3. Re-Ranking
Results are re-sorted descending by $\text{Score}_{\text{final}}(d)$. The boost can elevate a strongly connected note that scored slightly lower in lexical BM25 over an unlinked distant note.

---

## 📊 Benchmark Evaluation Metrics

Orbit evaluates retrieval performance using the Golden 10 ground truth benchmark ([`benchmarks/golden_10.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_10.json)) against `/home/ali/Vaults/orbit-test-vault`:

### Evaluation Results
- **MRR (Mean Reciprocal Rank):** **`0.950`**
  $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i} = \frac{9 \times 1.0 + 1 \times 0.5}{10} = 0.950$$
- **Hits@1:** **`90.0%`** (9 out of 10 queries returned the exact ground-truth note at rank 1)
- **Hits@3:** **`100.0%`** (10 out of 10 queries returned the ground-truth note within the top 3 results)
