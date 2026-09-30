"""Tool implementations exposed by the Project Orbit MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit.config import SUPPORTED_NOTE_EXTENSIONS
from orbit.graph.paths import (
    find_shortest_bridge,
    get_note_structural_context,
    get_vault_overview,
)
from orbit.graph.store import GraphStore
from orbit.search.service import SearchService


def execute_query_vault(
    search_service: SearchService,
    query: str,
    near: Optional[str] = None,
    mode: str = "hybrid",
    limit: int = 5,
    folder: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> str:
    """Execute hybrid search over the vault and format results as readable markdown."""
    clean_query = query.strip()
    if not clean_query:
        return "Query cannot be empty."

    results = search_service.search(
        query=clean_query,
        near=near,
        mode=mode,
        limit=max(1, min(limit, 20)),
        folder=folder,
        tags=tags,
    )

    if not results:
        details: list[str] = []
        if near:
            details.append(f"near '{near}'")
        if folder:
            details.append(f"in folder '{folder}'")
        if tags:
            details.append(f"with tags {tags}")
        filter_msg = f" ({', '.join(details)})" if details else ""
        return f"No relevant note chunks found for query: '{clean_query}'{filter_msg}."

    lines: list[str] = [f"Found {len(results)} relevant chunks in vault:\n"]
    for i, r in enumerate(results, start=1):
        heading_str = f" > {r.heading}" if r.heading else ""
        boost_str = (
            f" [graph boost: {r.graph_boost_factor:.2f}x]" if r.graph_boost_factor > 1.0 else ""
        )
        lines.append(
            f"### Result {i}: {r.note_title}{heading_str}\n"
            f"- **Path**: `{r.note_path}`\n"
            f"- **Score**: {r.score:.4f}{boost_str}\n\n"
            f"{r.text.strip()}\n"
        )

    return "\n---\n".join(lines)


def execute_read_note(
    vault_path: Path,
    note_path: str,
    max_chars: int = 15000,
    offset: int = 0,
    graph_store: Optional[GraphStore] = None,
) -> str:
    """Safely read full or partial note content, enforcing vault containment boundaries."""
    clean = note_path.strip()
    if not clean:
        return "Note path cannot be empty."

    resolved_vault = vault_path.resolve()
    raw_path = Path(clean)
    if raw_path.is_absolute():
        target = raw_path.resolve()
    else:
        target = (vault_path / clean).resolve()

    if not target.is_relative_to(resolved_vault):
        return f"Error: Access denied. '{note_path}' is outside vault boundaries."

    # Try appending supported extensions if file not found directly
    if not target.exists() and not target.suffix:
        for ext in SUPPORTED_NOTE_EXTENSIONS:
            candidate = target.with_suffix(ext)
            if candidate.exists() and candidate.is_relative_to(resolved_vault):
                target = candidate
                break

    if not target.is_file():
        return f"Error: Note '{note_path}' does not exist on disk."

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading note '{note_path}': {e}"

    total_len = len(content)
    if offset >= total_len:
        return (
            f"Note '{note_path}' has length {total_len} chars. "
            f"Requested offset {offset} is out of bounds."
        )

    clamped_max = max(100, min(max_chars, 50000))
    chunk = content[offset : offset + clamped_max]
    footer = ""
    if offset + clamped_max < total_len:
        next_offset = offset + clamped_max
        footer = (
            f"\n\n... [Truncated: showing chars {offset}..{next_offset} of {total_len}. "
            f"Call read_note with offset={next_offset} to read further.]"
        )

    rel_name = target.relative_to(resolved_vault).as_posix()
    result = f"# Note: {rel_name}\n\n{chunk}{footer}"

    if graph_store is not None:
        try:
            ctx = get_note_structural_context(graph_store.conn, rel_name)
            if ctx is not None:
                tags_str = ", ".join(f"`#{t}`" for t in ctx.tags) if ctx.tags else "None"
                out_items = [f"`{link}`" for link in ctx.outgoing_links[:10]]
                if len(ctx.outgoing_links) > 10:
                    out_items.append(f"+{len(ctx.outgoing_links) - 10} more")
                out_str = ", ".join(out_items) if out_items else "None"

                back_items = [f"`{link}`" for link in ctx.backlinks[:10]]
                if len(ctx.backlinks) > 10:
                    back_items.append(f"+{len(ctx.backlinks) - 10} more")
                back_str = ", ".join(back_items) if back_items else "None"

                result += (
                    f"\n\n---\n"
                    f"**Context**: Tags: {tags_str} | "
                    f"Outgoing ({len(ctx.outgoing_links)}): {out_str} | "
                    f"Backlinks ({len(ctx.backlinks)}): {back_str}"
                )
        except Exception:
            pass

    return result


def execute_get_note_context(
    graph_store: Optional[GraphStore],
    note_path: str,
) -> str:
    """Retrieve structured graph context including outgoing links, backlinks, and tags."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    ctx = get_note_structural_context(graph_store.conn, note_path)
    if ctx is None:
        return f"Note '{note_path}' was not found in the graph index."

    status_str = (
        "Ghost Note (unresolved wikilink target)" if ctx.is_unresolved else "Resolved on disk"
    )
    tags_str = ", ".join(f"`#{t}`" for t in ctx.tags) if ctx.tags else "None"

    def _format_bullets(items: list[str]) -> str:
        if not items:
            return "*(None)*"
        return "\n".join(f"- `{item}`" for item in items[:25])

    return (
        f"# Graph Context: {ctx.title}\n"
        f"- **Path**: `{ctx.path}`\n"
        f"- **Status**: {status_str}\n"
        f"- **Tags**: {tags_str}\n\n"
        f"## Outgoing Links ({len(ctx.outgoing_links)})\n"
        f"{_format_bullets(ctx.outgoing_links)}\n\n"
        f"## Backlinks / Cited By ({len(ctx.backlinks)})\n"
        f"{_format_bullets(ctx.backlinks)}\n\n"
        f"## 2-Hop Cluster ({len(ctx.neighbors_2hop)})\n"
        f"{_format_bullets(ctx.neighbors_2hop)}"
    )


