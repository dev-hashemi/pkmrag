# 7. Document Relatedness & Multi-Chunk Semantic Gap Detection

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** PKMRAG Core Team

---

## Context

In PKMRAG, notes are chunked by heading hierarchy into 1 to 40+ chunks and embedded using `bge-small-en-v1.5`.
When discovering missing links (semantic gaps), the system must compare notes across the vault to recommend unlinked connections.

The previous heuristic had several key UX and mathematical flaws:
1. **Severe Length Penalty:** Comparing a 40-chunk note and a 30-chunk note sharing 10 identical sections scored ~43% similarity due to a min-coverage ratio, while two 1-chunk notes with a single match scored 90%.
2. **Top-5 Truncation:** Only the top 5 chunks were matched and displayed, discarding valid evidence for comprehensive notes.
3. **Misleading Raw Percentages:** Showing raw cosine similarity percentages (e.g., "78% similar") confused users because it blurred the line between whole-document overlap, asymmetric containment, and a single shared topic.

---

## Decision

PKMRAG adopts a **calibrated bidirectional coverage engine** (`src/pkmrag/discovery/relatedness.py`) paired with **semantic intent classification** and **progressive disclosure**:

1. **Dead-Zone Noise Suppression ($\tau = 0.65$):** Cosine similarities below $0.65$ are clamped to $0.0$, eliminating false-positive noise accumulation across long notes.
2. **Sublinear Word Weighting:** Each chunk is weighted by $w = \sqrt{\text{clip}(\text{words}, 15, 400)}$ to prevent verbose wandering sections from dominating concise atomic notes while remaining resilient to paragraph splits.
3. **Greedy Reuse Decay ($\gamma = 0.5$):** When multiple chunks in note $A$ match the same chunk in note $B$, subsequent matches are geometrically discounted to prevent duplicate copy-pasted text from inflating coverage.
4. **Relationship Classification:** Pairs are categorized into semantic relationship types:
   - `DEEP_OVERLAP`: Mutual coverage across multiple sections.
   - `CONTAINMENT`: Atomic or focused note covered within a larger literature/hub note.
   - `SHARED_CONCEPT`: Distinct notes sharing a strong passage match.
   - `WEAK_OVERLAP`: Below significant threshold.
5. **Uncapped Evidence Extraction:** All qualified non-overlapping chunk pairs meeting the similarity floor are preserved.
6. **Progressive Disclosure UI:** The Obsidian companion plugin displays high-confidence items by default (top 5 notes, top 2 matching sections) with expandable toggles (`Show more related notes` / `Show more matching sections`) and replaces raw percentages with intent badges.

---

## Consequences

### Positive
- **Fair Multi-Topic Comparison:** Notes sharing multiple sections are properly surfaced as `DEEP_OVERLAP` without severe size penalties.
- **Accurate Asymmetric Containment:** Atomic concept notes discussed inside larger hub notes are classified as `Topic Included` ("Covers X% of note").
- **Auditability:** Users can expand and view all matching chunk pairs justifying the connection.
- **Zero Heavy Dependencies:** Evaluated in $< 1\text{ ms}$ per note pair using vectorized NumPy matrix operations.

### Negative
- Evaluating all non-overlapping chunk pairs for very large hub notes ($>50$ chunks) requires calculating full $m \times n$ cosine matrices, though mitigated by ANN pre-filtering.
