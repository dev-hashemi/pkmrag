---
title: PKMRAG Core
aliases: [PKMRAG, PKMRAG Engine]
tags:
  - project/pkmrag
  - type/core
  - status/active
---
# PKMRAG Core

PKMRAG is an in-process, local-first Hybrid GraphRAG retrieval engine and MCP server designed for linked Markdown vaults.

## Architecture
PKMRAG fuses two retrieval modalities:
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
    return "pkmrag"
```

## Related
- Subsystem: [[FastMCP Server]]
- Daily note: [[Daily/2026-09-27]]
