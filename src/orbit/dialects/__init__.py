"""Knowledge base dialects and extensible parsing strategies package."""

from orbit.dialects.base import KnowledgeDialect
from orbit.dialects.commonmark import CommonMarkDialect
from orbit.dialects.obsidian import ObsidianDialect
from orbit.dialects.registry import DialectRegistry, get_default_registry

__all__ = [
    "CommonMarkDialect",
    "DialectRegistry",
    "KnowledgeDialect",
    "ObsidianDialect",
    "get_default_registry",
]
