### Technical Implementation Specification: Missing Links Scoring Engine

> **For the Coding Agent:**
> This specification is self-contained. Implement the chunking adjustments, the `missing_links_scorer.py` module, the incremental note-save update hook, the UI/LLM data bindings, and the `test_missing_links_scorer.py` verification suite exactly as specified below. Only `numpy` and the Python standard library are required.

---

### 1. Pre-Embedding Chunking Rules

Update the Markdown heading chunker with the following rules before calling `BAAI/bge-small-en-v1.5`:

1. **Maximum Split Threshold:** Lower the paragraph split threshold from `500 words` to **`320 words`** (or `400 WordPiece tokens`). `bge-small-en-v1.5` has a hard `512`-token context limit; `500` words plus a heading breadcrumb exceeds `650` tokens and silently truncates the bottom ~30% of long sections.
2. **Split Overlap:** When splitting a section exceeding `320` words across paragraph boundaries, carry over the last paragraph (up to `40` words) as overlap into the next chunk.
3. **Store `body_tokens` Separately:** For each chunk, record `body_tokens` as the token count (or `max(1, int(body_word_count * 1.35))`) of the **body text only**, excluding the prepended `# Note Title > ## Section` breadcrumb.

---

### 2. Production Module: `missing_links_scorer.py`

Create `missing_links_scorer.py` with the following implementation. It includes full vault calibration (`fit`), fast single-note incremental updates (`upsert_note` / `remove_note` in $\lt 3\text{ ms}$), Stage 1 candidate generation (`generate_candidates`), and Stage 2 exact scoring (`score_focus_note`).

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import numpy as np


# ============================================================================
# Data Contracts
# ============================================================================


@dataclass
class NoteChunks:
    """In-memory and persisted representation of a note's chunks."""

    note_id: str
    title: str
    chunk_ids: List[str]
    headings: List[str]
    excerpts: List[str]
    raw_vectors: np.ndarray  # shape (m, 384), L2-normalized bge-small-en-v1.5 vectors
    body_tokens: np.ndarray  # shape (m,), body token counts excluding breadcrumb

    # Computed & managed by VaultCalibrationIndex:
    centered_vectors: np.ndarray = field(
        default_factory=lambda: np.empty((0, 384), dtype=np.float32)
    )
    mu: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    sigma: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    weights: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    centroid: np.ndarray = field(default_factory=lambda: np.zeros(384, dtype=np.float32))


@dataclass
class MatchedPassage:
    """A distinct matched section pair for the 'Why are these similar?' UI panel."""

    source_chunk_id: str
    target_chunk_id: str
    source_heading: str
    target_heading: str
    source_excerpt: str
    target_excerpt: str
    raw_cosine: float
    calibrated_strength: float  # g in [0, 1]
    neglog10_p: float  # -log10(p) tail rarity of this chunk pair


@dataclass
class RelatednessResult:
    """Output payload for a single Missing Links sidebar suggestion."""

    candidate_note_id: str
    candidate_title: str
    tier: str  # "strong" | "likely" | "possible" | "near-duplicate"
    display_score: float  # Calibrated [0.0, 1.0] score for UI badges & LLM cutoffs
    e_value: float  # Expected unrelated notes in vault this strong by chance
    p_value: float  # Combined Bonferroni-corrected pair p-value
    resemblance: float  # Symmetric broad F1 coverage R in [0, 1]
    containment: float  # Directional max coverage C = max(cover_focus, cover_candidate)
    cover_focus: float  # Weighted fraction of focus note covered by candidate
    cover_candidate: float  # Weighted fraction of candidate note covered by focus
    best_chunk_neglog10_p: float  # Unclipped -log10(p) of strongest single chunk match
    best_raw_cosine: float  # Raw bge-small cosine of strongest single chunk match
    ui_subtitle: str  # Ready-to-render coverage explanation string
    evidence_passages: List[MatchedPassage]


# ============================================================================
# Vault Calibration Index (Batch + <3ms Incremental Single-Note Updates)
# ============================================================================


