# Subsystem: Benchmarks & Evaluation

Orbit uses an automated ground-truth benchmark suite to guard against retrieval regression.

---

## 🎯 Dataset & Methodology
- **Benchmark Dataset:** [`benchmarks/golden_10.json`](file:///home/ali/projects/my/project-orbit/benchmarks/golden_10.json)
- **Test Harness:** [`tests/test_benchmark.py`](file:///home/ali/projects/my/project-orbit/tests/test_benchmark.py)
- **Reference Vault:** `/home/ali/Vaults/orbit-test-vault` (12 notes, 17 vertices, 39 links, 36 tags)

---

## 📊 Evaluation Metrics

Retrieval accuracy is measured using standard Information Retrieval metrics across the 10 Golden Queries:

$$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$

| Metric | Score | Minimum Target | Status |
| :--- | :---: | :---: | :---: |
| **Hits@1** | **90.0%** | $\ge 70\%$ | ✅ Passed |
| **Hits@3** | **100.0%** | $\ge 90\%$ | ✅ Passed |
| **MRR (Mean Reciprocal Rank)** | **0.950** | $\ge 0.80$ | ✅ Passed |

---

## 🧪 Running the Benchmark
```bash
uv run pytest tests/test_benchmark.py
```
Asserts that regression thresholds (`MRR >= 0.80`, `Hits@3 >= 0.90`) are maintained on every build.
