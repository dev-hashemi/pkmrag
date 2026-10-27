"""Contract guard: the Obsidian plugin DTOs must mirror the canonical Pydantic models."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from pkmrag.mcp.models import JobState
from pkmrag.models import (
    ChunkPairMatch,
    InferredRelationship,
    NoteContext,
    SearchResult,
    SemanticGapCandidate,
)

PLUGIN_TYPES = Path(__file__).resolve().parents[1] / "plugins" / "obsidian" / "src" / "types.ts"

# Interfaces that are transferred verbatim over the REST API.
SHARED_INTERFACES: dict[str, type[BaseModel]] = {
    "SearchResult": SearchResult,
    "SemanticGapCandidate": SemanticGapCandidate,
    "ChunkPairMatch": ChunkPairMatch,
    "NoteContext": NoteContext,
    "InferredRelationship": InferredRelationship,
    "ActiveJobState": JobState,
}

INTERFACE_RE = re.compile(
    r"export interface (?P<name>\w+)\s*\{(?P<body>[^}]*)\}",
    re.DOTALL,
)
FIELD_RE = re.compile(r"^\s*(?:readonly\s+)?(?P<name>\w+)\s*[?:]", re.MULTILINE)


def _plugin_interface_fields(source: str, name: str) -> set[str]:
    for match in INTERFACE_RE.finditer(source):
        if match.group("name") != name:
            continue
        return {m.group("name") for m in FIELD_RE.finditer(match.group("body"))}
    raise AssertionError(f"Interface '{name}' not found in {PLUGIN_TYPES}")


def _model_fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields.keys())


@pytest.mark.parametrize("name", sorted(SHARED_INTERFACES))
def test_plugin_dto_matches_backend_model(name: str) -> None:
    """Plugin TypeScript interfaces must expose exactly the backend model fields."""
    model = SHARED_INTERFACES[name]
    source = PLUGIN_TYPES.read_text(encoding="utf-8")
    plugin_fields = _plugin_interface_fields(source, name)
    model_fields = _model_fields(model)

    missing = model_fields - plugin_fields
    extra = plugin_fields - model_fields

    assert not missing, f"Plugin interface '{name}' is missing backend fields: {sorted(missing)}"
    assert not extra, f"Plugin interface '{name}' has fields absent from backend: {sorted(extra)}"


def test_plugin_types_file_exists() -> None:
    """Guard against the contract test silently passing on a renamed file."""
    assert PLUGIN_TYPES.is_file(), f"Plugin types file not found at {PLUGIN_TYPES}"
