---
title: GraphRAG Paradigms & Taxonomy
aliases: [GraphRAG, Knowledge Graphs in RAG]
tags: [research/graphrag, ai/nlp]
---
# GraphRAG Paradigms & Taxonomy

Comparison of heuristic, entity-extracted, and structural GraphRAG architectures.

## Naive Triple Extraction vs Structural Backbones
Traditional GraphRAG uses LLMs to extract entity triples `(subject, predicate, object)` from raw text chunks. This suffers from:
1. High token cost ($50-$200+ per vault)
2. Ontological drift and hallucination
3. Noisy entity resolution

In contrast, Orbit leverages the human-curated wikilink topology:
- Notes connect via [[Property Graphs]]
- Hybrid ranking connects via [[Hybrid Search]]
- Agent query plane via [[FastMCP Server]]

#methodology/ground-truth
