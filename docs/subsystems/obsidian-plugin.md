# Obsidian Desktop Plugin (`pkmrag`)

The PKMRAG plugin is a lightweight, local-first companion plugin for [Obsidian](https://obsidian.md). It connects Obsidian to the PKMRAG background daemon over HTTP/SSE (`http://127.0.0.1:3747`), surfacing AI-discovered missing connections, contradiction warnings, and structural graph context directly inside your editor.

---

## 1. Core Features

### 1.1 "Orbit Insights" Sidebar Panel
- **Active Note Context:** Automatically synchronizes with whatever markdown note is active in Obsidian.
- **Missing Links Section (Semantic Gaps):** Displays unlinked note pairs exhibiting high cosine similarity and graph distance $\ge 2$.
  - **Human-in-the-Loop Insertion:** Clicking `[+ Link]` writes `[[Target Note]]` directly at the editor cursor location (or appends to `## Related Notes` if no cursor is active). Orbit *never* mutates notes silently.
  - **Session Dismissal:** Clicking `[Dismiss]` hides recommendations for the active editing session.
- **Contradiction Warnings & Inferences:**
  - Distinct amber warning cards for notes classified with `CONTRADICTS` relationships, citing the LLM rationale excerpt.
  - Informational badges for `EXTENDS`, `PREREQUISITE_FOR`, and `SUPPORTS`.
- **Structural Graph Context:**
  - Tag chips and backlink lists for immediate topological awareness without switching to graph view.

### 1.2 Zero-Config Vault Token Authentication
When opened inside a vault indexed by Orbit, the plugin automatically reads `<vault>/.orbit/server_token` using Obsidian's Vault adapter (`app.vault.adapter.read`). No manual copy-pasting of API keys is needed.

### 1.3 Debounced Background Sync on Save
The plugin intercepts Obsidian's `vault.on('modify')` event with a **1500ms debounce timer**. When you pause typing, Orbit incrementally reindexes the modified note into LadybugDB and LanceDB in `< 40ms`, invalidating stale query caches without editor stutter.

### 1.4 Live Reactive Event Stream
The plugin subscribes to Orbit's Server-Sent Events stream (`GET /api/v1/events`). When an external tool or CLI run updates the vault index, open sidebar tabs automatically refresh.

### 1.5 CodeMirror 6 Inline Heading Indicators
- **Unobtrusive Ambient Awareness:** Lightweight CodeMirror 6 `ViewPlugin` renders subtle indicators next to document headings:
  - `🔗 N` indicates *N* unlinked semantic link recommendations available for this note.
  - `⚠️` alerts to detected logical contradictions or conflicts with other notes in the vault.
- **Direct Interaction:** Clicking any indicator smoothly reveals the Orbit Insights sidebar panel and refreshes live recommendations for the active note. Configurable via plugin settings.

### 1.6 Proximity Search Drawer (Concept Explorer)
- **Anchored Graph Search:** Accessible via the `🔍 Explore Concepts` drawer in the sidebar or command palette (`Orbit: Proximity Search & Reference`).
- **Context-Aware Fusion:** Dispatches hybrid semantic and graph traversal anchored to the active note (`POST /api/v1/search` with `--near <note>`), returning dense/sparse fusion scores and textual snippets.
- **1-Click Reference Insertion:** Inserts a markdown link or quote reference to the target note directly at your current cursor position.

### 1.7 Knowledge Governance & Persistent Dismissal Memory
- **Persistent Feedback:** Dismissed suggestions are recorded in plugin data (`dismissedSuggestions` in `data.json`) keyed by `source_path` and `target_title`, preventing dismissed links from recurring across sessions.
- **Transparent Recovery:** A collapsible "Dismissed Suggestions" drawer in the sidebar displays previously dismissed items with single-click `[Restore]` buttons.
- **Global Reset:** A "Reset All Dismissed Suggestions" action in Plugin Settings lets users flush negative feedback when restructuring their vault.

### 1.8 Zero-Terminal Background Daemon Management
- **Automatic Lifecycle:** On desktop, the plugin automatically spawns and manages the PKMRAG daemon process on startup and gracefully stops it on shutdown.
- **Process Controls:** Settings provide manual Start, Stop, and Restart controls along with live PID / status feedback.

### 1.9 In-App AI Discovery & Indexing
- **Header Action:** The `⚡ Discover` button in the insights sidebar header triggers background relationship inference.
- **Live Event Streaming:** Subscribes to SSE progress updates and automatically refreshes newly inferred relationships without manual CLI intervention.
- **Full Vault Rebuild:** Trigger full rebuilds directly from Settings or the Command Palette.

### 1.10 Custom LLM & Embedding Model Configuration
- **Model & Provider Independence:** Configure OpenAI, local Ollama, or any custom OpenAI-compatible endpoint (Groq, DeepSeek, vLLM, LM Studio) directly in Obsidian Settings.
- **Interactive Verification:** Test LLM credentials and measured response latency with a single click.
- **Embedding Model Setting:** View or change the dense embedding model (`BAAI/bge-small-en-v1.5` by default) with automatic vector reindexing guidance.
- **Per-Vault Persistence:** Automatically writes to `<vault>/.pkmrag/config.json`, keeping vault-specific preferences in sync across devices.

### 1.11 Interactive Setup Wizard for First-Time Users
- **Auto-Detection:** When the plugin is enabled, it checks if `pkmrag` is installed on the host machine (`~/.local/bin`, `~/.cargo/bin`, `/usr/local/bin`, or PATH).
- **Onboarding Card:** If the core engine is missing, the sidebar renders a 2-step setup wizard:
  - Step 1: Copy-to-clipboard command (`pipx install pkmrag` or `uv tool install pkmrag`).
  - Step 2: "Check Installation & Start" button that verifies detection and launches the daemon automatically.
- **Status Bar Integration:** Shows `⚪ PKMRAG: Setup Required` until the engine binary is installed.

### 1.12 Graceful Offline Recovery Panel
- **Helpful Status Feedback:** If the binary is installed but the daemon cannot be reached, the sidebar displays an offline card with status diagnostics.
- **Click-to-Copy CLI Fallback:** One-click copy for `pkmrag serve . -t http --port 3747`.
- **Immediate Reconnection:** "Retry Connection" button tests connectivity and auto-populates insights once the daemon is up.

---

## 2. Installation & Quickstart

### 2.1 Install PKMRAG Core Engine
```bash
# Recommended: Isolated global installation
pipx install pkmrag
# or
uv tool install pkmrag
```

### 2.2 Install Companion Plugin into Vault
```bash
# Install and enable plugin in your vault:
pkmrag install-plugin /path/to/my-vault

# For plugin development:
pkmrag install-plugin /path/to/my-vault --symlink
```

Alternatively, you can manually copy or symlink the build files:
```bash
mkdir -p "/path/to/my-vault/.obsidian/plugins/pkmrag"
cp plugins/obsidian/manifest.json \
   plugins/obsidian/main.js \
   plugins/obsidian/styles.css \
   "/path/to/my-vault/.obsidian/plugins/pkmrag/"
```

In Obsidian:
1. Open **Settings** → **Community Plugins**.
2. Enable Community Plugins (if not already enabled).
3. Verify **PKMRAG** is toggled on.
4. Click the PKMRAG ribbon icon (`assets/obsidian-ribbon-icon.svg`) on the left bar to open the **PKMRAG Insights** sidebar.


---

## 3. Development & Building

The plugin source code lives under `plugins/obsidian/`:

```
plugins/obsidian/
  src/
    client.ts        # Typed HTTP/SSE API client
    extension.ts     # CodeMirror 6 inline heading indicator extension
    main.ts          # Plugin lifecycle & event debouncers
    settings.ts      # Settings tab with connection test & governance
    types.ts         # TypeScript interfaces matching Orbit REST API
    view.ts          # "Orbit Insights" ItemView sidebar panel
    view_offline.ts  # Friendly offline recovery card & onboarding
    view_search.ts   # Proximity concept explorer & reference insertion
  tests/
    client.test.ts   # Client and storage unit tests
  icon.svg           # Community plugin icon (100x100 monochrome SVG)
  manifest.json      # Obsidian metadata
  package.json       # Node package configuration
  tsconfig.json      # TypeScript compiler options
  esbuild.config.mjs # Bundler script emitting main.js
  styles.css         # UI styles using Obsidian native CSS variables
```

### Build Commands
```bash
cd plugins/obsidian

# Install dependencies
npm install

# Typecheck
npm run typecheck

# Run unit tests
npm test

# Build bundled main.js
npm run build
```
