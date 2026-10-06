# Subsystem: Benchmarks & Evaluation

Orbit features a deterministic, in-process Information Retrieval (IR) evaluation harness to guard against retrieval regression. Curated ground-truth benchmarks are evaluated directly in CI with zero external API calls or LLM dependencies.

---

## 🎯 Datasets & Golden Benchmarks

Orbit maintains two automated ground-truth benchmarks:

### 1. Synthetic Golden 10 (Fast CI Quality Gate)
- **Dataset:** [`benchmarks/golden_10.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_10.json)
- **Reference Vault:** [`benchmarks/vault/`](file:///home/ali/projects/my/project-orbit/benchmarks/vault/) (12 notes, 17 vertices, 39 links, 36 tags)
- **CLI Command:** `uv run pkmrag eval`
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

## 🛠️ CLI Usage: `pkmrag eval`

```bash
# Run default evaluation (benchmarks/golden_10.json on benchmarks/vault)
uv run pkmrag eval

# Enforce custom quality gates in CI
uv run pkmrag eval --min-mrr 0.85 --min-recall 0.80

# Machine-readable JSON output for automated reporting
uv run pkmrag eval --json

# Run against custom vault or benchmark dataset
uv run pkmrag eval /path/to/vault -b /path/to/benchmark.json
```

### 📊 Metrics Explained

Orbit's evaluation harness tracks two classes of metrics: **Quality Gates** (strict pass/fail thresholds that block CI) and **Informational Telemetry** (diagnostic metrics for ranking distribution).

| Metric | Type | What It Measures | How It Is Interpreted |
| :--- | :---: | :--- | :--- |
| **Mean Reciprocal Rank (MRR)** | **Quality Gate** | **Position of the first hit.** $\frac{1}{\|Q\|} \sum \frac{1}{\text{rank}_i}$. | A score of `1.0` means the right note was ranked #1 on every query. `0.950` means 9 out of 10 queries had the right note at #1, and 1 at #2. |
| **Context Recall@5** | **Quality Gate** | **Completeness of context.** Fraction of all ground-truth notes retrieved within top 5. | Crucial for multi-hop questions. If an answer requires Note A and Note B, both must appear in top 5 to get full recall. |
| **Hits@1, 3, 5** | Telemetry | **Top-K Hit Rate.** Percentage of queries where at least one correct note appeared in the top $K$. | `Hits@1 = 90%` means 9/10 top results were relevant. `Hits@3 = 100%` means zero questions completely missed the top 3. |
| **Context Precision@5** | Telemetry | **Signal-to-noise ratio.** Fraction of the 5 retrieved notes that are relevant. | Naturally low (~`0.20`–`0.25`) because Orbit retrieves 5 notes (`limit=5`), but most queries only have 1 correct answer note ($\frac{1}{5} = 20\%$). |
| **MAP@5** | Telemetry | **Mean Average Precision.** Evaluates how high relevant notes are ranked throughout the list. | Penalizes placing relevant notes low in the list (e.g., at #4 or #5). Our score of `0.925` shows heavy front-loading. |
| **Multi-Hop Completeness** | Telemetry | **Complete multi-note chains.** Percentage of multi-target queries where *100%* of required notes were retrieved. | Assesses whether interconnected notes were both surfaced to supply complete context to downstream LLM reasoning. |

---

## ❓ Frequently Asked Questions

### Do I need to run `pkmrag ingest` before `pkmrag eval`?
**No.** `EvaluationHarness` is completely self-contained. It inspects the target vault and automatically executes `IngestPipeline` on demand. On the first run, it builds the graph and vector indices; on subsequent runs, it uses the cached indices to run the evaluation in **~20ms**.

### Does `pkmrag eval` evaluate LLM gap detection (`pkmrag discover`)?
**No.** `pkmrag eval` is strictly focused on the **Tier 1 & Tier 2 deterministic retrieval backbone** (LadybugDB graph + LanceDB vectors + BM25 keyword search + RRF fusion). 

Gap detection (Tier 3) requires LLM inference (calling Gemini, Claude, or local Ollama). Leaving LLM generation out of `pkmrag eval` ensures CI runs are:
- **100% Deterministic:** Zero test flakiness or non-reproducible scores.
- **$0 Cost:** Runs without paid API tokens.
- **Offline & Fast:** Completes in milliseconds on headless GitHub Actions runners.


