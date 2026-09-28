# 1. Embedded In-Process Storage Engines

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** Orbit Core Team

---

## Context
Traditional GraphRAG and vector search architectures rely on client-server infrastructure:
- Graph stores: Neo4j, Memgraph, or Neptune.
- Vector stores: Qdrant, Milvus, or Weaviate.

Running external daemons or Docker containers imposes significant barrier to entry, heavy resource consumption, and IPC network latency overhead for personal desktop knowledge bases.

---

## Decision
Orbit will exclusively utilize **embedded, zero-daemon, in-process storage engines**:
1. **LadybugDB:** In-process C++ graph database engine executing OpenCypher queries directly in the host process memory space.
2. **LanceDB:** In-process columnar vector and FTS engine backed by Apache Arrow and disk-persisted Lance datasets.

---

## Consequences

### Positive
- Zero deployment overhead (no Docker, no background services, no port conflicts).
- Sub-millisecond read/write latency via in-process memory sharing.
- Portable storage: Graph and vector databases are stored locally within `<vault>/.orbit/`.

### Negative
- Concurrent multi-process write access requires single-process locking.
- Vault scale bounded by single-machine filesystem and RAM constraints (sufficient for vaults with $< 100,000$ notes).
