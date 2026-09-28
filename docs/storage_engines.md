# Dual In-Process Storage Engines

Project Orbit deliberately avoids client-server databases (e.g., Neo4j, Milvus, Qdrant). Instead, it couples two specialized, embedded, zero-daemon storage engines within a single Python runtime:
1. **LadybugDB:** In-process C++ property graph executing OpenCypher queries for topological graph traversal.
2. **LanceDB:** In-process Apache Arrow columnar storage providing vector ANN and BM25 full-text search.

---

## 🐞 LadybugDB: The Property Graph Engine

LadybugDB stores notes, tags, folders, and explicit human wikilinks as a typed, directed multigraph with properties.

### Storage Location
```
<vault>/.orbit/graph/
└── orbit.ladybug/     # LadybugDB native storage files & WAL
```

### Data Definition Language (DDL) Schema

The schema is declared and applied during database initialization ([`schema.py`](file:///home/ali/projects/my/project-orbit/src/orbit/graph/schema.py)):

#### Node Tables
```cypher
-- Notes / Documents
CREATE NODE TABLE Note (
    path STRING,
    title STRING,
    hash STRING,
    mtime DOUBLE,
    is_unresolved BOOLEAN,
    PRIMARY KEY (path)
);

-- Vault Folders
CREATE NODE TABLE Folder (
    path STRING,
    name STRING,
    PRIMARY KEY (path)
);

-- Vault Tags (#tag/subtag)
CREATE NODE TABLE Tag (
    name STRING,
    PRIMARY KEY (name)
);
```

#### Relationship Tables
```cypher
-- Explicit Note-to-Note Links
CREATE REL TABLE LINKS_TO (
    FROM Note TO Note,
    anchor STRING,
    alias STRING,
    is_embed BOOLEAN
);

-- Note Tag Membership
CREATE REL TABLE TAGGED_WITH (
    FROM Note TO Tag
);

-- Directory Containment
CREATE REL TABLE NOTE_CONTAINED_IN (
    FROM Note TO Folder
);

CREATE REL TABLE FOLDER_CONTAINED_IN (
    FROM Folder TO Folder
);
```

### Topological Graph Traversal Queries

Orbit executes OpenCypher queries via [`traversal.py`](file:///home/ali/projects/my/project-orbit/src/orbit/graph/traversal.py) to calculate undirected topological neighborhood distances:

#### 1-Hop Neighbor Expansion (Direct Link or Inbound Backlink)
```cypher
MATCH (f:Note {path: $p})-[r:LINKS_TO]-(nbr:Note)
RETURN DISTINCT nbr.path;
```

#### 2-Hop Neighbor Expansion (Secondary Associative Links)
```cypher
MATCH (f:Note {path: $p})-[*2..2]-(nbr:Note)
WHERE nbr.path <> $p
RETURN DISTINCT nbr.path;
```

Notice the undirected edge syntax `-[r:LINKS_TO]-`. In knowledge vaults, inbound backlinks and outbound forward links indicate conceptual closeness regardless of edge directionality.

---

## ⚡ LanceDB: The Columnar Vector & BM25 Engine

LanceDB provides high-performance dense vector search and inverted full-text search directly on disk using the Lance columnar data format (built on Apache Arrow).

### Storage Location
```
<vault>/.orbit/vectors/
└── chunks.lance/      # Lance columnar dataset & inverted FTS index
```

### PyArrow Table Schema

The `chunks` table enforces the following schema ([`vector_store.py`](file:///home/ali/projects/my/project-orbit/src/orbit/search/vector_store.py)):

| Column Name | Arrow Type | Description |
| :--- | :--- | :--- |
| `id` | `pa.string()` | Deterministic chunk identifier (`notes/api.md#chunk_0`) |
| `note_path` | `pa.string()` | Relative POSIX path to source markdown file |
| `note_title` | `pa.string()` | Stem or title of the note |
| `heading` | `pa.string()` | Hierarchical breadcrumbs (`# Arch > ## Storage`) |
| `text` | `pa.string()` | Full text of chunk including heading prefix |
| `vector` | `pa.list_(pa.float32(), 384)` | 384-dimensional dense embedding vector |
| `chunk_index`| `pa.int32()` | Zero-indexed chunk position in note |
| `mtime` | `pa.float64()` | File modification timestamp for change tracking |

### Dual Retrieval Mechanics

#### 1. Dense Semantic Search (ANN)
Given a query vector $\vec{q} \in \mathbb{R}^{384}$, LanceDB scans the indexed vector dataset using L2 Euclidean distance:
$$D(\vec{q}, \vec{v}) = \|\vec{q} - \vec{v}\|_2 = \sqrt{\sum_{i=1}^{384} (q_i - v_i)^2}$$
Smaller distance values indicate higher semantic proximity.

#### 2. Sparse Lexical Search (BM25 FTS)
LanceDB builds an inverted full-text search index directly on the `text` column:
```python
table.create_index("text", config=FTS(), replace=True)
```
Queries execute native BM25 scoring:
$$\text{BM25}(D, Q) = \sum_{t \in Q} \text{IDF}(t) \cdot \frac{f(t, D) \cdot (k_1 + 1)}{f(t, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$
Higher scores indicate stronger keyword frequency and rarity.

### Incremental Updates & Atomicity
When a note is modified, Orbit avoids expensive full-table rewrites:
1. Purges existing chunks for the note:
   ```python
   table.delete(f"note_path = '{escaped_path}'")
   ```
2. Appends new chunks with freshly computed vectors and timestamps:
   ```python
   table.add(records)
   ```
3. Refreshes the inverted FTS index in-place.
