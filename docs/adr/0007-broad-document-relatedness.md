### Architectural Decision Record: Calibrated Multi-Signal Document Relatedness from Chunk Embeddings

* **Status:** Accepted
* **Date:** 2026-10-27
* **Context:** Missing Links Sidebar & Semantic Discovery Engine
* **Embedding Model:** `BAAI/bge-small-en-v1.5` ($d = 384$, L2-normalized cosine similarity)

---

### 1. Context & Problem Statement

Our local-first Markdown knowledge base splits notes by heading hierarchy into $1$ to $40+$ chunks (target size $\le 400$ tokens, prepended with a `# Note Title -> ## Heading` breadcrumb) and embeds each chunk with `BAAI/bge-small-en-v1.5`. No document-level embedding model or cross-encoder is available on the default synchronous path.

When a user opens a focus note $A$ ($m$ chunks), the **Missing Links** sidebar must rank unlinked candidate notes $B$ ($n$ chunks) across vaults of $10^3$–$10^4$ notes ($10^4$–$10^5$ chunks) within interactive browsing latency ($\lt 10\text{ ms}$ per query).

The system must simultaneously satisfy two distinct semantic retrieval intents (Broder, 1997):

1. **Broad Resemblance ($R$):** Do notes $A$ and $B$ cover substantially similar material overall?
2. **Directional Containment ($C$) & Specific Evidence ($q_{\max}$):** Is a shorter atomic note $A$ fully captured within a single section of a comprehensive hub note $B$, or do two multi-topic notes share a distinct, high-value passage worthy of an explicit wiki-link?

---

### 2. Mathematical Failure Analysis of the Legacy Heuristic

The legacy heuristic queries top-20 ANN neighbors per chunk of $A$, applies a hard cosine floor $\tau = 0.65$, defines matched chunk sets $M_A, M_B$, and computes:

$$\text{avg} = \frac{\sum_{a \in M_A} \max_{b \in B} S(a,b) + \sum_{b \in M_B} \max_{a \in A} S(a,b)}{\vert{}M_A\vert{} + \vert{}M_B\vert{}}$$

$$\text{coverage} = \min\left(\frac{\vert{}M_A\vert{}}{m}, \frac{\vert{}M_B\vert{}}{n}\right), \qquad \text{score}_{\text{legacy}} = \text{avg} \cdot (0.3 + 0.7 \cdot \text{coverage})$$

This formulation exhibits five structural failure modes:

1. **Severe Length & Multi-Topic Penalty:** Because $\text{coverage}$ uses the $\min$ ratio, a $40$-chunk note and a $30$-chunk note sharing $10$ near-identical sections ($S = 0.90$) yield $\text{coverage} = \min(10/40, 10/30) = 0.25$ and $\text{score}_{\text{legacy}} = 0.90 \times (0.3 + 0.7 \times 0.25) = 0.4275$ ("43% similar"). Two $1$-chunk notes with the exact same $0.90$ match yield $0.900$ ("90% similar").
2. **Weak-Broad vs. Strong-Specific Inversion:** For $m = n = 10$, ten generic matches at $S = 0.70$ produce $\text{coverage} = 1.0 \implies \text{score} = 0.700$, outranking a single near-identical section at $S = 0.95$ ($\text{coverage} = 0.1 \implies \text{score} = 0.95 \times 0.37 = 0.3515$).
3. **Anisotropy & Non-Portable Thresholds:** Transformer embeddings occupy a narrow forward cone (Ethayarajh, 2019). In a topically homogeneous vault, the median cross-note cosine is $\approx 0.67$, placing the hardcoded $0.65$ cutoff below the noise median. In a diverse vault, $0.65$ is overly restrictive.
4. **Hubness & Template Inflation:** Generic chunks (e.g., daily note templates `# YYYY-MM-DD -> ## Tasks`) reside near the vault centroid and behave as "hubs" (Radovanović et al., 2010), producing high cosine similarity with arbitrary notes.
5. **ANN Post-Filtering Starvation:** Because every chunk in Note $A$ shares the `# Note A Title` breadcrumb prefix, intra-note cosines are artificially inflated ($\ge 0.80$). Fetching $K=20$ ANN neighbors and filtering out `note_id == A` *after* retrieval starves long notes of cross-note candidates.

