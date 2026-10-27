# Broad Document Relatedness from Chunk Embeddings — Problem Brief

> **Note for the reviewer:** You do not have access to this codebase. Everything relevant is described below. Please critique the current approach and propose the best method for computing broad document relatedness under the stated constraints. Concrete formulas, algorithms, failure modes, and evaluation suggestions are welcome.

## TL;DR

We have Markdown notes split into heading-based chunks, each embedded with **BAAI/bge-small-en-v1.5** (384-d, cosine). Note pairs can have very different chunk counts (1 vs 40+). We need a symmetric **broad-relatedness** score for a "Missing Links" sidebar.

The current heuristic averages per-chunk best matches and multiplies by a `min` coverage factor. It is length-sensitive, uses arbitrary constants, ignores the full chunk×chunk matrix, and is not calibrated.

We are considering an exact two-stage approach: ANN for candidate notes, then a full chunk×chunk matrix for each candidate pair, aggregated with token-weighted bidirectional max matching and harmonic mean (F1), with similarities calibrated against a vault-relative background distribution.

Please critique this proposal and suggest the best method, including formulas, calibration strategy, chunk weighting, failure modes, and an evaluation protocol.

---

## 1. Product context

We build a local-first personal knowledge base for Markdown notes. Notes are connected with explicit wiki-links. A sidebar feature called **Missing Links** suggests notes that are semantically related but not explicitly linked.

The sidebar should show two distinct signals:

1. **Broad relatedness** — do the two notes cover similar material overall? This is a symmetric property of the pair.
2. **Strongest shared section** — is there one distinctive passage in note A that closely matches a passage in note B? This is a more directional, containment-like signal and explains *why* a specific link is worth considering.

This brief is about **signal 1: broad relatedness**. Signal 2 is used as evidence in the card and may have a different score.

When a note is opened, the app scans the focus note against the vault, filters out notes that are already linked, and returns a small ranked list (typically 5 suggestions). Latency matters because this happens during normal note browsing.

### Current sidebar card

Each card shows:

- the counterpart note title
- a percentage badge intended to represent similarity
- graph distance (how many wiki-link hops away the note is)
- an optional bridge path of intermediate notes
- an expandable **"Why are these similar?"** panel with matching passages from both notes
- **+ Link** and **Dismiss** actions

The percentage badge is the part that currently feels unreliable. Users interpret it as a probability or a cosine, but it is neither.

---

## 2. Data we have

### 2.1 Chunking

Notes are chunked by Markdown heading hierarchy:

- YAML frontmatter is removed.
- Each chunk gets its heading breadcrumb prepended to the text. For example, a paragraph under a third-level heading is embedded as:

  ```text
  # Note Title > ## Section > ### Subsection

  The body text of the section...
  ```

- Sections under roughly 40 words are merged with an adjacent section.
- Sections over roughly 500 words are split at paragraph boundaries.
- Split chunks currently have **no overlap**.
- A note can have 1 chunk or 40+ chunks. Chunk lengths vary from tens to hundreds of words.

One detail that matters: the 500 limit is a **word count**, not a model token count. The embedding model has a 512-token context limit, so a 500-word chunk can be truncated before embedding. The vector may not represent the tail of a long chunk.

### 2.2 Embeddings

- Model: **BAAI/bge-small-en-v1.5**
- Dimensions: **384**
- Similarity: **cosine similarity**
- Stored per chunk: stable ID, note path, note title, heading, text, 384-dimensional vector, chunk index.
- An ANN index supports top-k cosine search by chunk vector.
- No document-level embedding is stored. Only chunk embeddings exist.

### 2.3 Graph

An explicit wiki-link graph is available. It is used only to **filter out** note pairs that are already connected within a small number of hops. It is not part of the semantic score.

### 2.4 Scale

Vaults can be large: thousands of notes and tens of thousands of chunks. Exact all-pairs comparison is not feasible vault-wide. Exact comparison of a small number of candidate note pairs is feasible.

---

## 3. Current scoring method

For a focus note **A**:

1. For each chunk of A, run an ANN search over all chunks in the vault. Take the top 20 by cosine similarity.
2. Discard matches from the same note.
3. Discard matches below a fixed cosine floor of **0.65**.
4. For every candidate note **B**, keep:
   - the best observed cosine for each chunk of A that matched B
   - the best observed cosine for each chunk of B that matched A

