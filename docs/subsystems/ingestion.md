# Subsystem: Ingestion Pipeline

The ingestion pipeline coordinates filesystem discovery, dialect-specific parsing, delta change detection, and parallel synchronization across graph and vector stores.

---

## 💾 Implementation
- **Pipeline:** [`src/pkmrag/ingest/pipeline.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/ingest/pipeline.py)
- **Indexer:** [`src/pkmrag/parser/indexer.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/parser/indexer.py)
- **Dialects:** [`src/pkmrag/dialects/`](file:///home/ali/projects/my/project-orbit/src/pkmrag/dialects/)

---

## 🔌 Pluggable Dialect Strategy

Orbit separates syntax parsing from storage using [`KnowledgeDialect`](file:///home/ali/projects/my/project-orbit/src/pkmrag/dialects/base.py):
- `ObsidianDialect`: Parses `[[wikilinks|alias]]`, embedded media (`![[img.png]]`), hashtags (`#tag`), and YAML frontmatter.
- `CommonMarkDialect`: Parses standard Markdown links (`[text](url.md)`).
- Auto-detection selects the dialect based on vault configuration (e.g., presence of `.obsidian/`).

---

## ⚡ Incremental Delta Change Detection

Ingestion compares disk state against database state to avoid redundant work:

1. **LadybugDB Delta (SHA-256):** Computes note content hashes. If `file_hash == n.hash` and `not n.is_unresolved`, graph updates are skipped.
2. **LanceDB Delta (mtime):** Compares filesystem modification timestamps against chunk metadata. Unchanged notes bypass re-embedding.

**Target Control:**
```bash
pkmrag ingest /path/to/vault --target all     # Ingest graph + vectors
pkmrag ingest /path/to/vault --target graph   # Ingest LadybugDB graph only
pkmrag ingest /path/to/vault --target vector  # Ingest LanceDB vectors only
```

---

## 👻 Ghost Note Reconciliation Lifecycle

1. **Unresolved Link:** When note `A` links to `[[Future Note]]` that does not exist on disk, Orbit creates a ghost node:
   ```cypher
   MERGE (b:Note {path: 'Future Note.md'})
   ON CREATE SET b.is_unresolved = true;
   ```
2. **Realization:** When `Future Note.md` is subsequently created on disk:
   - Orbit detects the title matches an existing ghost note.
   - Migrates incoming `[:LINKS_TO]` relationships to the new real note vertex.
   - Deletes the ghost node, preserving graph connectivity.
