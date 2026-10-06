# HTTP & SSE Server Transport

Project Orbit exposes its Hybrid GraphRAG retrieval engine and knowledge graph through a dual-protocol HTTP/SSE daemon. This transport enables web applications, Electron desktop clients (such as the Obsidian desktop plugin), and external HTTP agents to consume Orbit services over a single local network port.

---

## 1. Dual Protocol Plane on Port 3747

Orbit runs an asynchronous Starlette/Uvicorn server hosting two distinct API planes concurrently on port `3747`:

```
                           ┌────────────────────────────────────────────────────────┐
                           │               Project Orbit HTTP Server                │
                           │                 (Default: 127.0.0.1:3747)              │
                           └────────────────────────────────────────────────────────┘
                                      │                                 │
           ┌──────────────────────────┴────────┐       ┌────────────────┴────────────────────────┐
           ▼                                   ▼       ▼                                         ▼
   [MCP SSE Protocol]                 [Public Health]  [Obsidian & Client REST API]      [Reactive SSE]
   • GET  /sse                        • GET /health    • GET  /api/v1/context             • GET /api/v1/events
   • POST /messages/?session_id=...                    • GET  /api/v1/gaps
                                                       • POST /api/v1/search
                                                       • POST /api/v1/reindex
                                                       • POST /api/v1/sync
                                                       • GET  /api/v1/overview
```

1. **Model Context Protocol (MCP) SSE Transport:**
   - Standard `/sse` endpoint opening an EventSource stream emitting session URLs.
   - Standard `/messages/` endpoint receiving JSON-RPC tool calls from Claude Desktop, Cursor, or MCP clients.
2. **Ergonomic REST API:**
   - Structured JSON endpoints designed specifically for direct consumption by frontend panels (e.g., the Obsidian "Orbit Insights" sidebar) without requiring MCP client wrappers.
3. **Reactive Event Stream (`/api/v1/events`):**
   - Push-based Server-Sent Events broadcasting live reindexing and sync notifications to keep connected views fresh.

---

## 2. CLI Usage

### 2.1 Starting the Server
```bash
# Start HTTP/SSE server (generates or reads .orbit/server_token)
uv run pkmrag serve /path/to/vault --transport http --port 3747

# Start with an explicit authentication token
uv run pkmrag serve /path/to/vault --transport http --token my_secret_token

# Start in local testing mode with authentication disabled
uv run pkmrag serve /path/to/vault --transport http --no-auth
```

### 2.2 Generating MCP Client Configuration
```bash
# Generate stdio configuration
uv run pkmrag mcp-config /path/to/vault

# Generate SSE configuration with auto-resolved Bearer token
uv run pkmrag mcp-config /path/to/vault --transport sse --port 3747
```

---

## 3. Security & Authentication

### 3.1 Loopback Binding by Default
To defend against browser-based DNS rebinding attacks, Orbit binds strictly to `127.0.0.1` by default.

### 3.2 Vault Token File Persistence
When started without an explicit token:
1. Orbit generates a cryptographically secure 32-character hex token (`secrets.token_hex(16)`).
2. Orbit writes the token to `<vault>/.orbit/server_token` with restricted owner-only permissions (`0o600`).
3. Local applications (like the Obsidian plugin running inside the vault) can auto-discover this token from disk for **zero-configuration authentication**.

### 3.3 Accepted Authentication Methods
Non-public endpoints (`/api/*`, `/sse`, `/messages/*`) require authentication via any of:
- `Authorization: Bearer <token>`
- `X-Orbit-Token: <token>`
- Query parameter `?token=<token>` (required for browser/Electron `EventSource` which cannot send custom HTTP headers).

### 3.4 CORS Origins
The server whitelists local origins by default:
- `app://obsidian.md`
- `capacitor://localhost`
- `http://localhost`
- `http://127.0.0.1`

---

## 4. REST API Reference

### `GET /health` (Public)
Health check probe for connection testing without authentication.
```json
{
  "status": "healthy",
  "version": "0.9.0",
  "vault": "notes",
  "vault_path": "/home/user/notes",
  "transport": "sse",
  "auth_enabled": true
}
```

### `GET /api/v1/context?note_path=<path>`
Returns the note's structural graph context including tags, forward links, backlinks, 2-hop clusters, and AI-inferred relationships.
```json
{
  "path": "Distributed Locking.md",
  "title": "Distributed Locking",
  "tags": ["#distributed", "#locks"],
  "outgoing_links": ["Consensus.md"],
  "backlinks": ["Storage Layer.md"],
  "neighbors_2hop": ["Paxos.md", "Raft.md"],
  "inferred_relationships": [
    {
      "source_path": "Distributed Locking.md",
      "target_path": "CAP Theorem.md",
      "rel_type": "CONTRADICTS",
      "confidence": 0.83,
      "reason": "Claims strong consistency with AP mode",
      "direction": "source_to_target"
    }
  ]
}
```

### `GET /api/v1/gaps?threshold=0.80&limit=10&note_path=<path>`
Returns unlinked candidate pairs exhibiting high vector similarity. If `note_path` is specified, filters candidates involving that note.

### `POST /api/v1/search`
Executes hybrid vector + BM25 search with graph proximity boosting.
```json
{
  "query": "distributed locks",
  "near": "Consensus.md",
  "mode": "hybrid",
  "limit": 5
}
```

### `POST /api/v1/reindex`
Incrementally re-indexes a single note after editing in Obsidian, evicts stale query caches, and broadcasts a `reindex` event.
```json
{
  "note_path": "Distributed Locking.md"
}
```

### `POST /api/v1/sync`
Performs delta synchronization across all modified vault files and broadcasts a `sync` event.

### `GET /api/v1/events`
Server-Sent Events stream yielding real-time updates when notes are re-indexed or synced:
```text
event: reindex
data: {"note_path": "Distributed Locking.md", "status": "ok"}
```