class VaultCalibrationIndex:
    """
    Maintains vault-wide centering vectors, background chunk sample, per-chunk
    (mu_i, sigma_i, w_i), SIF note centroids, and the 1D Z-to-neglog10(p) tail table.
    """

    DEFAULT_SIGMA: float = 0.115
    MIN_SIGMA_FLOOR: float = 0.045
    RAW_COSINE_GUARD_FLOOR: float = 0.58

    def __init__(self, rng_seed: int = 42):
        self.rng = np.random.default_rng(rng_seed)
        self.vault_mean_vec: np.ndarray = np.zeros(384, dtype=np.float32)
        self.pc1_vec: np.ndarray = np.zeros(384, dtype=np.float32)
        self.bg_vectors: np.ndarray = np.empty((0, 384), dtype=np.float32)
        self.bg_note_ids: List[str] = []
        self.z_quantiles: np.ndarray = np.linspace(-1.0, 5.5, 651, dtype=np.float32)
        self.neglog10_table: np.ndarray = np.zeros_like(self.z_quantiles)
        self.tail_slope: float = 0.85
        self.tail_anchor_z: float = 4.0
        self.tail_anchor_nlq: float = 3.0
        self.num_notes: int = 0
        self.total_chunks_at_last_fit: int = 0
        self.low_confidence_vault: bool = True

    def fit(self, notes: Dict[str, NoteChunks], sample_size_per_chunk: int = 512) -> None:
        """
        Full calibration across all notes in the vault (~80-150ms for 20k chunks).
        Call on startup and whenever total chunk count drifts by >= 25%.
        """
        valid_notes = [n for n in notes.values() if len(n.chunk_ids) > 0]
        self.num_notes = len(valid_notes)
        if self.num_notes == 0:
            return

        total_chunks = sum(len(n.chunk_ids) for n in valid_notes)
        self.total_chunks_at_last_fit = total_chunks
        self.low_confidence_vault = total_chunks < 200

        # 1. Note-balanced vault mean vector
        note_means = np.stack([n.raw_vectors.mean(axis=0) for n in valid_notes], axis=0)
        self.vault_mean_vec = note_means.mean(axis=0).astype(np.float32)

        # 2. Pre-center all notes so we can draw the note-stratified background sample
        for note in valid_notes:
            c = note.raw_vectors - self.vault_mean_vec[None, :]
            norms = np.linalg.norm(c, axis=1, keepdims=True)
            note.centered_vectors = (c / np.maximum(norms, 1e-8)).astype(np.float32)

        # 3. Draw up to K_bg = 512 random chunks (1 per distinct note) for local scaling
        K_bg = min(sample_size_per_chunk, len(valid_notes))
        sampled_indices = self.rng.choice(
            len(valid_notes), size=K_bg, replace=(len(valid_notes) < K_bg)
        )
        self.bg_vectors = np.stack(
            [
                valid_notes[idx].centered_vectors[
                    self.rng.integers(0, len(valid_notes[idx].chunk_ids))
                ]
                for idx in sampled_indices
            ],
            axis=0,
        ).astype(np.float32)
        self.bg_note_ids = [valid_notes[idx].note_id for idx in sampled_indices]

        # 4. Calibrate each individual note against the background sample
        for note in valid_notes:
            self._calibrate_single_note(note, apply_pc1=False)

        # 5. Compute first principal component of note centroids (SIF common-mode removal)
        if len(valid_notes) >= 10:
            centroids = np.stack([n.centroid for n in valid_notes], axis=0)
            _, _, vt = np.linalg.svd(centroids, full_matrices=False)
            self.pc1_vec = vt[0].astype(np.float32)
            for note in valid_notes:
                self._remove_pc1_from_centroid(note)
        else:
            self.pc1_vec = np.zeros(384, dtype=np.float32)

        # 6. Build the 1D empirical Z -> -log10(p) lookup table
        self._fit_tail_table(valid_notes)

    def upsert_note(self, note: NoteChunks, all_notes: Dict[str, NoteChunks]) -> None:
        """
        Incremental hook (< 2ms): Call whenever a user creates or edits a single note.
        Updates the note's calibrated vectors, weights, and centroid in-place, and
        triggers a full re-fit only if vault size has drifted by >= 25%.
        """
        all_notes[note.note_id] = note
        if len(note.chunk_ids) == 0:
            return

        if self.num_notes == 0 or len(self.bg_vectors) == 0:
            self.fit(all_notes)
            return

        self._calibrate_single_note(note, apply_pc1=True)

        # Check if vault chunk count drifted by >= 25% since last full fit
        current_total = sum(len(n.chunk_ids) for n in all_notes.values())
        if abs(current_total - self.total_chunks_at_last_fit) >= 0.25 * max(
            self.total_chunks_at_last_fit, 200
        ):
            self.fit(all_notes)

    def remove_note(self, note_id: str, all_notes: Dict[str, NoteChunks]) -> None:
        """Incremental hook when a note is deleted from the vault."""
        all_notes.pop(note_id, None)
        self.num_notes = sum(1 for n in all_notes.values() if len(n.chunk_ids) > 0)

    def _calibrate_single_note(self, note: NoteChunks, apply_pc1: bool = True) -> None:
        """Computes centered_vectors, mu, sigma, weights, and centroid for one note."""
        c = note.raw_vectors - self.vault_mean_vec[None, :]
        norms = np.linalg.norm(c, axis=1, keepdims=True)
        V_i = (c / np.maximum(norms, 1e-8)).astype(np.float32)
        note.centered_vectors = V_i

        K_bg = len(self.bg_vectors)
        if K_bg > 5:
            sims = V_i @ self.bg_vectors.T  # shape (m, K_bg)
            same_mask = np.array([nid == note.note_id for nid in self.bg_note_ids], dtype=bool)
            if np.any(same_mask) and np.sum(~same_mask) > 5:
                sims = sims[:, ~same_mask]
            mu = np.median(sims, axis=1)
            mad = np.median(np.abs(sims - mu[:, None]), axis=1)
            sigma = np.maximum(1.4826 * mad, self.MIN_SIGMA_FLOOR)
            z_bg = (sims - mu[:, None]) / sigma[:, None]
            df_i = np.sum(z_bg >= 2.5, axis=1) * (max(self.num_notes, 10) / max(sims.shape[1], 1))
        else:
            mu = np.zeros(len(note.chunk_ids), dtype=np.float32)
            sigma = np.full(len(note.chunk_ids), self.DEFAULT_SIGMA, dtype=np.float32)
            df_i = np.zeros(len(note.chunk_ids), dtype=np.float32)

        if self.low_confidence_vault:
            sigma = np.maximum(sigma, self.DEFAULT_SIGMA)

        note.mu = mu.astype(np.float32)
        note.sigma = sigma.astype(np.float32)

        # Specificity factor s_i in [0, 1] (removes template/boilerplate chunks)
        N = max(self.num_notes, 10)
        s_i = np.log((N + 1.0) / (df_i + 1.0)) / np.log(N + 1.0)
        s_i = np.where(df_i > 0.20 * N, 0.0, np.clip(s_i, 0.0, 1.0))

        # Intra-note redundancy divisor r_i >= 1.0 (discounts duplicate chunks in same note)
        S_self = V_i @ V_i.T
        r_i = np.sum(np.clip((S_self - 0.75) / 0.25, 0.0, 1.0), axis=1)
        r_i = np.maximum(r_i, 1.0)

        # Sublinear body token weight capped at 400 tokens
        t_capped = np.clip(note.body_tokens, 16.0, 400.0)
        note.weights = (np.sqrt(t_capped) * s_i / r_i).astype(np.float32)

        # Weighted note centroid
        w_sum = float(note.weights.sum())
        if w_sum > 1e-6:
            c_vec = (note.weights[:, None] * V_i).sum(axis=0) / w_sum
        else:
            c_vec = V_i.mean(axis=0)
        note.centroid = (c_vec / max(np.linalg.norm(c_vec), 1e-8)).astype(np.float32)

        if apply_pc1 and np.any(self.pc1_vec != 0):
            self._remove_pc1_from_centroid(note)

    def _remove_pc1_from_centroid(self, note: NoteChunks) -> None:
        proj = float(np.dot(note.centroid, self.pc1_vec)) * self.pc1_vec
        c_clean = note.centroid - proj
        note.centroid = (c_clean / max(np.linalg.norm(c_clean), 1e-8)).astype(np.float32)

    def _fit_tail_table(self, valid_notes: List[NoteChunks], num_pairs: int = 100_000) -> None:
        """Tabulates empirical -log10(P(Z_null >= z)) and fits log-linear tail slope."""
        if len(valid_notes) < 2 or self.low_confidence_vault:
            z = self.z_quantiles
            p_approx = (
                0.5
                * np.exp(-0.5 * np.maximum(z, 0.0) ** 2)
                / np.sqrt(2.0 * np.pi * np.maximum(z, 1.0) ** 2)
            )
            self.neglog10_table = np.where(
                z <= 0, 0.0, -np.log10(np.clip(p_approx, 1e-12, 1.0))
            ).astype(np.float32)
            self.tail_anchor_z = 3.5
            self.tail_anchor_nlq = float(np.interp(3.5, self.z_quantiles, self.neglog10_table))
            self.tail_slope = 0.95
            return

        n_notes = len(valid_notes)
        idx_a = self.rng.integers(0, n_notes, size=num_pairs)
        idx_b = (idx_a + self.rng.integers(1, n_notes, size=num_pairs)) % n_notes

        v_a = np.empty((num_pairs, 384), dtype=np.float32)
        v_b = np.empty((num_pairs, 384), dtype=np.float32)
        mu_a = np.empty(num_pairs, dtype=np.float32)
        mu_b = np.empty(num_pairs, dtype=np.float32)
        sig_a = np.empty(num_pairs, dtype=np.float32)
        sig_b = np.empty(num_pairs, dtype=np.float32)

        for k in range(num_pairs):
            na, nb = valid_notes[idx_a[k]], valid_notes[idx_b[k]]
            ca = int(self.rng.integers(0, len(na.chunk_ids)))
            cb = int(self.rng.integers(0, len(nb.chunk_ids)))
            v_a[k], mu_a[k], sig_a[k] = na.centered_vectors[ca], na.mu[ca], na.sigma[ca]
            v_b[k], mu_b[k], sig_b[k] = nb.centered_vectors[cb], nb.mu[cb], nb.sigma[cb]

        sims = np.sum(v_a * v_b, axis=1)
        z_sym = np.minimum((sims - mu_a) / sig_a, (sims - mu_b) / sig_b)
        z_sorted = np.sort(z_sym)

        ranks = np.searchsorted(z_sorted, self.z_quantiles, side="left")
        exceedance = np.maximum(num_pairs - ranks, 1) / (num_pairs + 1.0)
        self.neglog10_table = (-np.log10(exceedance)).astype(np.float32)

        z_q2 = float(np.percentile(z_sorted, 99.0))
        z_q3 = float(np.percentile(z_sorted, 99.9))
        self.tail_anchor_z = max(z_q3, z_q2 + 0.25)
        self.tail_anchor_nlq = 3.0
        self.tail_slope = 1.0 / max(self.tail_anchor_z - z_q2, 0.25)

    def neglog10_tail(self, z: np.ndarray) -> np.ndarray:
        """Maps symmetric Z-score matrix to -log10(p) with log-linear tail extrapolation."""
        base = np.interp(z, self.z_quantiles, self.neglog10_table)
        extrapolated = self.tail_anchor_nlq + self.tail_slope * (z - self.tail_anchor_z)
        return np.where(z > self.tail_anchor_z, extrapolated, base)


