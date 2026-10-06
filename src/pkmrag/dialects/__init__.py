"""Knowledge base dialects and extensible parsing strategies package."""

from pkmrag.dialects.base import KnowledgeDialect
from pkmrag.dialects.commonmark import CommonMarkDialect
from pkmrag.dialects.obsidian import ObsidianDialect
from pkmrag.dialects.registry import DialectRegistry, get_default_registry

__all__ = [
    "CommonMarkDialect",
    "DialectRegistry",
    "KnowledgeDialect",
    "ObsidianDialect",
    "get_default_registry",
]