---

### 3. Critique of Rejected Alternatives

#### 3.1 Why Naive Percentile Calibration + MaxSim Fails (The Order-Statistic Bug)

A natural proposal is to replace raw cosine $S_{ij}$ with its empirical global percentile $g(i,j) \in [0, 1]$ among random cross-note chunk pairs, then compute bidirectional mean coverage:

$$\text{cover}_A = \frac{1}{m} \sum_{i=1}^m \max_{j=1\dots n} g(i, j), \qquad \text{cover}_B = \frac{1}{n} \sum_{j=1}^n \max_{i=1\dots m} g(i, j)$$

**Mathematical Proof of Failure:** By the probability integral transform, if $A$ and $B$ are completely unrelated notes, each calibrated entry $g(i,j)$ is distributed as $\text{Uniform}(0, 1)$. For a fixed chunk $a_i$, the maximum over $n$ independent uniform draws $U_1, \dots, U_n \sim \text{Uniform}(0,1)$ has cumulative distribution function $F_{\max}(u) = u^n$ and expected value:

$$\mathbb{E}\left[\max_{j=1\dots n} g(i, j)\right] = \int_0^1 n u^n \, du = \frac{n}{n + 1}$$

Consequently, for two **completely unrelated** notes with $m = 40$ and $n = 30$:

$$\mathbb{E}[\text{cover}_A] = \frac{30}{31} \approx 0.968, \qquad \mathbb{E}[\text{cover}_B] = \frac{40}{41} \approx 0.976, \qquad \text{F1} \approx 0.972$$

Mapping similarities to uniform percentiles destroys sparsity at the bottom of the distribution and turns $\max_j$ into a monotonic function of partner note length $n$.

#### 3.2 Why Pure F1 Coverage Alone Cannot Rank "Missing Links"

Even when non-matches are properly zeroed out via a dead zone, symmetric F1 coverage:

$$R = \frac{2 \cdot \text{cover}_A \cdot \text{cover}_B}{\text{cover}_A + \text{cover}_B}$$

measures *resemblance*, not *containment*. Consider an atomic note $A$ ($m = 1$) that is duplicated verbatim inside one section of a comprehensive literature note $B$ ($n = 40$). Here $\text{cover}_A = 1.0$ and $\text{cover}_B = 1/40 = 0.025$, yielding:

$$R = \frac{2(1.0)(0.025)}{1.025} \approx 0.0488$$

In a personal knowledge base, linking an atomic concept note to the hub note that discusses it is a primary use case. Ranking solely by $R$ buries all asymmetric containment links.

#### 3.3 Why Balanced & Entropic Optimal Transport (Sinkhorn / WMD) Were Rejected

