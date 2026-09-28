"""Vault filesystem scanner and link resolution engine using pluggable dialects."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Optional

from orbit.dialects.base import KnowledgeDialect
from orbit.dialects.obsidian import ObsidianDialect
from orbit.models import NoteMetadata, ResolvedLink, SourceIndex, Wikilink
from orbit.parser.markdown import parse_frontmatter


class VaultIndexer:
    """Scans knowledge base files, indexes paths, and delegates link resolution to dialects."""

    def __init__(
        self,
        vault_path: Path | str,
        dialect: Optional[KnowledgeDialect] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.dialect: KnowledgeDialect = dialect or ObsidianDialect()
        self.index = SourceIndex()

    @property
    def paths_set(self) -> set[str]:
        return self.index.paths_set

    @property
    def lower_path_to_path(self) -> dict[str, str]:
        return self.index.lower_path_to_path

    @property
    def basename_to_paths(self) -> dict[str, list[str]]:
        return self.index.basename_to_paths

    @property
    def alias_to_path(self) -> dict[str, str]:
        return self.index.alias_to_path

    @property
    def file_hashes(self) -> dict[str, str]:
        return self.index.file_hashes

    @property
    def file_mtimes(self) -> dict[str, float]:
        return self.index.file_mtimes

    def scan_vault_structure(self) -> dict[str, Path]:
        """Walk the directory, filtering out ignored folders/files via the active dialect.

        Returns:
            Mapping from vault-relative POSIX path to absolute Path on disk.
        """
        discovered_files: dict[str, Path] = {}

        for root, dirs, files in os.walk(self.vault_path):
            # Prune ignored directories using active dialect
            dirs[:] = [d for d in dirs if not self.dialect.should_ignore_dir(d)]

            for file_name in files:
                if self.dialect.should_ignore_file(file_name):
                    continue

                abs_file_path = Path(root) / file_name
                rel_path = abs_file_path.relative_to(self.vault_path).as_posix()
                discovered_files[rel_path] = abs_file_path

        return discovered_files

    def index_vault_files(self, discovered_files: dict[str, Path]) -> None:
        """First-pass indexing of filenames, hashes, and frontmatter aliases."""
        self.index.paths_set.clear()
        self.index.lower_path_to_path.clear()
        self.index.basename_to_paths.clear()
        self.index.alias_to_path.clear()
        self.index.file_hashes.clear()
        self.index.file_mtimes.clear()

        for rel_path, abs_path in discovered_files.items():
            self.index.paths_set.add(rel_path)
            self.index.lower_path_to_path[rel_path.lower()] = rel_path

            # Map basename (stem) case-insensitively
            stem = PurePosixPath(rel_path).stem.lower()
            self.index.basename_to_paths.setdefault(stem, []).append(rel_path)

            # Read file stats and content hash
            stat = abs_path.stat()
            self.index.file_mtimes[rel_path] = stat.st_mtime

            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self.index.file_hashes[rel_path] = content_hash

            # Quick frontmatter inspection for aliases
            frontmatter, _ = parse_frontmatter(content)
            aliases_raw = frontmatter.get("aliases") or frontmatter.get("alias")
            if isinstance(aliases_raw, list):
                for a in aliases_raw:
                    if a:
                        self.index.alias_to_path[str(a).strip().lower()] = rel_path
            elif isinstance(aliases_raw, str):
                for a in aliases_raw.split(","):
                    clean = a.strip()
                    if clean:
                        self.index.alias_to_path[clean.lower()] = rel_path

    def parse_note(self, rel_path: str, abs_path: Path) -> NoteMetadata:
        """Parse note content into full NoteMetadata using the active dialect."""
        content = abs_path.read_text(encoding="utf-8", errors="replace")
        mtime = self.index.file_mtimes.get(rel_path, abs_path.stat().st_mtime)
        content_hash = self.index.file_hashes.get(
            rel_path, hashlib.sha256(content.encode("utf-8")).hexdigest()
        )
        return self.dialect.extract_document(rel_path, content, mtime, content_hash)

    def resolve_link(self, source_path: str, link: Wikilink) -> tuple[str, bool]:
        """Resolve a link using the active dialect rules.

        Returns:
            (canonical_target_path, is_unresolved)
        """
        resolved: ResolvedLink = self.dialect.resolve_link(source_path, link, self.index)
        return resolved.target_path, resolved.is_unresolved
