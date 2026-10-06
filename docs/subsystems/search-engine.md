# Subsystem: Search Engine

The search engine couples dense vector similarity search with sparse lexical BM25 full-text search using embedded **LanceDB** and Apache Arrow.

---

## 💾 Storage & Lifecycle
- **Implementation:** [`src/pkmrag/search/vector_store.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/search/vector_store.py) & [`src/pkmrag/search/embedder.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/search/embedder.py)
- **Path:** `<vault>/.orbit/vectors/chunks.lance`
- **Model:** `BAAI/bge-small-en-v1.5` (384 dimensions, ONNX Runtime CPU via `fastembed`).

---

## 📋 Apache Arrow Table Schema

The `chunks` table enforces the following schema:

| Column | Arrow Type | Description |
| :--- | :--- | :--- |
| `id` | `pa.string()` | Deterministic chunk ID (`notes/api.md#chunk_0`) |
| `note_path` | `pa.string()` | Relative POSIX path |
| `note_title` | `pa.string()` | Document stem or title |
| `heading` | `pa.string()` | Heading lineage (`# Title > ## Section`) |
| `text` | `pa.string()` | Full chunk text with heading context |
| `vector` | `pa.list_(pa.float32(), 384)` | Dense embedding vector |
| `chunk_index`| `pa.int32()` | Zero-indexed chunk position |
| `mtime` | `pa.float64()` | File timestamp for delta tracking |

---

## 🔍 Retrieval Modalities

1. **Dense Semantic Search:** Scans 384-dimensional embeddings using L2 Euclidean distance:
   ```python
   table.search(query_vector).limit(limit).to_list()
   ```
2. **Sparse BM25 Search:** Inverted index constructed on the `text` column via LanceDB native FTS:
   ```python
   table.create_index("text", config=FTS(), replace=True)
   table.search(query_text, query_type="fts").limit(limit).to_list()
   ```

## 🔄 Atomic Updates
When a note changes:
1. `table.delete(f"note_path = '{note_path}'")`
2. `table.add(new_chunk_records)`
3. Native FTS index is updated in-place without table rebuilds.