1. **Balanced Optimal Transport (Earth Mover's Distance):** Enforces marginal conservation $\sum_{j=1}^n T_{ij} = \tilde{w}_i$ and $\sum_{i=1}^m T_{ij} = \tilde{u}_j$. When Note $A$ ($40$ chunks) and Note $B$ ($5$ chunks) share $2$ sections, Balanced OT is forced to transport the remaining $38$ unrelated chunks of $A$ onto the $5$ chunks of $B$. The transport cost becomes dominated by the distance between unrelated sections.
2. **Unbalanced Entropic Optimal Transport:** Introduces three interdependent hyperparameters (entropy regularization $\varepsilon$ and marginal KL penalties $\rho_A, \rho_B$) whose optimal values shift with note length and embedding scale, while obscuring the exact chunk-to-chunk attribution required by the UI evidence panel.
3. **Many-to-One Regularization via Greedy Decay:** The only theoretical advantage of OT over Chamfer/MaxSim is preventing "star-graph collapse" (where $10$ repetitive chunks in $A$ all claim the *same* single chunk $b_1$ in $B$). We achieve this directly in $O(m \log m)$ time by sorting $A$'s row maxima and applying a geometric reuse discount $\gamma = 0.5^{k}$ on the $k$-th repeat claim of any target column $j$, combined with an intra-note redundancy divisor $r_i$.

#### 3.4 Why Brute-Force Pairwise Monte Carlo Nulls Were Rejected

Simulating $10^5$ random note pairs across size-stratified buckets requires $10^9$–$10^{10}$ floating-point operations (30–90 seconds in Python) and suffers from empty or sparse buckets for large notes ($m, n \ge 15$) in small-to-medium vaults. Instead, because chunk pairs are already standardized to tail probabilities via a 1D lookup table, the exact null mean and variance of $R$ for any $(m, n)$ pair can be evaluated analytically in $O(1)$ time via Kish's effective sample size and Extreme Value Theory.

---

### 4. Selected Mathematical Architecture

#### 4.1 Anisotropy Removal: Mean Centering & SIF Centroids

Let $v^{\text{raw}}_{a_i} \in \mathbb{R}^{384}$ be the L2-normalized `bge-small-en-v1.5` embedding of chunk $a_i$. To prevent long notes from dominating the vault center, we compute the note-balanced vault mean vector across all $N$ notes:

$$\bar{v}_{\text{vault}} = \frac{1}{N} \sum_{A=1}^{N} \left( \frac{1}{m_A} \sum_{i=1}^{m_A} v^{\text{raw}}_{a_i} \right)$$

Every chunk vector is centered and re-normalized:

$$v_{a_i} = \frac{v^{\text{raw}}_{a_i} - \bar{v}_{\text{vault}}}{\left\Vert{} v^{\text{raw}}_{a_i} - \bar{v}_{\text{vault}} \right\Vert{}_2}$$

This expands the effective cosine dynamic range from $[0.55, 1.0]$ to $[-0.40, 1.0]$ at zero runtime cost.

#### 4.2 Hubness Suppression: Symmetric Local Z-Scaling

For each chunk $a_i$, we sample $K_{\text{bg}} = 512$ random chunks (one per distinct foreign note) and compute robust location and scale statistics using the median and Median Absolute Deviation ($\text{MAD}$):

$$\mu_i = \text{median}_{b \in \text{bg}} \left(v_{a_i}^\top v_b\right), \qquad \sigma_i = \max\left(1.4826 \cdot \text{median}_{b \in \text{bg}} \left\vert{}v_{a_i}^\top v_b - \mu_i\right\vert{}, \, \sigma_{\min}\right)$$

For any candidate chunk pair $(a_i, b_j)$ with centered cosine $S_{ij} = v_{a_i}^\top v_{b_j}$, we define the **Symmetric Local Z-Score**:

$$Z_{ij} = \min\left( \frac{S_{ij} - \mu_i}{\sigma_i}, \, \frac{S_{ij} - \mu_j}{\sigma_j} \right)$$

Using $\min$ rather than an average enforces **mutual local surprise**: a match is strong only if $b_j$ is an outlier in $a_i$'s neighborhood *and* $a_i$ is an outlier in $b_j$'s neighborhood. Generic "hub" chunks have large $\mu_i$, automatically suppressing false positives.

#### 4.3 Empirical Tail Calibration & The 99% Dead Zone

During vault indexing, we sample $10^5$ random cross-note chunk pairs, compute their symmetric $Z$-scores, and tabulate the negative base-10 log exceedance probability:

$$q(z) = -\log_{10} \mathbb{P}\left(Z_{\text{null}} \ge z\right)$$

Beyond the $99.9\text{th}$ percentile ($q = 3.0$), $q(z)$ is extrapolated log-linearly using the empirical slope between $q = 2.0$ ($p = 10^{-2}$) and $q = 3.0$ ($p = 10^{-3}$).

Each entry $q_{ij} = q(Z_{ij})$ is mapped to a bounded match strength $g_{ij} \in [0, 1]$ via a linear ramp with a **99% dead zone**:

$$g_{ij} = \text{clip}\left( \frac{q_{ij} - 2.0}{4.0 - 2.0}, \, 0.0, \, 1.0 \right)$$

* Any chunk pair less rare than the top $1\%$ of random pairs ($q_{ij} \le 2.0$) receives **exact zero** ($g_{ij} = 0$).
* Any chunk pair at or beyond the top $0.01\%$ of random pairs ($q_{ij} \ge 4.0$) saturates at $g_{ij} = 1.0$.

This eliminates the $\frac{n}{n+1}$ uniform max-inflation bug: for unrelated notes, $99\%$ of entries in $g$ are strictly $0$.

#### 4.4 Tri-Factor Chunk Weighting (Sublinear Length, Specificity, Intra-Note Redundancy)

Each chunk $a_i$ receives weight:

$$w_i = \frac{\sqrt{\text{clip}(t_i, 16, 400)} \cdot s_i}{r_i}$$

1. **Sublinear Body Token Weight ($\sqrt{\text{clip}(t_i, 16, 400)}$):** Uses body token count $t_i$ (excluding the heading breadcrumb) capped at the model's effective context window ($400$ body tokens). Square-root scaling makes coverage nearly invariant to paragraph splitting while preventing long rambling sections from dominating concise atomic sections.
2. **Boilerplate Specificity ($s_i \in [0, 1]$):** Let $\text{df}_i$ be the estimated number of foreign notes in the vault containing a chunk with $Z \ge 2.5$ against $a_i$. We define inverse document frequency:

$$s_i = \begin{cases} 0 & \text{if } \text{df}_i \gt 0.20 N \\ \frac{\ln\left(\frac{N + 1}{\text{df}_i + 1}\right)}{\ln(N + 1)} & \text{otherwise} \end{cases}$$



Because $w_i$ appears in both the numerator and denominator of coverage, recurring daily-note template headings ($\text{df}_i \gg 1$) get $s_i \approx 0$ and vanish from both the numerator and denominator—neither creating false matches nor penalizing the note's unmatched chunk fraction.
3. **Intra-Note Redundancy Divisor ($r_i \ge 1$):** Using the intra-note centered similarity matrix $S_{AA} = V_A V_A^\top$,

$$r_i = \sum_{i'=1}^m \text{clip}\left(\frac{S_{AA}[i, i'] - 0.75}{0.25}, \, 0.0, \, 1.0\right)$$



