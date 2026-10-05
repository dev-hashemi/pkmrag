# Obsidian Desktop Plugin (`orbit-insights`)

The Orbit Insights plugin is a lightweight, local-first companion plugin for [Obsidian](https://obsidian.md). It connects Obsidian to the Project Orbit background daemon over HTTP/SSE (`http://127.0.0.1:3747`), surfacing AI-discovered missing connections, contradiction warnings, and structural graph context directly inside your editor.

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

---

## 2. Installation & Quickstart

### 2.1 Start Orbit HTTP Daemon
```bash
# In your terminal, start Orbit HTTP server for your vault:
uv run orbit serve /path/to/my-vault -t http --port 3747
```

### 2.2 Install Plugin into Vault
Copy or symlink the build artifacts to your vault's `.obsidian/plugins/` directory:
```bash
mkdir -p "/path/to/my-vault/.obsidian/plugins/orbit-insights"
cp plugins/obsidian/manifest.json \
   plugins/obsidian/main.js \
   plugins/obsidian/styles.css \
   "/path/to/my-vault/.obsidian/plugins/orbit-insights/"
```

In Obsidian:
1. Open **Settings** → **Community Plugins**.
2. Enable Community Plugins (if not already enabled).
3. Toggle on **Orbit Insights**.
4. Click the crosshair/satellite ribbon icon on the left bar to open the **Orbit Insights** sidebar.

---

## 3. Development & Building

The plugin source code lives under `plugins/obsidian/`:

```
plugins/obsidian/
  src/
    client.ts        # Typed HTTP/SSE API client
    main.ts          # Plugin lifecycle & event debouncers
    settings.ts      # Settings tab with connection test
    types.ts         # TypeScript interfaces matching Orbit REST API
    view.ts          # "Orbit Insights" ItemView sidebar panel
  tests/
    client.test.ts   # Client unit tests
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