5. Compute:

```text
M_A = chunks of A with at least one observed match
M_B = chunks of B with at least one observed match

avg = (Σ_{a∈M_A} best(a, B) + Σ_{b∈M_B} best(b, A))
      / (|M_A| + |M_B|)

coverage = min(|M_A| / total_chunks_A,
               |M_B| / total_chunks_B)

score = avg * (0.3 + 0.7 * coverage)
```

A strong pair can contribute to both sums, so `avg` is not a standard precision or recall. It is also weighted toward the note with more matched chunks.

6. The top 5 chunk pairs are kept as evidence. The best single chunk cosine is reported separately.
7. The score is displayed as a percentage, for example **"43% similar"**. Internally it has sometimes been called "cosine similarity", but it is not a cosine and not a probability.

Crucial detail: **the full chunk×chunk matrix is never computed.** Only the top-20 ANN neighbors per chunk are observed. In focus mode, only the focus note's chunks initiate queries.

---

## 4. Observed problems

### 4.1 Length and chunk-count sensitivity

Suppose note A has 40 chunks and note B has 30. Ten chunk pairs have cosine similarity `0.90`; all other pairs are below the `0.65` floor.

```text
|M_A| = 10
|M_B| = 10
avg = 0.90
coverage = min(10/40, 10/30) = 0.25
score = 0.90 * (0.3 + 0.7 * 0.25)
      = 0.90 * 0.475
      = 0.4275
```

The card says **43% similar**, even though every matched section is 90% similar.

If A and B were one-chunk notes with the same 0.90 match:

```text
coverage = 1
score = 0.90
```

The same section-level match is displayed as **43% or 90% depending only on note length**. That is the central problem.

### 4.2 Broad weak overlap can beat a specific strong link

Suppose both notes have 10 chunks.

- Ten generic chunk pairs at `0.70` produce coverage `1.0` and score `0.70`.
- One near-identical section at `0.95` produces coverage `0.1` and score `0.95 * 0.37 = 0.35`.

For a missing-links feature, the second pair is often the more actionable one.

### 4.3 Arbitrary constants

The match floor (`0.65`), coverage floor (`0.3`), and coverage weight (`0.7`) were hand-tuned. They are not calibrated to the embedding model or to a particular vault.

### 4.4 Raw cosine is not comparable across vaults

In a small, topically homogeneous benchmark vault, the median cross-note chunk cosine was approximately **0.67**. The fixed `0.65` floor was therefore near the median of all cross-note chunk pairs, not a "strong match" cutoff. In a more diverse vault, `0.65` could be very strong. A fixed cosine threshold is not portable.

### 4.5 ANN recall and asymmetry

A top-20 ANN query may miss the true best match. Same-note chunks are filtered *after* the query, so a chunk whose nearest neighbors are mostly its own note's chunks can yield very few cross-note observations. Focus-mode scores can differ from a vault-wide scan because the sets of observed matches differ.

### 4.6 Uniform chunk weights and repeated context

All chunks count equally regardless of length. Adding a heading or splitting a section into more chunks can change the score. Repeated or duplicated content can inflate coverage. Because the heading breadcrumb is repeated in every chunk, notes with similar heading structures (for example, daily notes) can also look more similar than their body content warrants.

### 4.7 Misleading presentation and unstable thresholds

The score is shown as a percentage and has been called cosine similarity. It is neither a cosine nor a probability. A user cannot tell whether a low percentage means "weak match" or "strong match, but most of the note is unrelated".

The same score is also used with different thresholds in different parts of the app: a low threshold for sidebar suggestions, a much higher threshold for LLM-based discovery. That only works because the score has no stable scale. It also means a poorly calibrated threshold can send weak candidates to the LLM, wasting tokens.

---

## 5. What we want from a broad-relatedness score

- **Symmetric:** `score(A, B) = score(B, A)`.
- **Length-normalized:** a 40-chunk vs 30-chunk pair should not be penalized merely for having more chunks; a 500-word section should not count the same as a 40-word section.
- **Content-aware:** a strong match on a distinctive section should matter more than a weak match on generic text.
- **Calibrated:** comparable across pairs in a vault, and ideally across vaults; not dependent on a raw cosine cutoff.
- **Cheap enough:** candidate generation can use ANN; exact scoring should be limited to a small number of candidate pairs per sidebar request.
- **Explainable:** we need coverage-like diagnostics and matched passages for the UI.
- **No new model in the default path:** use the existing chunk embeddings. Methods that require a cross-encoder, an LLM, or a new embedding model are acceptable as optional reranking stages, but not as the default.