If a paragraph is duplicated $k$ times inside Note $A$, each copy gets weight $1/k$, ensuring copy-pasted text cannot inflate coverage.

#### 4.5 Directional Coverage, Resemblance ($R$), and Containment ($C$)

Let $\hat{g}_{A \to B}(i)$ denote the row maximum $\max_j g_{ij}$ discounted by $\gamma = 0.5^{\text{claims}(j^*)}$ for each prior row of $A$ that already claimed column $j^*$. Then:

$$\text{cover}_A = \frac{\sum_{i=1}^m w_i \, \hat{g}_{A \to B}(i)}{\sum_{i=1}^m w_i}, \qquad \text{cover}_B = \frac{\sum_{j=1}^n u_j \, \hat{g}_{B \to A}(j)}{\sum_{j=1}^n u_j}$$

$$\text{Resemblance } R = \frac{2 \cdot \text{cover}_A \cdot \text{cover}_B}{\text{cover}_A + \text{cover}_B}, \qquad \text{Containment } C = \max(\text{cover}_A, \text{cover}_B)$$

#### 4.6 Analytical BLAST / Poisson-Clump Significance Ranker ($E$-Value)

To rank symmetric multi-section overlaps ($R$) and asymmetric section matches ($q_{\max} = \max_{i,j} q_{ij}, C$) on a single unified scale without a $10^{10}$-FLOP Monte Carlo loop, we evaluate two analytical null tests:

1. **Broad Resemblance Null Test ($p_R$):** Under the dead-zone null ($p_0 = 0.01$ probability of $g_{ij} \gt 0$, conditional positive mean $\mu_0 = 0.18$, std $\sigma_0 = 0.22$), the probability that a random chunk in $A$ finds at least one noise hit across $n$ chunks of $B$ is $p_{\text{hit}, A} = 1 - 0.99^n$ (and $p_{\text{hit}, B} = 1 - 0.99^m$). With Kish effective chunk counts $m_{\text{eff}} = \frac{(\sum w_i)^2}{\sum w_i^2}$ and $n_{\text{eff}} = \frac{(\sum u_j)^2}{\sum u_j^2}$, the null mean and standard deviation of $R$ are:

$$\mu_{R,0} = \mu_0 \frac{2 p_{\text{hit}, A} p_{\text{hit}, B}}{p_{\text{hit}, A} + p_{\text{hit}, B}}, \qquad \sigma_{R,0} = \sigma_0 \sqrt{\frac{1}{2}\left(\frac{p_{\text{hit}, A}}{m_{\text{eff}}} + \frac{p_{\text{hit}, B}}{n_{\text{eff}}}\right)} + 0.015$$



Combined with the corroborated chunk count $k_{\text{eff}} = \min\left(\#\{i : \hat{g}_{A\to B}(i) \gt 0.25\}, \#\{j : \hat{g}_{B\to A}(j) \gt 0.25\}\right)$, the broad negative log10 $p$-value is:

$$-\log_{10}(p_R) = 0.2171 \left(\max\left(0, \frac{R - \mu_{R,0}}{\sigma_{R,0}}\right)\right)^2 + 0.85 \max(0, k_{\text{eff}} - 1)$$


2. **Specific Section / Containment Null Test ($p_{\text{best}}$):** By the union bound across all $m \times n$ chunk pairs, the probability of observing a maximum peak rarity $q_{\max}$ by chance is:

$$p_{\text{best}} = \min\left(1.0, \, m \cdot n \cdot 10^{-q_{\max}}\right)$$



with a containment multiplier when a short note ($\min(m,n) \le 3$) is heavily covered ($C \ge 0.65$).
3. **Combined Bonferroni $p$-Value & Expected False Positives ($E$-Value):**

$$p_{\text{pair}} = \min\left(1.0, \, 2 \cdot \min(p_R, p_{\text{best}})\right), \qquad E = N_{\text{notes}} \cdot p_{\text{pair}}$$



Here $E$ has the exact interpretation of a **BLAST $E$-value** (Altschul et al., 1990): *the expected number of unrelated notes across the entire vault of size $N_{\text{notes}}$ that would achieve a match this strong by random chance.*

---

### 5. Consequences & Guarantees

* **Zero Length Bias:** Unrelated $40 \times 30$ pairs evaluate to $E \ge 10$ and are suppressed.
* **Unified Multi-Signal Ranking:** A $40 \times 30$ pair sharing $10$ sections ($R \approx 0.30, k_{\text{eff}} = 10 \implies E \lt 10^{-6}$) and a $1 \times 40$ atomic containment match ($C = 1.0, q_{\max} = 5.2 \implies E \lt 0.05$) both surface in the `"strong"` tier ($E \lt 0.1$).
* **Self-Calibrating Across Vaults:** Tiers (`E < 0.1` Strong, `E < 1.0` Likely, `E < 10.0` Possible) maintain identical false-positive rates regardless of whether the vault is topically narrow or broad.

---
