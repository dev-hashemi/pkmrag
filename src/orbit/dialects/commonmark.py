"""Standard CommonMark documentation repository dialect implementation."""

from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath

from orbit.config import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_FILES
from orbit.models import NoteMetadata, ResolvedLink, SourceIndex, Wikilink
from orbit.parser.markdown import (
    extract_tags,
    extract_wikilinks,
    normalize_frontmatter_aliases,
    normalize_frontmatter_tags,
    parse_frontmatter,
    strip_code_blocks,
)


class CommonMarkDialect:
    """Dialect for standard Markdown repositories, documentation sites, and wikis.

    Enforces strict relative POSIX path matching for links and frontmatter metadata.
    """

    name: str = "commonmark"

    def can_handle(self, root_path: Path) -> bool:
        """Generic fallback when no specialized PKM directory structure is present."""
        return not (root_path / ".obsidian").is_dir()

    def should_ignore_dir(self, dir_name: str) -> bool:
        """Filter out hidden, build, and version control directories."""
        return (
            dir_name in DEFAULT_IGNORED_DIRS
            or dir_name.startswith(".")
            or dir_name in {"build", "dist", "out", "_site"}
        )

    def should_ignore_file(self, file_name: str) -> bool:
        """Filter out hidden and non-markdown files."""
        return (
            file_name in DEFAULT_IGNORED_FILES
            or file_name.startswith(".")
            or not file_name.endswith((".md", ".markdown"))
        )

    def extract_document(
        self,
        rel_path: str,
        content: str,
        mtime: float,
        content_hash: str,
    ) -> NoteMetadata:
        """Parse standard Markdown content extracting frontmatter, markdown links, and tags."""
        frontmatter, body = parse_frontmatter(content)
        masked_body = strip_code_blocks(body)

        # Title
        title = str(frontmatter.get("title", "")).strip()
        if not title:
            title = PurePosixPath(rel_path).stem

        # Aliases
        aliases_raw = frontmatter.get("aliases") or frontmatter.get("alias")
        aliases = normalize_frontmatter_aliases(aliases_raw)

        # Tags (frontmatter + optional inline tags)
        fm_tags_raw = frontmatter.get("tags") or frontmatter.get("tag")
        fm_tags = normalize_frontmatter_tags(fm_tags_raw)
        tags = extract_tags(masked_body, frontmatter_tags=fm_tags)

        # Links (extracts both markdown [text](dest) and any wikilinks present)
        links = extract_wikilinks(masked_body)

        return NoteMetadata(
            path=rel_path,
            title=title,
            hash=content_hash,
            mtime=mtime,
            is_unresolved=False,
            aliases=aliases,
            tags=tags,
            links=links,
        )

    def resolve_link(
        self,
        source_rel_path: str,
        link: Wikilink,
        index: SourceIndex,
    ) -> ResolvedLink:
        """Resolve links using strict POSIX relative directory navigation."""
        target = link.target.strip()

        # 1. Self-anchor reference
        if not target:
            return ResolvedLink(
                target_path=source_rel_path,
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # Clean target path
        norm = target.replace("\\", "/").strip()

        # Handle absolute links from vault root
        if norm.startswith("/"):
            candidate = posixpath.normpath(norm.lstrip("/"))
        else:
            source_dir = posixpath.dirname(source_rel_path)
            candidate = posixpath.normpath(posixpath.join(source_dir, norm))

        # Check if extension is needed
        valid_exts = (".md", ".markdown", ".png", ".jpg", ".svg", ".pdf")
        if not any(candidate.endswith(ext) for ext in valid_exts):
            candidate_md = f"{candidate}.md"
        else:
            candidate_md = candidate

        # Verify against index
        if candidate_md.lower() in index.lower_path_to_path:
            return ResolvedLink(
                target_path=index.lower_path_to_path[candidate_md.lower()],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        if candidate.lower() in index.lower_path_to_path:
            return ResolvedLink(
                target_path=index.lower_path_to_path[candidate.lower()],
                is_unresolved=False,
                anchor=link.anchor,
                alias=link.alias,
                is_embed=link.is_embed,
            )

        # Fallback to unresolved ghost node
        return ResolvedLink(
            target_path=candidate_md,
            is_unresolved=True,
            anchor=link.anchor,
            alias=link.alias,
            is_embed=link.is_embed,
        )
