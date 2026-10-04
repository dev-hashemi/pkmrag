---
title: In-Process Storage Layer
tags: [storage/in-process, database/embedded]
---
# In-Process Storage Layer

Zero-daemon, in-memory and local file-backed storage engines.

## Components
- Graph Engine: [[Property Graphs]] via LadybugDB C++ bindings.
- Vector Engine: [[Vector Retrieval]] via LanceDB and Apache Arrow.
- Fusion Engine: [[Lexical BM25]] fused with vector similarities.

## Planned Explorations
- Distributed sync: [[Distributed Cluster Spec]]
#performance/low-latency
