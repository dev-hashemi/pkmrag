"""Pydantic data models for vault entities, links, and ingestion statistics."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Wikilink(BaseModel):
    """Extracted link reference (wikilink or markdown link)."""

    target: str
    anchor: str = ""
    alias: str = ""
    is_embed: bool = False
    raw_text: str = ""


# Alias for app-agnostic terminology
RawLink = Wikilink


class ResolvedLink(BaseModel):
    """Link resolved against a knowledge base source index."""

    target_path: str
    is_unresolved: bool
    anchor: str = ""
    alias: str = ""
    is_embed: bool = False


class SourceIndex(BaseModel):
    """Indexed knowledge base metadata for resolving links across documents."""

    paths_set: set[str] = Field(default_factory=set)
    lower_path_to_path: dict[str, str] = Field(default_factory=dict)
    basename_to_paths: dict[str, list[str]] = Field(default_factory=dict)
    alias_to_path: dict[str, str] = Field(default_factory=dict)
    file_hashes: dict[str, str] = Field(default_factory=dict)
    file_mtimes: dict[str, float] = Field(default_factory=dict)


class NoteMetadata(BaseModel):
    """Metadata and extracted graph entities from a single document/note."""

    path: str
    title: str
    hash: str
    mtime: float
    is_unresolved: bool = False
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[Wikilink] = Field(default_factory=list)


class FolderInfo(BaseModel):
    """Directory node representing an Obsidian or filesystem folder."""

    path: str
    name: str
    parent_path: Optional[str] = None


class IngestStats(BaseModel):
    """Statistical summary of a vault graph ingestion run."""

    vault_path: str
    dialect: str = "obsidian"
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
