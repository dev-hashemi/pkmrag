"""Abstract protocol definition for pluggable knowledge base dialects."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pkmrag.models import NoteMetadata, ResolvedLink, SourceIndex, Wikilink


@runtime_checkable
class KnowledgeDialect(Protocol):
    """Protocol defining how an application parses content and resolves graph topology."""

    name: str

    def can_handle(self, root_path: Path) -> bool:
        """Heuristic check to determine if this dialect applies to the given root directory."""
        ...

    def should_ignore_dir(self, dir_name: str) -> bool:
        """Determine if a directory should be skipped during filesystem traversal."""
        ...

    def should_ignore_file(self, file_name: str) -> bool:
        """Determine if a file should be skipped during filesystem traversal."""
        ...

    def extract_document(
        self,
        rel_path: str,
        content: str,
        mtime: float,
        content_hash: str,
    ) -> NoteMetadata:
        """Parse raw document content into metadata, tags, and links."""
        ...

    def resolve_link(
        self,
        source_rel_path: str,
        link: Wikilink,
        index: SourceIndex,
    ) -> ResolvedLink:
        """Resolve a link against indexed documents into a canonical path or ghost note."""
        ...