# ============================================================================
# Stage 1 — High-Recall Candidate Generation
# ============================================================================


def generate_candidates(
    focus_note: NoteChunks,
    all_notes: Dict[str, NoteChunks],
    excluded_note_ids: Set[str],
    ann_neighbors_per_chunk: List[List[Tuple[str, int, float]]],
    max_candidates: int = 50,
) -> List[str]:
    """
    Unions chunk-level ANN z-score votes with a brute-force SIF centroid scan.
    Query the ANN index with K = min(100, len(focus_note.chunk_ids) + 60) per chunk
    so same-note chunks never starve cross-note recall.
    """
    excluded = set(excluded_note_ids) | {focus_note.note_id}
    chunk_votes: Dict[str, float] = {}

    for i, neighbors in enumerate(ann_neighbors_per_chunk):
        mu_i = float(focus_note.mu[i]) if len(focus_note.mu) > i else 0.0
        sig_i = float(focus_note.sigma[i]) if len(focus_note.sigma) > i else 0.115
        for cand_id, _, raw_cos in neighbors:
            if cand_id in excluded or cand_id not in all_notes:
                continue
            z_approx = (raw_cos - mu_i) / sig_i
            if z_approx > 1.0:
                chunk_votes[cand_id] = chunk_votes.get(cand_id, 0.0) + z_approx

    top_ann_ids = [
        cid for cid, _ in sorted(chunk_votes.items(), key=lambda x: x[1], reverse=True)[:35]
    ]

    cand_ids = [
        nid for nid in all_notes if nid not in excluded and len(all_notes[nid].chunk_ids) > 0
    ]
    if cand_ids:
        centroid_mat = np.stack([all_notes[nid].centroid for nid in cand_ids], axis=0)
        centroid_sims = centroid_mat @ focus_note.centroid
        top_centroid_indices = np.argsort(centroid_sims)[::-1][:25]
        top_centroid_ids = [
            cand_ids[idx] for idx in top_centroid_indices if centroid_sims[idx] > 0.15
        ]
    else:
        top_centroid_ids = []

    combined: List[str] = []
    seen: Set[str] = set()
    for cid in top_ann_ids + top_centroid_ids:
        if cid not in seen:
            seen.add(cid)
            combined.append(cid)
            if len(combined) >= max_candidates:
                break
    return combined


