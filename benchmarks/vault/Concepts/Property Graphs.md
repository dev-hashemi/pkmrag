---
title: Property Graph Data Model
tags: [concept/graph, database/cypher]
---
# Property Graph Data Model

## Overview
A property graph consists of vertices (nodes) and directed relationships (edges), both of which can possess arbitrary key-value properties.

## Cypher Queries
openCypher provides declarative pattern matching:
```cypher
MATCH (a:Note)-[r:LINKS_TO]->(b:Note)
WHERE b.is_unresolved = false
RETURN a.title, r.anchor, b.title;
```

Used by [[Projects/Orbit Core]] and discussed in [[Research/GraphRAG Paradigms]].
#graph-theory
