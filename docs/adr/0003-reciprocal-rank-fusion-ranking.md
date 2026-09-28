# 3. Reciprocal Rank Fusion (RRF) for Hybrid Search

- **Status:** Accepted
- **Date:** 2026-09-28
- **Deciders:** Orbit Core Team

---

## Context
Combining dense vector search and sparse BM25 keyword search is essential for high-precision retrieval.
A common baseline combines raw scores linearly:
$$Score(d) = \alpha \cdot Score_{\text{dense}}(d) + (1 - \alpha) \cdot Score_{\text{sparse}}(d)$$

However:
- BM25 produces unbounded scores $[0, \infty)$ sensitive to document lengths and corpus frequencies.
- Vector distance metrics (L2 Euclidean distance) require non-linear conversion into bounded similarities.
- Linear weight $\alpha$ is highly sensitive to query types (keyword IDs vs. semantic concepts).

---

## Decision
Orbit adopts **Reciprocal Rank Fusion (RRF)** with standard smoothing constant $k = 60$:
$$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{60 + \text{rank}_m(d)}$$

---

## Consequences

### Positive
- **Scale Invariant:** Depends purely on rank position, completely bypassing score normalization artifacts.
- **Corroboration Boost:** Chunks appearing in top ranks of both modalities naturally receive a compound boost over single-modality candidates.
- Zero extra hyperparameters to tune per user vault.

### Negative
- Drops granular distance margins between adjacent items in a single ranked stream.