---

## 6. Approaches considered

| Approach | Idea | Main issue |
|---|---|---|
| Mean of all chunk-pair cosines | Average the full `m × n` matrix | Dominated by non-matches; almost every pair looks moderately similar |
| Top-k pair mean | Sort all pairs, average the top `k` | `k` is arbitrary; long docs have more chances; duplicates inflate |
| Current heuristic | Average matched-chunk strength × coverage | Length-sensitive, arbitrary constants, uncalibrated |
| Bidirectional max + F1 | Best match per chunk in each direction, harmonic mean | Simple, symmetric, length-normalized; strong baseline |
| Optimal transport / Sinkhorn | Transport matching mass optimally | More principled, more complex, needs tuning |
| Hungarian one-to-one matching | Choose one-to-one best pairs | Sensitive to chunk boundaries; saturates |
| Pooled document embedding | Weighted mean of chunk vectors, one cosine | Cheap but coarse; dilutes multi-topic notes |
| Cross-encoder / LLM | Direct pair judgment | Most accurate, but too slow/costly for every sidebar request |
| Topic clustering | Cluster chunks, compare topic distributions | Complex; sensitive to clustering parameters |

---

## 7. One proposed approach (for critique)

We are considering a two-stage method.

### Stage 1 — candidate generation

Use the existing ANN index per chunk to find candidate notes:

- increase the top-k beyond 20
- exclude same-note chunks during or immediately after the query
- deduplicate candidates by note
- keep the best raw similarity per note pair

This stage only needs high recall. It does not produce the final score.

### Stage 2 — exact scoring

For each candidate pair, load all chunks of both notes and compute the full cross-similarity matrix:

```text
S[i, j] = cosine(vector_a[i], vector_b[j])
```

Then aggregate:

```text
Calibrate each similarity to a vault-relative match strength:
    g(i, j) = percentile of S[i, j] among random cross-note chunk pairs
              (optionally computed per source chunk; if per-chunk, use a
               symmetric combination of the two chunks' percentiles)

Weight each chunk by its body token count:
    w_i > 0

Coverage of A by B:
    cover_A = Σ_i w_i * max_j g(i, j) / Σ_i w_i

Coverage of B by A:
    cover_B = Σ_j w_j * max_i g(i, j) / Σ_j w_j

Broad relatedness:
    relatedness = 2 * cover_A * cover_B / (cover_A + cover_B)
```

Interpretation:

- `cover_A` answers: "What fraction of A's content has a plausible counterpart in B?"
- `cover_B` answers the reverse.
- `relatedness` is the harmonic mean of the two coverage values (F1). It is symmetric, balances the two directions, and avoids choosing an arbitrary top-k.
- Calibration maps raw cosine to a percentile, so a fixed threshold is not tied to one embedding model or one vault's similarity distribution.
- Exact scoring for a 40×30 pair is only `1,200` dot products of 384 dimensions. This is cheap once the candidate pair is known.

### Signal 2 — strongest shared section

Separately from the broad score, select the strongest **distinct** section pairs for the evidence panel:

- sort chunk pairs by calibrated match strength
- greedily pick pairs so that neither the source chunk nor the target chunk is reused
- keep the top 3–5 pairs
- show raw cosine, calibrated percentile, heading, and a short excerpt

A directional containment diagnostic can also be computed for the smaller note:

```text
section_containment = cover_smaller_note
```

This is useful for "this short note is fully covered by one section of the longer note" cases, but it is displayed as evidence rather than used as the broad-relatedness ranking.

### Why we like this proposal

- It is a standard set-similarity aggregation (BERTScore / Chamfer / MaxSim family).
- It handles unequal chunk counts naturally.
- It avoids the arbitrary top-k and the arbitrary coverage multiplier.
- It is explainable: coverage in each direction plus matched passages.
- It cleanly separates broad relatedness from single-section link evidence.

### Open questions

