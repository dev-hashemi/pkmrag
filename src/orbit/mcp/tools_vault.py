"""Vault browsing and navigation tools for the Orbit MCP server."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Optional

from orbit.config import settings
from orbit.graph.store import GraphStore
from orbit.graph.traversal import get_all_tags, get_notes_by_tag

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def execute_list_notes(
    vault_path: Path,
    folder: Optional[str] = None,
    pattern: Optional[str] = None,
    limit: int = 100,
) -> str:
    """List markdown notes in the vault with optional folder and filename filtering."""
    clamped = max(1, min(limit, 200))
    resolved_vault = vault_path.resolve()

    search_root = resolved_vault
    if folder:
        candidate = (resolved_vault / folder.strip("/")).resolve()
        if not candidate.is_relative_to(resolved_vault):
            return f"Error: Folder '{folder}' is outside vault boundaries."
        if not candidate.is_dir():
            return f"Error: Folder '{folder}' does not exist."
        search_root = candidate

    note_files: list[Path] = []
    for ext in settings.supported_extensions:
        note_files.extend(search_root.rglob(f"*{ext}"))
    sorted_files = sorted(set(note_files))

    # Exclude internal/hidden directories (.obsidian, .git, .trash, logseq, node_modules, etc.)
    sorted_files = [
        f
        for f in sorted_files
        if not any(
            part.startswith(".") or part.lower() in settings.ignored_dirs
            for part in f.relative_to(resolved_vault).parts
        )
    ]

    if pattern:
        sorted_files = [f for f in sorted_files if fnmatch.fnmatch(f.name.lower(), pattern.lower())]

    total = len(sorted_files)
    truncated = total > clamped
    display_files = sorted_files[:clamped]

    if not display_files:
        folder_msg = f" in folder '{folder}'" if folder else ""
        pattern_msg = f" matching '{pattern}'" if pattern else ""
        return f"No markdown notes found{folder_msg}{pattern_msg}."

    header = f"Found {total} notes"
    if truncated:
        header += f" (showing first {clamped})"
    lines: list[str] = [f"{header}:\n"]

    for f in display_files:
        rel = f.relative_to(resolved_vault).as_posix()
        size_kb = f.stat().st_size / 1024
        lines.append(f"- `{rel}` ({size_kb:.1f} KB)")

    if truncated:
        lines.append(
            f"\n*Truncated: {total - clamped} more notes not shown. "
            "Use `folder` or `pattern` to narrow results.*"
        )

    return "\n".join(lines)


def execute_list_tags(
    graph_store: Optional[GraphStore],
    limit: int = 50,
) -> str:
    """List all tags in the vault ordered by frequency."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    tags = get_all_tags(graph_store.conn, limit=limit)
    if not tags:
        return "No tags found in the vault."

    lines: list[str] = [f"Found {len(tags)} tags:\n"]
    lines.append("| Tag | Notes |")
    lines.append("| :--- | :---: |")
    for t in tags:
        lines.append(f"| `#{t['tag']}` | {t['notes_count']} |")

    return "\n".join(lines)


def execute_search_by_tag(
    graph_store: Optional[GraphStore],
    tag: str,
    limit: int = 50,
) -> str:
    """Find all notes with a specific tag."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    clean_tag = tag.strip().lstrip("#")
    if not clean_tag:
        return "Tag cannot be empty."

    notes = get_notes_by_tag(graph_store.conn, clean_tag, limit=limit)
    if not notes:
        return f"No notes found with tag `#{clean_tag}`."

    lines: list[str] = [f"Found {len(notes)} notes tagged `#{clean_tag}`:\n"]
    for n in notes:
        title = n["title"] or n["path"]
        lines.append(f"- `{n['path']}` — {title}")

    return "\n".join(lines)


def execute_get_outline(
    vault_path: Path,
    note_path: str,
) -> str:
    """Extract the heading structure of a note for navigation."""
    clean = note_path.strip()
    if not clean:
        return "Note path cannot be empty."

    resolved_vault = vault_path.resolve()
    raw_path = Path(clean)
    target = raw_path.resolve() if raw_path.is_absolute() else (vault_path / clean).resolve()

    if not target.is_relative_to(resolved_vault):
        return f"Error: Access denied. '{note_path}' is outside vault boundaries."

    if not target.exists() and not target.suffix:
        for ext in settings.supported_extensions:
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

    rel_name = target.relative_to(resolved_vault).as_posix()
    headings: list[str] = []
    for i, line in enumerate(content.splitlines(), 1):
        match = HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            indent = "  " * (level - 1)
            headings.append(f"{indent}- {title} (line {i})")

    if not headings:
        return f"# Outline: {rel_name}\n\nNo headings found in this note."

    return f"# Outline: {rel_name}\n\n" + "\n".join(headings)


def execute_discover_gaps(
    vault_path: Path,
    graph_store: Optional[GraphStore],
    threshold: float = 0.80,
    limit: int = 10,
) -> str:
    """Discover unlinked note pairs exhibiting high semantic similarity (semantic gaps)."""
    if graph_store is None:
        return "Graph store is not available for this vault."

    from orbit.discovery.engine import GapDiscoveryEngine

    engine = GapDiscoveryEngine(vault_path=vault_path, graph_store=graph_store)
    candidates = engine.find_gap_candidates(min_similarity=threshold)

    if not candidates:
        return (
            f"No semantic gaps found with similarity >= {threshold:.2f} "
            "(all closely related notes are already connected in the graph)."
        )

    clamped = max(1, min(limit, 50))
    display = candidates[:clamped]
    lines: list[str] = [f"# Discovered Semantic Gaps ({len(candidates)} candidate pairs found):\n"]
    for c in display:
        lines.append(
            f"### `{c.source_path}` ↔ `{c.target_path}`\n"
            f"- **Cosine Similarity**: {c.similarity:.4f}\n"
            f"- **Source Excerpt**: {c.source_chunk_text[:120].strip()}...\n"
            f"- **Target Excerpt**: {c.target_chunk_text[:120].strip()}...\n"
        )

    if len(candidates) > clamped:
        lines.append(
            f"\n*Showing top {clamped} of {len(candidates)} gaps. "
            f"Run `orbit discover` via CLI to classify with LLM.*"
        )

    return "\n".join(lines)
