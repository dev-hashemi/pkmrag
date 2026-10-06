"""Markdown AST parsing, frontmatter extraction, and wikilink tokenization."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader  # type: ignore[assignment]

from pkmrag.models import NoteMetadata, Wikilink

# Regex patterns
FENCED_CODE_PATTERN = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]+`")
WIKILINK_PATTERN = re.compile(
    r"(!)?\[\[([^\[\]|\n#]+)?(?:#([^\[\]|\n|]+))?(?:\|([^\[\]|\n]+))?\]\]"
)
MARKDOWN_LINK_PATTERN = re.compile(r"(!)?\[([^\]\n]+)\]\(([^)\n]+)\)")
TAG_PATTERN = re.compile(r"(?:^|[\s(\[{])#([a-zA-Z0-9_\-\/]*[a-zA-Z_\-\/][a-zA-Z0-9_\-\/]*)")
H1_HEADER_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def strip_code_blocks(content: str) -> str:
    """Mask fenced code blocks and inline code spans to prevent false positive parsing."""
    without_fenced = FENCED_CODE_PATTERN.sub("", content)
    return INLINE_CODE_PATTERN.sub("", without_fenced)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from Markdown content.

    Returns:
        (frontmatter_dict, markdown_body)
    """
    clean_content = content.lstrip("\ufeff")
    if not clean_content.startswith("---"):
        return {}, clean_content

    # Look for closing frontmatter delimiter
    match = re.search(r"^---\s*$", clean_content[3:], re.MULTILINE)
    if not match:
        return {}, clean_content

    yaml_end = 3 + match.end()
    yaml_chunk = clean_content[3 : 3 + match.start()]
    body = clean_content[yaml_end:]

    try:
        data = yaml.load(yaml_chunk, Loader=SafeLoader)
        if isinstance(data, dict):
            return data, body
    except Exception:
        # Fall back gracefully on malformed YAML
        pass

    return {}, clean_content


def normalize_frontmatter_tags(raw_tags: Any) -> list[str]:
    """Normalize tags from YAML frontmatter (lists, strings, comma-separated)."""
    tags: set[str] = set()
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if item is not None:
                val = str(item).lstrip("#").strip()
                if val:
                    tags.add(val)
    elif isinstance(raw_tags, str):
        for part in raw_tags.split(","):
            val = part.lstrip("#").strip()
            if val:
                tags.add(val)
    return sorted(tags)


def normalize_frontmatter_aliases(raw_aliases: Any) -> list[str]:
    """Normalize aliases from YAML frontmatter."""
    aliases: set[str] = set()
    if isinstance(raw_aliases, list):
        for item in raw_aliases:
            if item is not None:
                val = str(item).strip()
                if val:
                    aliases.add(val)
    elif isinstance(raw_aliases, str):
        for part in raw_aliases.split(","):
            val = part.strip()
            if val:
                aliases.add(val)
    return sorted(aliases)


def extract_tags(body: str, frontmatter_tags: list[str] | None = None) -> list[str]:
    """Extract both inline and frontmatter tags.

    Masks links from body to avoid capturing anchor names like `[[#Section]]`.
    """
    tags: set[str] = set(frontmatter_tags or [])

    # Mask links to avoid false positive tags from anchors
    body_no_links = WIKILINK_PATTERN.sub("", body)
    body_no_links = MARKDOWN_LINK_PATTERN.sub("", body_no_links)

    for match in TAG_PATTERN.finditer(body_no_links):
        tag_candidate = match.group(1).strip()
        # Filter trailing punctuation
        tag_candidate = tag_candidate.rstrip(".,;!?:")
        if tag_candidate:
            tags.add(tag_candidate)

    return sorted(tags)


def extract_wikilinks(body: str) -> list[Wikilink]:
    """Extract all wikilinks and internal markdown links from Markdown body in document order."""
    raw_links: list[tuple[int, Wikilink]] = []

    # 1. Obsidian wikilinks: [[target#anchor|alias]] or ![[embed]]
    for match in WIKILINK_PATTERN.finditer(body):
        is_embed = bool(match.group(1))
        target = (match.group(2) or "").strip()
        anchor = (match.group(3) or "").strip()
        alias = (match.group(4) or "").strip()
        raw_text = match.group(0)

        raw_links.append(
            (
                match.start(),
                Wikilink(
                    target=target,
                    anchor=anchor,
                    alias=alias,
                    is_embed=is_embed,
                    raw_text=raw_text,
                ),
            )
        )

    # 2. Standard Markdown links: [alias](target#anchor)
    for match in MARKDOWN_LINK_PATTERN.finditer(body):
        is_embed = bool(match.group(1))
        alias = (match.group(2) or "").strip()
        dest = (match.group(3) or "").strip()

        # Skip external web protocols
        if any(dest.startswith(p) for p in ("http://", "https://", "mailto:", "ftp://")):
            continue

        if "#" in dest:
            target, anchor = dest.split("#", 1)
        else:
            target, anchor = dest, ""

        target = target.strip()
        anchor = anchor.strip()

        # Only process relative markdown or anchor links
        if not target and not anchor:
            continue

        raw_links.append(
            (
                match.start(),
                Wikilink(
                    target=target,
                    anchor=anchor,
                    alias=alias,
                    is_embed=is_embed,
                    raw_text=match.group(0),
                ),
            )
        )

    # Sort in document appearance order
    raw_links.sort(key=lambda item: item[0])
    return [item[1] for item in raw_links]


def parse_note_content(
    rel_path: str,
    content: str,
    mtime: float,
    content_hash: str,
) -> NoteMetadata:
    """Parse Markdown file content into a structured NoteMetadata entity."""
    frontmatter, body = parse_frontmatter(content)
    masked_body = strip_code_blocks(body)

    # Resolve Title
    title = str(frontmatter.get("title", "")).strip()
    if not title:
        h1_match = H1_HEADER_PATTERN.search(masked_body)
        if h1_match:
            title = h1_match.group(1).strip()
        else:
            title = PurePosixPath(rel_path).stem

    # Resolve Aliases
    aliases_raw = frontmatter.get("aliases") or frontmatter.get("alias")
    aliases = normalize_frontmatter_aliases(aliases_raw)

    # Resolve Frontmatter Tags
    fm_tags_raw = frontmatter.get("tags") or frontmatter.get("tag")
    fm_tags = normalize_frontmatter_tags(fm_tags_raw)

    # Resolve All Tags
    tags = extract_tags(masked_body, frontmatter_tags=fm_tags)

    # Resolve Links
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
