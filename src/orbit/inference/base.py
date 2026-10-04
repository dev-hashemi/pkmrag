"""Base protocol and structured response models for inference providers."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orbit.models import RelationshipType


class InferredRelationshipResult(BaseModel):
    """Structured output returned by an inference provider for a candidate pair."""

    model_config = ConfigDict(extra="forbid")

    rel_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    direction: Literal["source_to_target", "target_to_source", "bidirectional"] = "source_to_target"

    @field_validator("rel_type", mode="before")
    @classmethod
    def _normalize_rel_type(cls, v: object) -> str:
        if isinstance(v, str):
            clean = v.upper().strip()
            if clean in (
                "EXTENDS",
                "CONTRADICTS",
                "SUPPORTS",
                "PREREQUISITE_FOR",
                "REFINES",
                "NONE",
            ):
                return clean
        return "NONE"

    @classmethod
    def strict_json_schema(cls) -> dict[str, object]:
        """Generate strict JSON schema conforming to OpenAI/Groq structured outputs."""
        schema = cls.model_json_schema()
        schema["required"] = list(schema.get("properties", {}).keys())
        return schema


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
