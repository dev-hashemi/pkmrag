"""Vault filesystem scanner and link resolution engine."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from orbit.config import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_FILES
from orbit.models import NoteMetadata, Wikilink
from orbit.parser.markdown import parse_frontmatter, parse_note_content


class VaultIndexer:
    """Scans Obsidian vault filesystem, indexes notes and aliases, and resolves wikilinks."""

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.paths_set: set[str] = set()
        self.lower_path_to_path: dict[str, str] = {}
        self.basename_to_paths: dict[str, list[str]] = {}
        self.alias_to_path: dict[str, str] = {}
        self.file_hashes: dict[str, str] = {}
        self.file_mtimes: dict[str, float] = {}

    def scan_vault_structure(self) -> dict[str, Path]:
        """Walk the vault directory, filtering out ignored folders/files.

        Returns:
            Mapping from vault-relative POSIX path to absolute Path on disk.
        """
        discovered_files: dict[str, Path] = {}

        for root, dirs, files in os.walk(self.vault_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORED_DIRS and not d.startswith(".")]

            for file_name in files:
                if (
                    file_name in DEFAULT_IGNORED_FILES
                    or file_name.startswith(".")
                    or not file_name.endswith(".md")
                ):
                    continue

                abs_file_path = Path(root) / file_name
                rel_path = abs_file_path.relative_to(self.vault_path).as_posix()
                discovered_files[rel_path] = abs_file_path

        return discovered_files

    def index_vault_files(self, discovered_files: dict[str, Path]) -> None:
        """First-pass indexing of filenames, hashes, and frontmatter aliases."""
        self.paths_set.clear()
        self.lower_path_to_path.clear()
        self.basename_to_paths.clear()
        self.alias_to_path.clear()
        self.file_hashes.clear()
        self.file_mtimes.clear()

        for rel_path, abs_path in discovered_files.items():
            self.paths_set.add(rel_path)
            self.lower_path_to_path[rel_path.lower()] = rel_path

            # Map basename (stem) case-insensitively
            stem = PurePosixPath(rel_path).stem.lower()
            self.basename_to_paths.setdefault(stem, []).append(rel_path)

            # Read file stats and content hash
            stat = abs_path.stat()
            self.file_mtimes[rel_path] = stat.st_mtime

            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self.file_hashes[rel_path] = content_hash

            # Quick frontmatter inspection for aliases
            frontmatter, _ = parse_frontmatter(content)
            aliases_raw = frontmatter.get("aliases") or frontmatter.get("alias")
            if isinstance(aliases_raw, list):
                for a in aliases_raw:
                    if a:
                        self.alias_to_path[str(a).strip().lower()] = rel_path
            elif isinstance(aliases_raw, str):
                for a in aliases_raw.split(","):
                    clean = a.strip()
                    if clean:
                        self.alias_to_path[clean.lower()] = rel_path

    def parse_note(self, rel_path: str, abs_path: Path) -> NoteMetadata:
        """Parse note content into full NoteMetadata."""
        content = abs_path.read_text(encoding="utf-8", errors="replace")
        mtime = self.file_mtimes.get(rel_path, abs_path.stat().st_mtime)
        content_hash = self.file_hashes.get(
            rel_path, hashlib.sha256(content.encode("utf-8")).hexdigest()
        )
        return parse_note_content(rel_path, content, mtime, content_hash)

    def resolve_link(self, source_path: str, link: Wikilink) -> tuple[str, bool]:
        """Resolve a Wikilink against the vault index.

        Returns:
            (canonical_target_path, is_unresolved)
        """
        target = link.target.strip()

        # 1. Self-anchor reference (e.g. `[[#Section]]`)
        if not target:
            return source_path, False

        # Normalize slashes and leading dots
        norm = target.replace("\\", "/").lstrip("/")
        if norm.startswith("./"):
            norm = norm[2:]

        norm_md = norm if norm.endswith(".md") else f"{norm}.md"

        # 2. Exact relative path from vault root (case-insensitive)
        if norm_md.lower() in self.lower_path_to_path:
            return self.lower_path_to_path[norm_md.lower()], False
        if norm.lower() in self.lower_path_to_path:
            return self.lower_path_to_path[norm.lower()], False

        # 3. Relative to source note directory (case-insensitive)
        source_dir = str(PurePosixPath(source_path).parent)
        if source_dir != ".":
            rel_candidate = f"{source_dir}/{norm_md}".lower()
            if rel_candidate in self.lower_path_to_path:
                return self.lower_path_to_path[rel_candidate], False

        # 4. Basename lookup (case-insensitive shortest-unique-path matching)
        base = PurePosixPath(norm).name
        if base.lower().endswith(".md"):
            base = base[:-3]
        base_lower = base.lower()

        if base_lower in self.basename_to_paths:
            candidates = self.basename_to_paths[base_lower]
            if len(candidates) == 1:
                return candidates[0], False

            # Same directory takes precedence
            for cand in candidates:
                if str(PurePosixPath(cand).parent) == source_dir:
                    return cand, False

            # Otherwise shallowest path depth
            candidates_sorted = sorted(
                candidates,
                key=lambda p: (len(PurePosixPath(p).parts), p),
            )
            return candidates_sorted[0], False

        # 5. Alias lookup
        target_lower = norm.lower()
        if target_lower in self.alias_to_path:
            return self.alias_to_path[target_lower], False

        # 6. Unresolved / Ghost note
        is_asset = any(
            norm.lower().endswith(ext)
            for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".mp3", ".webp")
        )
        if "/" not in norm and source_dir != ".":
            ghost_path = f"{source_dir}/{norm}" if is_asset else f"{source_dir}/{norm_md}"
        else:
            ghost_path = norm if is_asset else norm_md
        return ghost_path, True
