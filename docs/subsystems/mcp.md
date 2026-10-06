# Subsystem: Model Context Protocol (MCP) Server

Project Orbit exposes its 3-tier Hybrid GraphRAG engine via an embedded Model Context Protocol (MCP) server over `stdio`. This allows Claude Code, Cursor, and Claude Desktop to autonomously search, fetch, and explore linked Markdown vaults.

---

## 🛰️ Architecture & Stdio Safety

In `stdio` transport mode, standard input and output streams are strictly reserved for JSON-RPC 2.0 messages:

$$\text{Client} \underset{\text{stdio}}{\overset{\text{JSON-RPC}}{\rightleftharpoons}} \text{Orbit MCP Server} \longrightarrow \begin{cases} \text{SearchService (LanceDB + FastEmbed + BM25)} \\ \text{GraphStore (LadybugDB Cypher)} \\ \text{Sandboxed Vault Filesystem} \end{cases}$$

- **Stdio Stream Isolation**: All Orbit logging, Python warnings, and third-party outputs route exclusively to `sys.stderr` to prevent JSON-RPC stream corruption.
- **Unified Store & Concurrency Lock**: Graph operations run on a shared Read-Write `GraphStore` guarded by an in-process write mutex (`threading.Lock`), ensuring instant visibility of incremental updates without transaction collisions.

---

## 🛠️ Exposed Tools

| Tool | Purpose | Primary Backend |
| :--- | :--- | :--- |
| `query_vault(query, near?, mode?, limit?, folder?, tags?)` | Hybrid search with graph boost, folder prefix, and tag filtering | LanceDB + FastEmbed + LadybugDB + L1 Cache |
| `read_note(note_path, max_chars?, offset?)` | Fetch note content enriched with graph context (tags, links, backlinks) | Filesystem + LadybugDB |
| `list_notes(folder?, pattern?, limit?)` | Browse notes with folder filtering and filename pattern matching | Filesystem glob |
| `list_tags(limit?)` | List all unique vault tags ranked by frequency | LadybugDB `Tag` nodes |
| `search_by_tag(tag, limit?)` | Find all notes tagged with a specific tag | LadybugDB `TAGGED_WITH` |
| `get_outline(note_path)` | Extract heading tree and line numbers for large notes | Filesystem heading parser |
| `get_note_context(note_path)` | Inspect incoming backlinks, outgoing citations, tags, and 2-hop cluster | LadybugDB graph queries |
| `find_bridges(source_note, target_note)` | Find shortest wikilink connection path across the vault | LadybugDB `SHORTEST` path |
| `vault_overview(limit?)` | Bird's-eye view: total notes, links, tags, and central hub notes | LadybugDB in-degree ranking |
| `discover_gaps(threshold?, limit?)` | Find unlinked note pairs with high vector similarity | LanceDB ANN + LadybugDB distance |
| `reindex_note(note_path)` | Incrementally re-index a single note after external edits (< 40ms) | LadybugDB + LanceDB + Cache Invalidation |
| `sync_vault()` | Delta sync all modified or added notes across the vault | LadybugDB + LanceDB + Cache Invalidation |


---

## ⚙️ Client Configuration

Run `pkmrag mcp-config <vault_path>` to generate the configuration block for your client.

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

### OpenCode CLI (`opencode`)
Add Orbit with a single native command:
```bash
opencode mcp add pkmrag -- uv --directory /absolute/path/to/project-orbit run pkmrag serve /absolute/path/to/your/vault
```
Verify connection status:
```bash
opencode mcp list
# Displays: ● ✓ orbit connected
```

---

## 🧪 Testing

```bash
uv run pytest tests/test_mcp_tools.py tests/test_mcp_server.py
```