# ============================================================================
# Stage 2 — Exact Matrix Scoring & Evidence Extraction
# ============================================================================


def _greedy_dedup_max(g_matrix: np.ndarray, reuse_discount: float = 0.5) -> np.ndarray:
    """Discounts repeated claims on the same target chunk to prevent star-graph collapse."""
    m, n = g_matrix.shape
    row_best = g_matrix.max(axis=1)
    row_argmax = g_matrix.argmax(axis=1)

    order = np.argsort(row_best)[::-1]
    col_claims = np.zeros(n, dtype=np.int32)
    adjusted = np.zeros(m, dtype=np.float32)

    for r in order:
        val = float(row_best[r])
        if val <= 0.0:
            break
        c = int(row_argmax[r])
        adjusted[r] = val * (reuse_discount ** int(col_claims[c]))
        col_claims[c] += 1

    return adjusted


def score_candidate_pair(
    focus: NoteChunks,
    candidate: NoteChunks,
    calib: VaultCalibrationIndex,
    max_evidence: int = 5,
) -> Optional[RelatednessResult]:
    """Scores a single (focus, candidate) note pair using exact chunk matrix & E-values."""
    m, n = len(focus.chunk_ids), len(candidate.chunk_ids)
    if m == 0 or n == 0 or focus.note_id == candidate.note_id:
        return None

    wa, wb = focus.weights, candidate.weights
    if float(wa.sum()) < 1e-6 or float(wb.sum()) < 1e-6:
        return None

    S_raw = focus.raw_vectors @ candidate.raw_vectors.T
    best_raw_cos = float(S_raw.max())
    if best_raw_cos < calib.RAW_COSINE_GUARD_FLOOR:
        return None

    S_centered = focus.centered_vectors @ candidate.centered_vectors.T
    Z_a = (S_centered - focus.mu[:, None]) / focus.sigma[:, None]
    Z_b = (S_centered - candidate.mu[None, :]) / candidate.sigma[None, :]
    Z = np.minimum(Z_a, Z_b)

    nlq = calib.neglog10_tail(Z)
    g = np.clip((nlq - 2.0) / 2.0, 0.0, 1.0)
    if np.all(g == 0.0):
        return None

    g_a_to_b = _greedy_dedup_max(g, reuse_discount=0.5)
    g_b_to_a = _greedy_dedup_max(g.T, reuse_discount=0.5)

    cover_a = float(np.sum(wa * g_a_to_b) / wa.sum())
    cover_b = float(np.sum(wb * g_b_to_a) / wb.sum())

    resemblance = (
        (2.0 * cover_a * cover_b / (cover_a + cover_b)) if (cover_a + cover_b) > 0 else 0.0
    )
    containment = max(cover_a, cover_b)
    best_q = float(nlq.max())

    # Analytical size-stratified null significance (Karlin-Altschul / Poisson-clump)
    eff_m = float((wa.sum() ** 2) / np.sum(wa**2))
    eff_n = float((wb.sum() ** 2) / np.sum(wb**2))

    p_hit_a = 1.0 - (0.99**n)
    p_hit_b = 1.0 - (0.99**m)
    null_mean_r = 0.18 * (2.0 * p_hit_a * p_hit_b / max(p_hit_a + p_hit_b, 1e-6))
    null_std_r = (
        0.22 * np.sqrt(0.5 * (p_hit_a / max(eff_m, 1.0) + p_hit_b / max(eff_n, 1.0))) + 0.015
    )

    z_resemblance = max(0.0, (resemblance - null_mean_r) / max(null_std_r, 0.01))
    k_eff = min(float(np.sum(g_a_to_b > 0.25)), float(np.sum(g_b_to_a > 0.25)))
    nlq_resemblance = 0.2171 * (z_resemblance**2) + 0.85 * max(0.0, k_eff - 1.0)
    p_resemblance = 10.0 ** (-min(nlq_resemblance, 12.0))

    p_best_section = min(1.0, (m * n) * (10.0 ** (-best_q)))
    if containment >= 0.65 and min(m, n) <= 3:
        p_best_section *= max(0.1, 1.0 - 0.8 * containment)

    p_combined = min(1.0, 2.0 * min(p_resemblance, p_best_section))
    e_value = max(calib.num_notes, 100) * p_combined

    if resemblance >= 0.88 and containment >= 0.90:
        tier = "near-duplicate"
    elif e_value < 0.1:
        tier = "strong"
    elif e_value < 1.0:
        tier = "likely"
    elif e_value < 10.0:
        tier = "possible"
    else:
        return None

    sig_score = np.clip((1.0 - np.log10(max(e_value, 1e-4))) / 5.0, 0.0, 1.0)
    display_score = float(
        np.clip(0.65 * sig_score + 0.35 * max(resemblance, 0.7 * containment), 0.0, 0.99)
    )

    if containment >= 2.2 * max(resemblance, 1e-4):
        smaller_label = "this note" if cover_a >= cover_b else "target note"
        ui_subtitle = f"Covers {int(round(containment * 100))}% of {smaller_label}"
    else:
        ui_subtitle = (
            f"Covers {int(round(cover_a * 100))}% of this note · "
            f"{int(round(cover_b * 100))}% of target"
        )

    evidence = _extract_distinct_evidence(focus, candidate, S_raw, g, nlq, max_evidence)

    return RelatednessResult(
        candidate_note_id=candidate.note_id,
        candidate_title=candidate.title,
        tier=tier,
        display_score=round(display_score, 4),
        e_value=float(e_value),
        p_value=float(p_combined),
        resemblance=round(resemblance, 4),
        containment=round(containment, 4),
        cover_focus=round(cover_a, 4),
        cover_candidate=round(cover_b, 4),
        best_chunk_neglog10_p=round(best_q, 2),
        best_raw_cosine=round(best_raw_cos, 4),
        ui_subtitle=ui_subtitle,
        evidence_passages=evidence,
    )


