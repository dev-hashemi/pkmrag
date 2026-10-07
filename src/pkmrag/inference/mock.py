"""Deterministic mock inference provider for unit testing without network or token costs."""

from __future__ import annotations

from pkmrag.inference.base import InferredRelationshipResult


class MockInferenceProvider:
    """Deterministic mock provider for unit testing without network or token costs."""

    def __init__(
        self,
        default_rel: InferredRelationshipResult | None = None,
        custom_mapping: dict[tuple[str, str], InferredRelationshipResult] | None = None,
    ) -> None:
        self.default_rel = default_rel or InferredRelationshipResult(
            rel_type="NONE",
            confidence=0.5,
            reason="Mock default no relationship",
            direction="source_to_target",
        )
        self.custom_mapping = custom_mapping or {}
        self.name = "mock-inference"
        self.model = "mock-v1"
        self.calls: list[tuple[str, str]] = []

    def classify_relationship(
        self,
        source_title: str,
        source_excerpt: str,
        target_title: str,
        target_excerpt: str,
    ) -> InferredRelationshipResult:
        self.calls.append((source_title, target_title))
        key = (source_title, target_title)
        rev_key = (target_title, source_title)
        if key in self.custom_mapping:
            return self.custom_mapping[key]
        if rev_key in self.custom_mapping:
            return self.custom_mapping[rev_key]
        return self.default_rel

    def test_connection(self) -> tuple[bool, str, float]:
        """Test provider connectivity and return (success, message, latency_ms)."""
        return True, f"Mock provider '{self.model}' active", 0.5
