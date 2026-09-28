"""Pydantic data models for vault entities, links, and ingestion statistics."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Wikilink(BaseModel):
    """Extracted wikilink or markdown link reference."""

    target: str
    anchor: str = ""
    alias: str = ""
    is_embed: bool = False
    raw_text: str = ""


class NoteMetadata(BaseModel):
    """Metadata and extracted graph entities from a single markdown note."""

    path: str
    title: str
    hash: str
    mtime: float
    is_unresolved: bool = False
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[Wikilink] = Field(default_factory=list)


class FolderInfo(BaseModel):
    """Directory node representing an Obsidian folder."""

    path: str
    name: str
    parent_path: Optional[str] = None


class IngestStats(BaseModel):
    """Statistical summary of a vault graph ingestion run."""

    vault_path: str
    notes_scanned: int = 0
    notes_added: int = 0
    notes_updated: int = 0
    notes_unchanged: int = 0
    notes_deleted: int = 0
    unresolved_notes: int = 0
    total_notes: int = 0
    total_links: int = 0
    total_tags: int = 0
    total_folders: int = 0
    duration_ms: float = 0.0
