---
title: FastMCP Server Integration
tags: [project/pkmrag/mcp, protocol/mcp]
aliases: [PKMRAG MCP]
---
# FastMCP Server Integration

Exposes PKMRAG graph traversals and semantic search to agentic reasoning tools like Claude Code and Cursor.

## Tool Schema
- `query_vault(query: str, hops: int = 1)`
- `read_note(path: str)`
- `find_bridges(note_a: str, note_b: str)`

See specifications in [[Model Context Protocol]].
Builds directly on [[Projects/PKMRAG Core]].

Self section reference: [[#Tool Schema]].
#mcp/tools #integration
