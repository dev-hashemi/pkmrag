# AGENTS.md — PKMRAG

## What This Is

A local-first Hybrid GraphRAG engine for linked personal knowledge bases (PKMs).
Obsidian serves as the primary reference dialect, with a pluggable dialect layer for CommonMark, Logseq, Foam, and other linked systems.
3-tier architecture: deterministic graph (LadybugDB) → semantic search (LanceDB) → AI gap detection (LLM).
Exposed as an MCP server — no chat UI.

## Project Layout

```
src/pkmrag/
  cli.py          # Typer CLI entry point
  cli_views.py    # Rich terminal display renderers
  config.py       # Settings, defaults, env vars
  models.py       # Pydantic data models (shared across modules)
  doctor.py       # `pkmrag doctor` health checks
  dialects/       # Pluggable markdown dialect parsing (obsidian, commonmark)
  cache/          # SQLite L1 query cache and dependency tracking
  parser/         # Markdown parsing + vault file indexing
  graph/          # LadybugDB graph store, schema DDL, and traversal
  ingest/         # Vault → graph and vector ingestion pipeline & single-note reindexer
  search/         # Chunking, FastEmbed, LanceDB vector store, RRF fusion, service
  inference/      # LLM inference client (OpenAI, Ollama) and token-bucket rate limiter
  discovery/      # Semantic gap discovery and relationship inference engine
  eval/           # Retrieval evaluation harness and IR metrics (MRR, Recall, MAP)
  telemetry/      # OpenTelemetry spans, collector, visual tree, tracer lifecycle
  mcp/            # FastMCP server, tool handlers, and stdio transport

tests/            # Mirrors src/pkmrag/ structure
benchmarks/       # Ground-truth evaluation benchmarks (golden_10, vault)
```


## Hard Rules

1. **Max 300 lines per file.** If a file approaches this, split it. No exceptions.
2. **No overengineering.** Solve the problem in front of you. Don't add abstractions for hypothetical future needs.
3. **Simple > clever.** If a colleague can't understand it in 30 seconds, rewrite it.
4. **Prefer focused libraries over hand-rolled code.** If a well-maintained library solves the exact problem, use it — don't rewrite what's already battle-tested. But don't pull in a heavy framework for a single utility; the dependency's weight should be proportional to the value it provides.
5. **Type everything.** `mypy --strict` must pass. No `Any` escapes except for third-party lib boundaries.
6. **Pydantic for data boundaries.** All structured data crossing module boundaries uses Pydantic models defined in `models.py` (or a module-local `models.py` if domain-specific).
7. **Tests are mandatory.** Every new module gets a corresponding `tests/test_<module>.py`. Test behavior, not implementation.
8. **Preserve existing comments and docstrings** unless directly contradicted by the change.
9. **Keep docs current but minimal.** Update `README.md` and `AGENTS.md` when features or layout change. Don't pad them — if it's obvious from the code, don't document it.

## Style

- **Formatter/linter:** `ruff` (line-length 100). Run `uv run ruff check --fix . && uv run ruff format .`
- **Type checker:** `uv run mypy src/`
- **Tests:** `uv run pytest`
- Docstrings: one-line summary in `"""..."""`. Multi-line only when non-obvious.
- Imports: `from __future__ import annotations` at top of every module.
- Use `Path` from `pathlib`, never raw string paths for filesystem ops.

## Architecture Decisions (Don't Undo These)

- **Embedded DBs only.** LadybugDB + LanceDB + SQLite. No servers, no Docker, no network DBs.
- **Dialect-agnostic core.** The property graph, vector store, and MCP tools operate on abstract knowledge primitives (Note, Tag, Folder, LINKS_TO). All syntax parsing lives in pluggable `dialects/` (Obsidian, CommonMark, Logseq). Never introduce dialect-specific branching into storage, search, or MCP tools.
- **Incremental sync.** Ingestion compares file hashes; only changed files are reprocessed.
- **Inferred edges are separate from ground truth.** AI-discovered relationships go in their own table/label, tagged with confidence + model + timestamp. Never pollute human-curated graph data.
- **MCP over custom UI.** The primary interface is an MCP server (stdio + SSE), not a chat frontend.

## When Adding New Features

1. Ensure new functionality aligns with the architectural design and existing subsystems.
2. Put code in the right subpackage. Create a new one if needed — flat files over deep nesting.
3. Add CLI commands in `cli.py` using Typer. Keep handlers thin — delegate to engine modules.
4. Wire up tests before marking done.

## Common Commands

```bash
uv run pkmrag doctor                      # Sanity check both DBs
uv run pkmrag ingest <path>               # Ingest a vault (all, graph, or vector)
uv run pkmrag search "query" --near <note># Hybrid search with graph boost
uv run pkmrag search "query" --trace      # Hybrid search with visual execution trace tree
uv run pkmrag discover <path>             # Discover semantic gaps and infer relationships
uv run pkmrag discover <path> -p ollama   # Offline semantic discovery via local Ollama
uv run pkmrag eval                        # Automated IR retrieval evaluation against golden benchmark
uv run pkmrag serve <path>                # Start stdio MCP server for Claude/Cursor
uv run pkmrag serve <path> -t http        # Start HTTP/SSE MCP & REST daemon on port 3747
uv run pkmrag mcp-config <path>           # Output MCP JSON client configuration
uv run pkmrag install-plugin              # Install Obsidian companion plugin to vault (via PKMRAG_VAULT_PATH)
uv run pkmrag install-plugin --symlink    # Symlink plugin files for live development
uv run ruff check --fix .                 # Lint

uv run ruff format .                      # Format
uv run mypy src tests                     # Type check
uv run pytest                             # Test
```
