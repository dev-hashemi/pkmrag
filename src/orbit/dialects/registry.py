"""Registry and auto-detection engine for knowledge base dialects."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit.dialects.base import KnowledgeDialect
from orbit.dialects.commonmark import CommonMarkDialect
from orbit.dialects.obsidian import ObsidianDialect


class DialectRegistry:
    """Manages available source dialects and handles automatic detection."""

    def __init__(self) -> None:
        self._dialects: dict[str, KnowledgeDialect] = {}

    def register(self, dialect: KnowledgeDialect) -> None:
        """Register a new knowledge base dialect."""
        self._dialects[dialect.name.lower()] = dialect

    def get(self, name: str) -> KnowledgeDialect:
        """Retrieve a dialect by name."""
        clean_name = name.lower().strip()
        if clean_name not in self._dialects:
            available = ", ".join(sorted(self._dialects.keys()))
            raise ValueError(f"Unknown dialect '{name}'. Available dialects: {available}")
        return self._dialects[clean_name]

    def list_dialects(self) -> list[str]:
        """List all registered dialect names."""
        return sorted(self._dialects.keys())

    def detect(self, root_path: Path, preferred: Optional[str] = "auto") -> KnowledgeDialect:
        """Determine appropriate dialect for a directory via auto-detection or explicit choice."""
        if preferred and preferred.lower() != "auto":
            return self.get(preferred)

        resolved_root = Path(root_path).resolve()

        # 1. Specialized application checks (e.g. Obsidian)
        for name, dialect in self._dialects.items():
            if name != "commonmark" and dialect.can_handle(resolved_root):
                return dialect

        # 2. Fall back to CommonMark if present, otherwise default to Obsidian
        commonmark = self._dialects.get("commonmark")
        if commonmark and commonmark.can_handle(resolved_root):
            return commonmark

        return self.get("obsidian")


def get_default_registry() -> DialectRegistry:
    """Create and populate standard DialectRegistry with built-in dialects."""
    registry = DialectRegistry()
    registry.register(ObsidianDialect())
    registry.register(CommonMarkDialect())
    return registry
