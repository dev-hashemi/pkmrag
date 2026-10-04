---
title: Project Orbit Core
aliases: [Orbit, Orbit Engine]
tags:
  - project/orbit
  - type/core
  - status/active
---
# Project Orbit Core

Orbit is an in-process, local-first Hybrid GraphRAG retrieval engine and MCP server designed for linked Markdown vaults.

## Architecture
Orbit fuses two retrieval modalities:
1. Explicit structural knowledge via [[Concepts/Property Graphs#Cypher Queries|Property Graphs]] in LadybugDB.
2. High-dimensional semantic vectors and lexical search managed by [[Storage Layer]].

Key principles follow modern [[Research/GraphRAG Paradigms]].
Embedded diagram: ![[Architecture Blueprint.png]].

## Code Example
```python
# Parser test - these must be ignored by graph extractor:
# [[IgnoredWikilinkInCode]]
# tag: #not-a-real-tag
def test_fn():
    return "orbit"
```

## Related
- Subsystem: [[FastMCP Server]]
- Daily note: [[Daily/2026-09-27]]
