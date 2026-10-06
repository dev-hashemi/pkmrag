# Subsystem: Graph Engine

The graph engine manages the deterministic topological backbone of notes, tags, folders, and explicit human links using embedded **LadybugDB**.

---

## 💾 Storage & Lifecycle
- **Implementation:** [`src/pkmrag/graph/store.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/graph/store.py) & [`src/pkmrag/graph/traversal.py`](file:///home/ali/projects/my/project-orbit/src/pkmrag/graph/traversal.py)
- **Path:** `<vault>/.orbit/graph/orbit.ladybug`
- **Execution:** In-process C++ binding via `ladybug.Database` and `ladybug.Connection`. Zero network daemons.

---

## 📋 OpenCypher Schema (DDL)

```cypher
-- Nodes
CREATE NODE TABLE Note (
    path STRING,
    title STRING,
    hash STRING,
    mtime DOUBLE,
    is_unresolved BOOLEAN,
    PRIMARY KEY (path)
);

CREATE NODE TABLE Folder (
    path STRING,
    name STRING,
    PRIMARY KEY (path)
);

CREATE NODE TABLE Tag (
    name STRING,
    PRIMARY KEY (name)
);

-- Relationships
CREATE REL TABLE LINKS_TO (FROM Note TO Note, anchor STRING, alias STRING, is_embed BOOLEAN);
CREATE REL TABLE TAGGED_WITH (FROM Note TO Tag);
CREATE REL TABLE NOTE_CONTAINED_IN (FROM Note TO Folder);
CREATE REL TABLE FOLDER_CONTAINED_IN (FROM Folder TO Folder);
```

---

## 🔍 Undirected Neighborhood Traversal

In knowledge bases, relationships indicate conceptual closeness regardless of arrow direction. Orbit uses undirected pattern matching to expand graph neighborhoods:

### 1-Hop Expansion (Direct link or inbound backlink)
```cypher
MATCH (f:Note {path: $p})-[r:LINKS_TO]-(nbr:Note)
RETURN DISTINCT nbr.path;
```

### 2-Hop Expansion (Secondary associative links)
```cypher
MATCH (f:Note {path: $p})-[*2..2]-(nbr:Note)
WHERE nbr.path <> $p
RETURN DISTINCT nbr.path;
```