def execute_find_bridges(
    graph_store: Optional[GraphStore],
    source_note: str,
    target_note: str,
    max_hops: int = 5,
) -> str:
    """Discover the shortest path of links connecting two notes across the graph."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    bridge = find_shortest_bridge(
        graph_store.conn,
        source_note,
        target_note,
        max_hops=max_hops,
    )

    if not bridge.found:
        return (
            f"No link path found between '{source_note}' and '{target_note}' "
            f"within {max_hops} hops."
        )

    if bridge.hops == 0:
        return f"Source and target refer to the exact same note: `{bridge.source}`."

    path_chain = " ➔ ".join(f"`{p}`" for p in bridge.path)
    return (
        f"# Shortest Bridge: {bridge.source} ↔ {bridge.target}\n"
        f"- **Distance**: {bridge.hops} hops\n"
        f"- **Path**: {path_chain}\n"
    )


def execute_vault_overview(
    graph_store: Optional[GraphStore],
    limit: int = 10,
) -> str:
    """Summarize overall vault graph topology, hub notes, and popular tags."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    overview = get_vault_overview(graph_store.conn, limit=limit)

    hubs_rows = (
        "\n".join(f"| `{h['path']}` | {h['backlinks_count']} |" for h in overview.hub_notes)
        or "| *(None)* | 0 |"
    )

    tags_rows = (
        "\n".join(f"| `#{t['tag']}` | {t['notes_count']} |" for t in overview.top_tags)
        or "| *(None)* | 0 |"
    )

    return (
        f"# Vault Knowledge Graph Overview\n"
        f"- **Total Notes**: {overview.total_notes} "
        f"({overview.resolved_notes} on disk, {overview.ghost_notes} unresolved ghost notes)\n"
        f"- **Total Wikilinks**: {overview.total_links}\n"
        f"- **Total Unique Tags**: {overview.total_tags}\n\n"
        f"## Top Central Hub Notes (Most Backlinks / Maps of Content)\n"
        f"| Note Path | Backlinks Count |\n"
        f"| :--- | :---: |\n"
        f"{hubs_rows}\n\n"
        f"## Top Tags\n"
        f"| Tag | Notes Count |\n"
        f"| :--- | :---: |\n"
        f"{tags_rows}"
    )
