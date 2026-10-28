# PKMRAG for Obsidian

> Local-first Hybrid GraphRAG insights, missing link discovery, and contradiction warnings for Obsidian.

PKMRAG is a companion plugin that connects your Obsidian vault to the local [PKMRAG](https://github.com/dev-hashemi/pkmrag) engine. It brings semantic understanding and deterministic graph intelligence into your daily note-taking without sending your notes to third-party cloud services.

---

## Features

### 1. Insights Sidebar
* **Missing Links (Semantic Gaps):** Surfaces unlinked note pairs exhibiting deep semantic overlap that are unconnected or distant in your graph.
* **Evidence & Passage Citations:** Shows why two notes are semantically related, displaying heading breadcrumbs and clickable excerpts from both notes.
* **1-Click Link Insertion:** Clicking **Add to Related** automatically appends `[[Target Note]]` under the active note's `## Related` section (creating it if needed) using atomic vault updates.
* **Contradiction Warnings & Inferences:** Amber alert cards flag potential contradictions or conceptual conflicts detected between notes in your vault.
* **Structural Context:** Interactive exploration of backlinks, outgoing links, and 2-hop clusters.

### 2. Proximity Concept Explorer
* Search your knowledge base anchored to your current active note.
* Combines dense vector retrieval with graph proximity boosting (`⚡ ×1.25 · 1 hop`) to rank notes that are both semantically and structurally relevant.
* Insert direct heading references (`[[Note#Heading]]`) at your editor cursor with one click.

### 3. Ambient Heading Indicators
* Subtle, unobtrusive CodeMirror 6 inline indicators next to markdown headings:
  * `🔗 N` indicates *N* unlinked semantic recommendations for the note.
  * `⚠️ N` flags detected contradictions with other notes in the vault.
* Clicking an indicator smoothly focuses the Insights sidebar.

### 4. Background Sync & Governance
* **Incremental Reindexing:** Automatically updates the graph and vector index on save (debounced 1500ms) with `< 40ms` latency.
* **Persistent Memory:** Dismissed suggestions are recorded so rejected recommendations won't recur.

---

## Prerequisites & Installation

The plugin relies on the local **PKMRAG Core Engine** running on your desktop.

### 1. Install Core Engine
Run in your terminal:
```bash
# Recommended (fast, isolated):
uv tool install pkmrag

# Or with pipx:
pipx install pkmrag
```

### 2. Enable Plugin in Obsidian
1. In Obsidian, go to **Settings** → **Community Plugins**.
2. Search for **PKMRAG** and click **Install**, then **Enable**.
3. Open the Insights panel by clicking the ribbon icon or running `PKMRAG: Open Insights Sidebar` from the command palette.
4. If the engine is not running yet, the built-in Setup Wizard will detect your environment and start the engine with one click.

---

## Disclosures & Privacy

* **Localhost Daemon:** The plugin communicates exclusively with the local PKMRAG engine running locally on your computer at `http://127.0.0.1:3747`. Vault contents, graph indices, and embeddings remain strictly on your local machine.
* **AI & LLM Services:** AI gap discovery and contradiction detection can be configured in Plugin Settings to run either **100% offline via local Ollama** or using your own API key with OpenAI / custom OpenAI-compatible endpoints. The plugin never transmits data to any other third-party servers.
* **No Telemetry:** PKMRAG contains zero client-side tracking, analytics, or telemetry identifiers.

---

## Commands

* `Open Insights Sidebar` — Reveals the PKMRAG Insights panel.
* `Refresh Insights for Active Note` — Refreshes suggestions and graph context.
* `Run AI Gap Discovery` — Triggers background relationship and contradiction detection.
* `Rebuild Vault Index (Full)` — Re-indexes all vault notes into the local graph and vector store.
* `Sync Vault Index (Incremental)` — Syncs modified notes.
* `Toggle Inline Heading Indicators` — Toggles ambient heading badges.
* `Restart Local Engine` — Restarts the desktop background daemon process.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
