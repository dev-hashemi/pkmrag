# Subsystem: Benchmarks & Evaluation

Orbit features a deterministic, in-process Information Retrieval (IR) evaluation harness to guard against retrieval regression. Curated ground-truth benchmarks are evaluated directly in CI with zero external API calls or LLM dependencies.

---

## 🎯 Datasets & Golden Benchmarks

Orbit maintains two automated ground-truth benchmarks:

### 1. Synthetic Golden 10 (Fast CI Quality Gate)
- **Dataset:** [`benchmarks/golden_10.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_10.json)
- **Reference Vault:** [`benchmarks/vault/`](file:///home/ali/projects/my/project-orbit/benchmarks/vault/) (12 notes, 17 vertices, 39 links, 36 tags)
- **CLI Command:** `uv run orbit eval`
- **Execution Time:** ~35ms warm cache, ~1.5s cold
- **CI Quality Gates:** `MRR >= 0.80`, `Recall@5 >= 0.80`

| Metric | Target | Score | Status |
| :--- | :---: | :---: | :---: |
| **Mean Reciprocal Rank (MRR)** | $\ge 0.80$ | **0.950** | ✅ Passed |
| **Context Recall@5** | $\ge 0.80$ | **0.950** | ✅ Passed |
| **Hits@1 (Top-1 Accuracy)** | - | **90.0%** | ✅ Passed |
| **Hits@3** | - | **100.0%** | ✅ Passed |
| **Hits@5** | - | **100.0%** | ✅ Passed |
| **Mean Average Precision (MAP@5)** | - | **0.925** | ✅ Passed |
| **Multi-Hop Completeness** | - | **50.0%** | ⚠️ Partial |

### 2. Canonical Obsidian Help 50 (Comprehensive Real-World Evaluation)
- **Dataset:** [`benchmarks/golden_50_obsidian_help.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_50_obsidian_help.json)
- **Reference Vault:** `/home/ali/Vaults/obsidian-help` (176 notes, 345 note vertices, 1,611 wikilinks, 1,100 chunks)
- **Harness:** [`tests/test_benchmark_obsidian_help.py`](file:///home/ali/projects/my/project-orbit/tests/test_benchmark_obsidian_help.py)
- **Test Categories:**
  - 15 Exact keyword / syntax queries (BM25 testing)
  - 20 Semantic / paraphrased queries (FastEmbed dense vector testing)
  - 15 Graph neighborhood queries with `--near` (LadybugDB proximity boost testing)

| Category / Scope | Queries | MRR | Hits@1 | Hits@3 | Hits@5 | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Exact Keyword** | 15 | 0.728 | 60.0% | 86.7% | 93.3% | ✅ Passed |
| **Semantic Concept** | 20 | 0.682 | 55.0% | 85.0% | 85.0% | ✅ Passed |
| **Graph Proximity (`--near`)** | 15 | 0.817 | 73.3% | 86.7% | 86.7% | ✅ Passed |
| **Overall Combined** | **50** | **0.736** | **62.0%** | **86.0%** | **88.0%** | **✅ Passed** |

---

## 🛠️ CLI Usage: `orbit eval`

```bash
# Run default evaluation (benchmarks/golden_10.json on benchmarks/vault)
uv run orbit eval

# Enforce custom quality gates in CI
uv run orbit eval --min-mrr 0.85 --min-recall 0.80

# Machine-readable JSON output for automated reporting
uv run orbit eval --json

# Run against custom vault or benchmark dataset
uv run orbit eval /path/to/vault -b /path/to/benchmark.json
```

### Metrics Explained

- **MRR (Mean Reciprocal Rank):** $\frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$. Measures how quickly the first relevant note appears.
- **Context Recall@K:** Fraction of required ground-truth notes retrieved in the top $K$ results. Crucial for multi-hop retrieval queries.
- **Context Precision@K:** Fraction of retrieved top $K$ notes that are relevant to the query.
- **MAP@K (Mean Average Precision):** Rewards ranking relevant notes higher throughout the top $K$ slots.
- **Multi-Hop Completeness:** Fraction of multi-target queries where *all* expected ground-truth notes were retrieved within top $K$.


