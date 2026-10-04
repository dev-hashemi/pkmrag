# Subsystem: Semantic Gap Discovery

The discovery subsystem implements Tier 3 of Orbit's Hybrid GraphRAG architecture: discovering implicit conceptual relationships between notes that share high semantic similarity but lack explicit human graph links.

---

## 💾 Storage & Lifecycle
- **Implementation:** [`src/orbit/discovery/engine.py`](file:///home/ali/projects/my/project-orbit/src/orbit/discovery/engine.py)
- **Graph Storage:** Persisted to LadybugDB in the `[:INFERRED_REL]` edge table.
- **CLI Interface:** `orbit discover <vault> --threshold 0.80`

---

## 🔄 3-Tier Discovery Pipeline

```
[LanceDB Vector Store]
          │
          ▼ 1. Find Nearest Neighbor Note Pairs (Cosine Similarity ≥ Threshold)
[Candidate Note Pairs]
          │
          ▼ 2. Graph Filter: Exclude pairs with LadybugDB distance ≤ max_hops
[Unlinked Semantic Gaps]
          │
          ▼ 3. Targeted LLM Inference (Classify conceptual relationship)
[[:INFERRED_REL] Edges in LadybugDB]
```

### Step 1: Vector Candidate Mining
Scans chunk embeddings across notes in LanceDB using cosine similarity to discover unlinked notes discussing similar concepts.

### Step 2: Deterministic Graph Distance Filtering
For each high-similarity note pair $(A, B)$, Orbit queries LadybugDB to evaluate existing topological connectivity:
- If $B$ is reachable from $A$ within $\le 2$ hops via explicit `[:LINKS_TO]` edges, the pair is **pruned** (as the relationship is already known/structured).
- If the pair already has an evaluated `[:INFERRED_REL]` edge, it is skipped.
- Only topologically disconnected note pairs proceed to inference.

### Step 3: Targeted LLM Classification
The candidate pair's representative text snippets are submitted to the LLM to infer relationship types (`[:EXTENDS]`, `[:CONTRADICTS]`, `[:SUPPORTS]`, `[:PREREQUISITE_FOR]`, `[:REFINES]`).

### Step 4: Isolated Edge Persistence
Inferred relationships are written to LadybugDB's `[:INFERRED_REL]` table with confidence, model name, reason, and creation timestamp. They are strictly isolated from human-curated `[:LINKS_TO]` wikilinks.
