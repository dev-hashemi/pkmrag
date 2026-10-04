---
title: FastMCP Server Integration
tags: [project/orbit/mcp, protocol/mcp]
aliases: [Orbit MCP]
---
# FastMCP Server Integration

Exposes Orbit graph traversals and semantic search to agentic reasoning tools like Claude Code and Cursor.

## Tool Schema
- `query_vault(query: str, hops: int = 1)`
- `read_note(path: str)`
- `find_bridges(note_a: str, note_b: str)`

See specifications in [[Model Context Protocol]].
Builds directly on [[Projects/Orbit Core]].

Self section reference: [[#Tool Schema]].
#mcp/tools #integration