1. Is bidirectional max + harmonic mean the best simple choice for broad relatedness, or is there a better length-normalized set similarity?
2. Is percentile calibration the right approach? Global vs per-chunk? How should the background sample be drawn in a topically homogeneous vault, and how large should it be?
3. What chunk weighting is best: token count, `sqrt(token count)`, IDF/commonness, or something else?
4. Is optimal transport / Sinkhorn worth the complexity for documents with 1–40 chunks? Which variant (balanced, unbalanced, entropic) would you use?
5. How should we handle generic/boilerplate chunks, repeated content, and daily-note templates?
6. How should we evaluate the score without a large labeled dataset? Is leave-one-link-out a valid proxy? What metrics and perturbations would you use?
7. How should we set thresholds or tiers that generalize across vaults?
8. Should we add a document-level embedding (title + headings, weighted mean, SIF, summary) as a prior or tie-breaker? If so, how should it be combined with chunk-level coverage?
9. What are the main failure modes of chunk-level document similarity that we have not listed?
10. If you were designing this from scratch, what would you do differently?

---

## 8. Constraints and non-goals

- Local, offline, embedded storage; no server-side vector database.
- Python implementation.
- The default sidebar path must not call an LLM or a cross-encoder.
- We can afford exact scoring for the top ~20–50 candidate notes per focus note, but not for all vault pairs.
- We are not asking to redesign the chunker or replace the embedding model in this brief. Brief comments on whether the chunking/truncation issues invalidate the approach are welcome.
- We are not asking for UI implementation details. The output of this work is the scoring method and its diagnostics.

---

## 9. Current score vs proposed score

| Property | Current | Proposed |
|---|---|---|
| Full matrix | No, top-20 ANN only | Yes, for candidate pairs |
| Symmetry | Formula symmetric, observations can differ | Symmetric |
| Chunk count | `min` coverage penalty | Token-weighted bidirectional coverage |
| Chunk length | Uniform | Token-weighted |
| Calibration | Fixed 0.65 floor | Vault-relative percentile |
| Weak broad vs strong specific | Broad weak can win | Calibrated; specific evidence is separate |
| Interpretability | Opaque percentage | Coverage components + matched sections |
| Cost | ANN only | ANN + small exact matrices |

---

## 10. Notation

| Symbol | Meaning |
|---|---|
| `A`, `B` | Two notes |
| `a_i` | Chunk `i` of note A |
| `b_j` | Chunk `j` of note B |
| `m`, `n` | Number of chunks in A and B |
| `S[i,j]` | Cosine similarity between chunk `a_i` and chunk `b_j` |
| `g(i,j)` | Calibrated match strength in `[0,1]` |
| `w_i` | Weight of chunk `i`, normally body token count |
| `cover_A` | Weighted fraction of A covered by B |
| `cover_B` | Weighted fraction of B covered by A |
| `relatedness` | Harmonic mean of `cover_A` and `cover_B` |

---

## 11. Worked example

A has 40 chunks, B has 30. Ten chunk pairs have cosine `0.90`; all other pairs are below the current match floor.

Current score:

```text
avg = 0.90
coverage = min(10/40, 10/30) = 0.25
score = 0.90 * (0.3 + 0.7*0.25) = 0.4275
```

Proposed score with perfect calibration (non-matches ≈ 0) and uniform weights:

```text
cover_A ≈ 10 * 0.90 / 40 = 0.225
cover_B ≈ 10 * 0.90 / 30 = 0.300
relatedness = 2 * 0.225 * 0.300 / (0.225 + 0.300)
            ≈ 0.257
```

The proposed score is lower in this example because it counts the unmatched chunks as zero instead of excluding them and then applying a separate coverage multiplier. The intended behavior is:

- broad relatedness is low when most of both notes are unrelated;
- the single-section signal still highlights the 90% shared sections in the evidence panel.

With token weights, calibration, and a different distribution of content, the value changes, but the interpretation stays the same.

---

## 12. What would help us most

Please respond with:

1. Your recommended scoring formula, with precise definitions and edge cases.
2. Why it is better than bidirectional max + F1 for this use case, or why it confirms that approach.
3. How to calibrate similarities and set thresholds across vaults.
4. How to weight chunks and handle generic or repetitive content.
5. An evaluation protocol that works with little or no labeled data.
6. Any references or known methods we should look at.
7. If you recommend optimal transport or a reranker, explain the cost/benefit and the simplest viable variant.