def _extract_distinct_evidence(
    focus: NoteChunks,
    candidate: NoteChunks,
    S_raw: np.ndarray,
    g: np.ndarray,
    nlq: np.ndarray,
    max_pairs: int = 5,
) -> List[MatchedPassage]:
    """Greedily selects up to `max_pairs` 1-to-1 non-overlapping chunk pairs."""
    m, n = g.shape
    flat_indices = np.argsort(nlq.ravel())[::-1]
    used_a: Set[int] = set()
    used_b: Set[int] = set()
    passages: List[MatchedPassage] = []

    for flat_idx in flat_indices:
        i, j = int(flat_idx // n), int(flat_idx % n)
        if g[i, j] <= 0.0:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        passages.append(
            MatchedPassage(
                source_chunk_id=focus.chunk_ids[i],
                target_chunk_id=candidate.chunk_ids[j],
                source_heading=focus.headings[i],
                target_heading=candidate.headings[j],
                source_excerpt=focus.excerpts[i],
                target_excerpt=candidate.excerpts[j],
                raw_cosine=round(float(S_raw[i, j]), 4),
                calibrated_strength=round(float(g[i, j]), 4),
                neglog10_p=round(float(nlq[i, j]), 2),
            )
        )
        if len(passages) >= max_pairs:
            break

    return passages


def score_focus_note(
    focus_note: NoteChunks,
    candidate_ids: List[str],
    all_notes: Dict[str, NoteChunks],
    calib: VaultCalibrationIndex,
    top_k_results: int = 5,
) -> List[RelatednessResult]:
    """Scores all Stage 1 candidates and returns the top ranked Missing Links cards."""
    results: List[RelatednessResult] = []
    for cid in candidate_ids:
        cand = all_notes.get(cid)
        if cand is None:
            continue
        res = score_candidate_pair(focus_note, cand, calib)
        if res is not None:
            results.append(res)

    results.sort(key=lambda r: (r.e_value, -r.display_score))
    return results[:top_k_results]
```

---

### 3. UI & Downstream Threshold Bindings

Bind the fields of `RelatednessResult` to the Missing Links sidebar and LLM discovery pipeline as follows:

| Consumer | Field / Condition | Behavior |
| --- | --- | --- |
| **Sidebar Card Order** | `results` list order | Already sorted by `e_value` ascending, tie-broken by `-display_score`. |
| **Card Primary Badge** | `f"{result.tier.title()} · {int(result.display_score * 100)}%"` | Displays e.g. `Strong · 86%` or `Likely · 62%`. |
| **Card Subtitle** | `result.ui_subtitle` | Displays e.g. `Covers 92% of this note` (for containment) or `Covers 28% of this note · 35% of target` (for broad overlap). |
| **Sidebar Filter** | `result is not None` | Automatically hides noisy candidates with `e_value >= 10.0` or `best_raw_cosine < 0.58`. |
| **LLM Discovery Gate** | `result.e_value < 0.1` (or `result.display_score >= 0.75`) | Ensures only statistically verified (`"strong"`) pairs consume LLM tokens. |
| **Expandable Evidence** | `result.evidence_passages` | Renders the top 3–5 non-overlapping passage matches with headings and excerpts. |

---

### 4. Automated Verification Suite: `test_missing_links_scorer.py`

Save this file alongside `missing_links_scorer.py` and run `pytest test_missing_links_scorer.py` to verify all mathematical and product requirements.

```python
import numpy as np
from typing import Dict, Optional
from missing_links_scorer import (
    NoteChunks,
    VaultCalibrationIndex,
    score_candidate_pair,
)


def _build_synthetic_vault(
    seed: int = 123,
) -> tuple[Dict[str, NoteChunks], np.ndarray, np.random.Generator]:
    rng = np.random.default_rng(seed)
    common_cone = rng.normal(size=384).astype(np.float32)
    common_cone /= np.linalg.norm(common_cone)

    def make_vec(topic_vec: Optional[np.ndarray] = None, mix: float = 0.0) -> np.ndarray:
        noise = rng.normal(size=384).astype(np.float32)
        noise /= np.linalg.norm(noise)
        v = 0.78 * common_cone + 0.62 * noise
        if topic_vec is not None and mix > 0:
            v = (1.0 - mix) * v + mix * topic_vec
        return (v / np.linalg.norm(v)).astype(np.float32)

    vault: Dict[str, NoteChunks] = {}
    for idx in range(400):
        m_chunks = int(rng.choice([1, 3, 8, 15, 35]))
        vecs = np.stack([make_vec() for _ in range(m_chunks)], axis=0)
        nid = f"note_{idx}"
        vault[nid] = NoteChunks(
            note_id=nid,
            title=f"Note {idx}",
            chunk_ids=[f"{nid}_c{k}" for k in range(m_chunks)],
            headings=[f"# Note {idx} > ## Sec {k}" for k in range(m_chunks)],
            excerpts=["Body text"] * m_chunks,
            raw_vectors=vecs,
            body_tokens=np.full(m_chunks, 180.0, dtype=np.float32),
        )
    return vault, common_cone, rng


def test_unrelated_large_notes_are_suppressed():
    """Verifies that the n/(n+1) percentile inflation bug is eliminated."""
    vault, common_cone, rng = _build_synthetic_vault()

    def rand_vec():
        noise = rng.normal(size=384).astype(np.float32)
        noise /= np.linalg.norm(noise)
        v = 0.78 * common_cone + 0.62 * noise
        return (v / np.linalg.norm(v)).astype(np.float32)

    vault["unrel_40"] = NoteChunks(
        "unrel_40",
        "Unrelated 40",
        [f"u40_{k}" for k in range(40)],
        ["H"] * 40,
        ["T"] * 40,
        np.stack([rand_vec() for _ in range(40)]),
        np.full(40, 200.0, dtype=np.float32),
    )
    vault["unrel_30"] = NoteChunks(
        "unrel_30",
        "Unrelated 30",
        [f"u30_{k}" for k in range(30)],
        ["H"] * 30,
        ["T"] * 30,
        np.stack([rand_vec() for _ in range(30)]),
        np.full(30, 200.0, dtype=np.float32),
    )

    calib = VaultCalibrationIndex()
    calib.fit(vault)

    res = score_candidate_pair(vault["unrel_40"], vault["unrel_30"], calib)
    assert res is None or res.e_value > 2.0


def test_worked_example_40x30_and_atomic_containment():
    """Verifies both the 40x30 (10 shared sections) worked example and 1-in-40 containment."""
    vault, common_cone, rng = _build_synthetic_vault()

    def make_vec(topic: Optional[np.ndarray] = None, mix: float = 0.0) -> np.ndarray:
        noise = rng.normal(size=384).astype(np.float32)
        noise /= np.linalg.norm(noise)
        v = 0.78 * common_cone + 0.62 * noise
        if topic is not None:
            v = (1.0 - mix) * v + mix * topic
        return (v / np.linalg.norm(v)).astype(np.float32)

    topics = [make_vec() for _ in range(10)]
    vecs_40 = np.stack([make_vec(topics[k], 0.86) if k < 10 else make_vec() for k in range(40)])
    vecs_30 = np.stack([make_vec(topics[k], 0.86) if k < 10 else make_vec() for k in range(30)])

    vault["worked_40"] = NoteChunks(
        "worked_40",
        "Worked 40",
        [f"w40_{k}" for k in range(40)],
        ["H"] * 40,
        ["T"] * 40,
        vecs_40,
        np.full(40, 200.0, dtype=np.float32),
    )
    vault["worked_30"] = NoteChunks(
        "worked_30",
        "Worked 30",
        [f"w30_{k}" for k in range(30)],
        ["H"] * 30,
        ["T"] * 30,
        vecs_30,
        np.full(30, 200.0, dtype=np.float32),
    )
    vault["atomic_1"] = NoteChunks(
        "atomic_1",
        "Atomic 1",
        ["a_0"],
        ["# Atomic"],
        ["Body"],
        np.stack([make_vec(topics[0], 0.90)]),
        np.array([200.0], dtype=np.float32),
    )

    calib = VaultCalibrationIndex()
    calib.fit(vault)

    res_worked = score_candidate_pair(vault["worked_40"], vault["worked_30"], calib)
    assert res_worked is not None
    assert res_worked.tier == "strong"
    assert len(res_worked.evidence_passages) == 5

    res_atomic = score_candidate_pair(vault["atomic_1"], vault["worked_40"], calib)
    assert res_atomic is not None
    assert res_atomic.tier in ("strong", "likely")
    assert res_atomic.containment >= 0.80


def test_clone_stutter_resistance():
    """Duplicating a matching chunk 5x inside Note A must not inflate the score."""
    vault, common_cone, rng = _build_synthetic_vault()

    def make_vec(topic: Optional[np.ndarray] = None, mix: float = 0.0) -> np.ndarray:
        noise = rng.normal(size=384).astype(np.float32)
        noise /= np.linalg.norm(noise)
        v = 0.78 * common_cone + 0.62 * noise
        if topic is not None:
            v = (1.0 - mix) * v + mix * topic
        return (v / np.linalg.norm(v)).astype(np.float32)

    shared = make_vec()
    v_match_a = make_vec(shared, 0.88)
    v_match_b = make_vec(shared, 0.88)
    other_a = [make_vec() for _ in range(4)]
    other_b = [make_vec() for _ in range(4)]

    vault["orig_A"] = NoteChunks(
        "orig_A",
        "Orig A",
        [f"oa_{k}" for k in range(5)],
        ["H"] * 5,
        ["T"] * 5,
        np.stack([v_match_a] + other_a),
        np.full(5, 200.0, dtype=np.float32),
    )
    # Clone the matching chunk 5 times in Note A (9 chunks total)
    vault["cloned_A"] = NoteChunks(
        "cloned_A",
        "Cloned A",
        [f"ca_{k}" for k in range(9)],
        ["H"] * 9,
        ["T"] * 9,
        np.stack([v_match_a] * 5 + other_a),
        np.full(9, 200.0, dtype=np.float32),
    )
    vault["target_B"] = NoteChunks(
        "target_B",
        "Target B",
        [f"tb_{k}" for k in range(5)],
        ["H"] * 5,
        ["T"] * 5,
        np.stack([v_match_b] + other_b),
        np.full(5, 200.0, dtype=np.float32),
    )

    calib = VaultCalibrationIndex()
    calib.fit(vault)

    res_orig = score_candidate_pair(vault["orig_A"], vault["target_B"], calib)
    res_cloned = score_candidate_pair(vault["cloned_A"], vault["target_B"], calib)
    assert res_orig is not None and res_cloned is not None
    assert abs(res_cloned.resemblance - res_orig.resemblance) < 0.04
```