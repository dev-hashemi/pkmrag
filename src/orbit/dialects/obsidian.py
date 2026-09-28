"""Obsidian vault dialect implementation for Project Orbit."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from orbit.config import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_FILES
from orbit.models import NoteMetadata, ResolvedLink, SourceIndex, Wikilink
from orbit.parser.markdown import parse_note_content


class ObsidianDialect:
    """Dialect implementing Obsidian rules: wikilinks, shortest-path matching, and aliases."""

    name: str = "obsidian"

    def can_handle(self, root_path: Path) -> bool:
        """Check if root directory contains an Obsidian vault or publish structure."""
        return (
            (root_path / ".obsidian").is_dir()
            or (root_path / "site-options.json").is_file()
            or (root_path / "publish.css").is_file()
        )

    def should_ignore_dir(self, dir_name: str) -> bool:
        """Filter out Obsidian internal folders and dot directories."""
        return dir_name in DEFAULT_IGNORED_DIRS or dir_name.startswith(".")

    def should_ignore_file(self, file_name: str) -> bool:
        """Filter out hidden or non-markdown files."""
        return (
            file_name in DEFAULT_IGNORED_FILES
            or file_name.startswith(".")
            or not file_name.endswith(".md")
        )

    def extract_document(
        self,
        rel_path: str,
        content: str,
        mtime: float,
        content_hash: str,
    ) -> NoteMetadata:
        """Parse note content extracting YAML frontmatter, wikilinks, and tags."""
        return parse_note_content(rel_path, content, mtime, content_hash)

    def resolve_link(
        self,
        source_rel_path: str,
        link: Wikilink,
        index: SourceIndex,
    ) -> ResolvedLink:
        """Resolve an Obsidian wikilink using shortest-path, alias, and proximity matching."""
        target = link.target.strip()

        # 1. Self-anchor reference (e.g. `[[#Section]]`)
        if not target:
            return ResolvedLink(
                target_path=source_rel_path,
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # Normalize slashes and leading dots
        norm = target.replace("\\", "/").lstrip("/")
        if norm.startswith("./"):
            norm = norm[2:]

        norm_md = norm if norm.endswith(".md") else f"{norm}.md"

        # 2. Exact relative path from vault root (case-insensitive)
        if norm_md.lower() in index.lower_path_to_path:
            return ResolvedLink(
                target_path=index.lower_path_to_path[norm_md.lower()],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )
        if norm.lower() in index.lower_path_to_path:
            return ResolvedLink(
                target_path=index.lower_path_to_path[norm.lower()],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # 3. Relative to source note directory (case-insensitive)
        source_dir = str(PurePosixPath(source_rel_path).parent)
        if source_dir != ".":
            rel_candidate = f"{source_dir}/{norm_md}".lower()
            if rel_candidate in index.lower_path_to_path:
                return ResolvedLink(
                    target_path=index.lower_path_to_path[rel_candidate],
                    is_unresolved=False,
                    anchor=link.anchor,
                    alias=link.alias,
                    is_embed=link.is_embed,
                )

        # 4. Basename lookup (case-insensitive shortest-unique-path matching)
        base = PurePosixPath(norm).name
        if base.lower().endswith(".md"):
            base = base[:-3]
        base_lower = base.lower()

        if base_lower in index.basename_to_paths:
            candidates = index.basename_to_paths[base_lower]
            if len(candidates) == 1:
                return ResolvedLink(
                    target_path=candidates[0],
                    is_unresolved=False,
                    anchor=link.anchor,
                    alias=link.alias,
                    is_embed=link.is_embed,
                )

            # Same directory takes precedence
            for cand in candidates:
                if str(PurePosixPath(cand).parent) == source_dir:
                    return ResolvedLink(
                        target_path=cand,
                        is_unresolved=False,
                        anchor=link.anchor,
                        alias=link.alias,
                        is_embed=link.is_embed,
                    )

            # Otherwise shallowest path depth
            candidates_sorted = sorted(
                candidates,
                key=lambda p: (len(PurePosixPath(p).parts), p),
            )
            return ResolvedLink(
                target_path=candidates_sorted[0],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # 5. Alias lookup
        target_lower = norm.lower()
        if target_lower in index.alias_to_path:
            return ResolvedLink(
                target_path=index.alias_to_path[target_lower],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # 6. Unresolved / Ghost note
        is_asset = any(
            norm.lower().endswith(ext)
            for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".mp3", ".webp")
        )
        if "/" not in norm and source_dir != ".":
            ghost_path = f"{source_dir}/{norm}" if is_asset else f"{source_dir}/{norm_md}"
        else:
            ghost_path = norm if is_asset else norm_md

        return ResolvedLink(
            target_path=ghost_path,
            is_unresolved=True,
            anchor=link.anchor,
            alias=link.alias,
            is_embed=link.is_embed,
        )
