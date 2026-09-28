# AGENTS.md — Project Orbit

## What This Is

A local-first Hybrid GraphRAG engine for linked knowledge bases (Obsidian vaults).
3-tier architecture: deterministic graph (LadybugDB) → semantic search (LanceDB) → AI gap detection (LLM).
Exposed as an MCP server — no chat UI.

## Project Layout

```
src/orbit/
  cli.py          # Typer CLI entry point
  cli_views.py    # Rich terminal display renderers
  config.py       # Settings, defaults, env vars
  models.py       # Pydantic data models (shared across modules)
  doctor.py       # `orbit doctor` health checks
  dialects/       # Pluggable markdown dialect parsing (obsidian, commonmark)
  parser/         # Markdown parsing + vault file indexing
  graph/          # LadybugDB graph store, schema DDL, and traversal
  ingest/         # Vault → graph and vector ingestion pipeline
  search/         # Chunking, FastEmbed, LanceDB vector store, RRF fusion, service
tests/            # Mirrors src/orbit/ structure
benchmarks/       # Ground-truth evaluation benchmarks
```


## Hard Rules

1. **Max 300 lines per file.** If a file approaches this, split it. No exceptions.
2. **No overengineering.** Solve the problem in front of you. Don't add abstractions for hypothetical future needs.
3. **Simple > clever.** If a colleague can't understand it in 30 seconds, rewrite it.
4. **Type everything.** `mypy --strict` must pass. No `Any` escapes except for third-party lib boundaries.
5. **Pydantic for data boundaries.** All structured data crossing module boundaries uses Pydantic models defined in `models.py` (or a module-local `models.py` if domain-specific).
6. **Tests are mandatory.** Every new module gets a corresponding `tests/test_<module>.py`. Test behavior, not implementation.
7. **Preserve existing comments and docstrings** unless directly contradicted by the change.
8. **Keep docs current but minimal.** Update `README.md` and `AGENTS.md` when features or layout change. Don't pad them — if it's obvious from the code, don't document it.

## Style

- **Formatter/linter:** `ruff` (line-length 100). Run `uv run ruff check --fix . && uv run ruff format .`
- **Type checker:** `uv run mypy src/`
- **Tests:** `uv run pytest`
- Docstrings: one-line summary in `"""..."""`. Multi-line only when non-obvious.
- Imports: `from __future__ import annotations` at top of every module.
- Use `Path` from `pathlib`, never raw string paths for filesystem ops.

## Architecture Decisions (Don't Undo These)

- **Embedded DBs only.** LadybugDB + LanceDB + SQLite. No servers, no Docker, no network DBs.
- **Dialect system** for markdown parsing. Obsidian-specific logic lives in `dialects/obsidian.py`, not in the core parser. New vault formats (e.g., Logseq) get a new dialect file.
- **Incremental sync.** Ingestion compares file hashes; only changed files are reprocessed.
- **Inferred edges are separate from ground truth.** AI-discovered relationships go in their own table/label, tagged with confidence + model + timestamp. Never pollute human-curated graph data.
- **MCP over custom UI.** The primary interface is an MCP server (stdio + SSE), not a chat frontend.

## When Adding New Features

1. Check which phase it belongs to in the roadmap (README or companion doc).
2. Put code in the right subpackage. Create a new one if needed — flat files over deep nesting.
3. Add CLI commands in `cli.py` using Typer. Keep handlers thin — delegate to engine modules.
4. Wire up tests before marking done.

## Common Commands

```bash
uv run orbit doctor                      # Sanity check both DBs
uv run orbit ingest <path>               # Ingest a vault (all, graph, or vector)
uv run orbit search "query" --near <note># Hybrid search with graph boost
uv run ruff check --fix .                # Lint
uv run ruff format .                     # Format
uv run mypy src tests                    # Type check
uv run pytest                            # Test
```

