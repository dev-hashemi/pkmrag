"""Base protocol and structured response models for inference providers."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from orbit.models import RelationshipType


class InferredRelationshipResult(BaseModel):
    """Structured output returned by an inference provider for a candidate pair."""

    rel_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    direction: Literal["source_to_target", "target_to_source", "bidirectional"] = "source_to_target"


@runtime_checkable
class InferenceProvider(Protocol):
    """Protocol for classifying conceptual relationships between note pairs."""

    name: str
    model: str

    def classify_relationship(
        self,
        source_title: str,
        source_excerpt: str,
        target_title: str,
        target_excerpt: str,
    ) -> InferredRelationshipResult:
        """Analyze two note excerpts and return structured relationship classification."""
        ...
