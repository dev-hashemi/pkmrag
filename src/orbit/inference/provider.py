"""Inference provider implementations for relationship classification."""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from orbit.inference.base import InferredRelationshipResult

SYSTEM_PROMPT = """You are an expert personal knowledge graph analyst.
Analyze two notes from a knowledge base that are semantically similar but currently unlinked.
Determine how they are conceptually related.

Available relationship types:
- EXTENDS: Source note adds new concepts, dimensions, or continuation to Target note.
- CONTRADICTS: Source note opposes, disproves, or presents conflicting arguments to Target note.
- SUPPORTS: Source note provides corroborating evidence or validation for Target note.
- PREREQUISITE_FOR: Source note is necessary foundational knowledge for Target note.
- REFINES: Source note provides a specialized, more granular, or updated version of Target note.
- NONE: The notes merely share topical vocabulary without a direct conceptual relationship.

Respond strictly in valid JSON with these fields:
{
  "rel_type": "EXTENDS" | "CONTRADICTS" | "SUPPORTS" | "PREREQUISITE_FOR" | "REFINES" | "NONE",
  "confidence": float between 0.0 and 1.0,
  "reason": "1-2 concise sentences explaining why",
  "direction": "source_to_target" | "target_to_source" | "bidirectional"
}"""


class OpenAICompatibleProvider:
    """Invokes OpenAI or OpenAI-compatible endpoints (Ollama, vLLM, LiteLLM) via HTTP."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        from orbit.config import settings

        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout
        self.name = f"openai-compatible ({self.model})"

    def classify_relationship(
        self,
        source_title: str,
        source_excerpt: str,
        target_title: str,
        target_excerpt: str,
    ) -> InferredRelationshipResult:
        """Query LLM endpoint and parse structured JSON relationship."""
        user_prompt = (
            f"Note A Title: {source_title}\n"
            f"Note A Excerpt:\n{source_excerpt}\n\n"
            f"Note B Title: {target_title}\n"
            f"Note B Excerpt:\n{target_excerpt}\n\n"
            "Classify the relationship between Note A and Note B:"
        )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                raw_content = data["choices"][0]["message"]["content"]
                return self._parse_json_result(raw_content)
        except Exception as e:
            # Return safe NONE on HTTP or parsing failures
            return InferredRelationshipResult(
                rel_type="NONE",
                confidence=0.0,
                reason=f"Inference failed: {e}",
                direction="source_to_target",
            )

    def _parse_json_result(self, raw_content: str) -> InferredRelationshipResult:
        """Extract and validate JSON fields into InferredRelationshipResult."""
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            # Fallback regex extraction if model returned wrapped markdown blocks
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                raise ValueError("No JSON object found in response")

        rel_type = str(parsed.get("rel_type", "NONE")).upper().strip()
        if rel_type not in (
            "EXTENDS",
            "CONTRADICTS",
            "SUPPORTS",
            "PREREQUISITE_FOR",
            "REFINES",
            "NONE",
        ):
            rel_type = "NONE"

        confidence = max(0.0, min(float(parsed.get("confidence", 0.0)), 1.0))
        reason = str(parsed.get("reason", "")).strip() or "No rationale provided"
        direction = str(parsed.get("direction", "source_to_target")).strip()
        if direction not in ("source_to_target", "target_to_source", "bidirectional"):
            direction = "source_to_target"

        return InferredRelationshipResult(
            rel_type=rel_type,  # type: ignore[arg-type]
            confidence=confidence,
            reason=reason,
            direction=direction,  # type: ignore[arg-type]
        )


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
