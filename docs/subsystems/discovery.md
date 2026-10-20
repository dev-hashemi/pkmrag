# Subsystem: Semantic Gap Discovery

The discovery subsystem implements Tier 3 of PKMRAG's Hybrid GraphRAG architecture: discovering implicit conceptual relationships between notes that share high semantic similarity but lack explicit human graph links.

---

## 💾 Storage & Lifecycle
- **Implementation:** [`src/pkmrag/discovery/engine.py`](file:///home/ali/projects/my/pkmrag/src/pkmrag/discovery/engine.py) (orchestration + LLM classification) and [`src/pkmrag/discovery/scanner.py`](file:///home/ali/projects/my/pkmrag/src/pkmrag/discovery/scanner.py) (vector + graph scanning)
- **Graph Storage:** Persisted to LadybugDB in the `[:INFERRED_REL]` edge table.
- **CLI Interface:** `pkmrag discover <vault> --threshold 0.80`
  - `--dry-run` opens the vault graph read-only, so it works while the background daemon holds the vault database. The write path reports a clear error instead of a driver traceback when the database is locked by another PKMRAG process.

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

The scan can be **scoped to a single note**. When a focus note is supplied, only that note's chunks are swept and the resulting pairs are exactly the vault-wide pairs that touch it — but the cost is proportional to the note instead of to the whole vault. This is what the Obsidian sidebar uses on every note open, so a request stays fast regardless of vault size.

### Step 2: Deterministic Graph Distance Filtering
For each high-similarity note pair $(A, B)$, PKMRAG queries LadybugDB to evaluate existing topological connectivity:
- If $B$ is reachable from $A$ within $\le 2$ hops via explicit `[:LINKS_TO]` edges, the pair is **pruned** (as the relationship is already known/structured).
- If the pair already has an evaluated `[:INFERRED_REL]` edge, it is skipped.
- Only topologically disconnected note pairs proceed to inference.

Hop distance is symmetric, so a note-scoped scan needs a single neighbour lookup for the focus note instead of one lookup per candidate pair.

### Step 3: Targeted LLM Classification
The candidate pair's representative text snippets are submitted to the LLM to infer relationship types (`[:EXTENDS]`, `[:CONTRADICTS]`, `[:SUPPORTS]`, `[:PREREQUISITE_FOR]`, `[:REFINES]`).

### Step 4: Isolated Edge Persistence
Inferred relationships are written to LadybugDB's `[:INFERRED_REL]` table with confidence, model name, reason, and creation timestamp. They are strictly isolated from human-curated `[:LINKS_TO]` wikilinks.
