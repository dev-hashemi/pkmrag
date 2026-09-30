"""Pydantic data models for vault entities, links, and ingestion statistics."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

RelationshipType = Literal[
    "EXTENDS",
    "CONTRADICTS",
    "SUPPORTS",
    "PREREQUISITE_FOR",
    "REFINES",
    "NONE",
]


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
    """Statistical summary of a vault graph and vector ingestion run."""

    vault_path: str
    dialect: str = "obsidian"
    target: str = "all"
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
    chunks_created: int = 0
    chunks_deleted: int = 0
    total_chunks: int = 0
    duration_ms: float = 0.0


class ChunkMetadata(BaseModel):
    """Segment of a note split along heading boundaries with context."""

    chunk_id: str
    note_path: str
    note_title: str
    heading: str = ""
    text: str
    chunk_index: int
    token_count: int
    start_char: int = 0
    end_char: int = 0


class SearchResult(BaseModel):
    """Ranked search result retrieved and fused across retrieval pipelines."""

    chunk_id: str
    note_path: str
    note_title: str
    heading: str = ""
    text: str
    score: float
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    graph_boost_factor: float = 1.0
    hop_distance: Optional[int] = None


class NoteContext(BaseModel):
    """Detailed structural neighborhood and metadata for a note."""

    path: str
    title: str
    tags: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    neighbors_2hop: list[str] = Field(default_factory=list)
    inferred_relationships: list[InferredRelationship] = Field(default_factory=list)
    is_unresolved: bool = False


class GraphBridge(BaseModel):
    """Shortest graph path connection between two notes."""

    source: str
    target: str
    found: bool = False
    hops: int = -1
    path: list[str] = Field(default_factory=list)


class VaultOverview(BaseModel):
    """High-level structural summary of vault graph and top hubs."""

    total_notes: int
    resolved_notes: int
    ghost_notes: int
    total_links: int
    total_tags: int
    hub_notes: list[dict[str, Any]] = Field(default_factory=list)
    top_tags: list[dict[str, Any]] = Field(default_factory=list)


class InferredRelationship(BaseModel):
    """An AI-discovered relationship stored separately from human wikilinks."""

    source_path: str
    target_path: str
    rel_type: str
    confidence: float
    reason: str
    model: str = ""
    created_at: str = ""


class SemanticGapCandidate(BaseModel):
    """A pair of notes that exhibit high similarity but lack a graph connection."""

    source_path: str
    target_path: str
    similarity: float
    source_chunk_id: str
    target_chunk_id: str
    source_chunk_text: str
    target_chunk_text: str


class DiscoveryStats(BaseModel):
    """Summary metrics from a semantic gap discovery run."""

    vault_path: str
    total_notes_scanned: int
    vector_candidates_found: int
    graph_filtered_candidates: int
    relationships_inferred: int
    duration_ms: float
