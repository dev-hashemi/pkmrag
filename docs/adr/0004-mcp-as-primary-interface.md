# 4. Model Context Protocol (MCP) as Primary Interface

- **Status:** Accepted
- **Date:** 2026-09-28
- **Deciders:** Orbit Core Team

---

## Context
Personal knowledge retrieval engines often attempt to build custom user interfaces:
- Web apps (React / Next.js frontends).
- Obsidian desktop plugins with custom chat sidebars.
- Electron wrapper apps.

Developing and maintaining custom chat and graph rendering frontends creates immense maintenance overhead, while competing with frontier agentic coding and reasoning environments (e.g., Cursor, Claude Code, Windsurf, Claude Desktop).

---

## Decision
Orbit exposes its capabilities primarily as a **Model Context Protocol (MCP) server**:
- Transport: Standard input/output (stdio) and Server-Sent Events (SSE).
- Interface: Deterministic tools (`query_vault`, `read_note`, `find_bridges`) and graph resources.
- CLI serves as a local developer inspection tool (`pkmrag search`, `pkmrag ingest`, `pkmrag doctor`).
- No custom web UI or frontend chat application.

---

## Consequences

### Positive
- Keeps Orbit lean, focused entirely on indexing and retrieval performance.
- Seamless, zero-glue integration into frontier AI agent tools.
- Decouples UI evolution from backend retrieval logic.

### Negative
- Requires users to have an MCP-compatible client (Claude Desktop, Cursor, etc.) for agentic interaction.
