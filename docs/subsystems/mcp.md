# Subsystem: Model Context Protocol (MCP) Server

Project Orbit exposes its 3-tier Hybrid GraphRAG engine via an embedded Model Context Protocol (MCP) server over `stdio`. This allows Claude Code, Cursor, and Claude Desktop to autonomously search, fetch, and explore linked Markdown vaults.

---

## 🛰️ Architecture & Stdio Safety

In `stdio` transport mode, standard input and output streams are strictly reserved for JSON-RPC 2.0 messages:

$$\text{Client} \underset{\text{stdio}}{\overset{\text{JSON-RPC}}{\rightleftharpoons}} \text{Orbit MCP Server} \longrightarrow \begin{cases} \text{SearchService (LanceDB + FastEmbed + BM25)} \\ \text{GraphStore (LadybugDB Cypher)} \\ \text{Sandboxed Vault Filesystem} \end{cases}$$

- **Stdio Stream Isolation**: All Orbit logging, Python warnings, and third-party outputs route exclusively to `sys.stderr` to prevent JSON-RPC stream corruption.
- **Read-Only Concurrency**: Underlying LadybugDB and LanceDB instances are opened in `read_only=True` mode, preventing database lock collisions with concurrent CLI commands.

---

## 🛠️ Exposed Tools

| Tool | Purpose | Primary Backend |
| :--- | :--- | :--- |
| `query_vault(query, near?, mode?, limit?)` | Semantic + BM25 keyword search with graph proximity boost | LanceDB + FastEmbed + LadybugDB |
| `read_note(note_path, max_chars?, offset?)` | Fetch full note content with path traversal containment | Sandboxed filesystem |
| `get_note_context(note_path)` | Inspect incoming backlinks, outgoing citations, tags, and 2-hop cluster | LadybugDB graph queries |
| `find_bridges(source_note, target_note)` | Find shortest wikilink connection path across the vault | LadybugDB `SHORTEST` path |
| `vault_overview(limit?)` | Bird's-eye view: total notes, links, tags, and central hub notes | LadybugDB in-degree ranking |

---

## ⚙️ Client Configuration

Run `orbit mcp-config <vault_path>` to generate the configuration block for your client.

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "orbit": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/project-orbit",
        "run",
        "orbit",
        "serve",
        "/absolute/path/to/your/vault"
      ]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
Add an entry with type `"command"`, command `"uv"`, and args matching the above.

---

## 🧪 Testing

```bash
uv run pytest tests/test_mcp_tools.py tests/test_mcp_server.py
```
