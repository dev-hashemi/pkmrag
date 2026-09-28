# Subsystem: Benchmarks & Evaluation

Orbit uses an automated ground-truth benchmark suite to guard against retrieval regression.

---

## 🎯 Datasets & Methodology

Orbit maintains two automated ground-truth benchmarks:

### 1. Synthetic Golden 10 (Fast Smoke Evaluation)
- **Dataset:** [`benchmarks/golden_10.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_10.json)
- **Harness:** [`tests/test_benchmark.py`](file:///home/ali/projects/my/project-orbit/tests/test_benchmark.py)
- **Reference Vault:** `/home/ali/Vaults/orbit-test-vault` (12 notes, 17 vertices, 39 links, 36 tags)

| Metric | Score | Minimum Target | Status |
| :--- | :---: | :---: | :---: |
| **Hits@1** | **90.0%** | $\ge 70\%$ | ✅ Passed |
| **Hits@3** | **100.0%** | $\ge 90\%$ | ✅ Passed |
| **MRR (Mean Reciprocal Rank)** | **0.950** | $\ge 0.80$ | ✅ Passed |

### 2. Canonical Obsidian Help 50 (Real-World Evaluation)
- **Dataset:** [`benchmarks/golden_50_obsidian_help.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_50_obsidian_help.json)
- **Harness:** [`tests/test_benchmark_obsidian_help.py`](file:///home/ali/projects/my/project-orbit/tests/test_benchmark_obsidian_help.py)
- **Reference Vault:** `/home/ali/Vaults/obsidian-help` (176 notes, 345 note vertices, 1,611 wikilinks, 1,100 chunks)
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

## 🧪 Running the Benchmarks

```bash
# Run Golden 10 smoke test
uv run pytest tests/test_benchmark.py

# Run Canonical Obsidian Help 50 evaluation with breakdown
uv run pytest -s tests/test_benchmark_obsidian_help.py
```
Asserts that IR thresholds (`MRR >= 0.70`, `Hits@3 >= 0.75`, `Hits@5 >= 0.80`) are consistently maintained.

