"""Inference provider implementations for relationship classification."""

from __future__ import annotations

import re
from typing import Callable, Optional

import httpx

from pkmrag.inference.base import InferredRelationshipResult
from pkmrag.inference.limiter import RateLimiter, estimate_tokens, parse_retry_after
from pkmrag.telemetry import trace_span

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

Respond strictly in valid JSON adhering to the provided schema with these fields:
- rel_type: "EXTENDS" | "CONTRADICTS" | "SUPPORTS" | "PREREQUISITE_FOR" | "REFINES" | "NONE"
- confidence: float between 0.0 and 1.0
- reason: 1-2 concise sentences explaining why
- direction: "source_to_target" | "target_to_source" | "bidirectional"
"""


class OpenAICompatibleProvider:
    """Invokes OpenAI or OpenAI-compatible endpoints (Ollama, Groq, vLLM) with strict schema."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        rate_limiter: Optional[RateLimiter] = None,
        on_wait: Optional[Callable[[float, str], None]] = None,
        is_local: bool = False,
        max_retries: Optional[int] = None,
    ) -> None:
        from pkmrag.config import settings

        self.api_key = api_key or settings.openai_api_key
        raw_base = (base_url or settings.openai_base_url).rstrip("/")
        if ("localhost" in raw_base or "127.0.0.1" in raw_base) and not raw_base.endswith("/v1"):
            raw_base = f"{raw_base}/v1"
        self.base_url = raw_base
        self.model = model or settings.llm_model
        self.timeout = timeout
        self.name = f"openai-compatible ({self.model})"
        self.is_local = is_local
        self.max_retries = (
            max_retries
            if max_retries is not None
            else (rate_limiter.max_retries if rate_limiter else settings.llm_max_retries)
        )
        self.rate_limiter = (
            rate_limiter
            if rate_limiter is not None
            else RateLimiter(
                rpm=settings.llm_rpm,
                tpm=settings.llm_tpm,
                max_retries=self.max_retries,
            )
        )
        self.on_wait = on_wait
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def classify_relationship(
        self,
        source_title: str,
        source_excerpt: str,
        target_title: str,
        target_excerpt: str,
    ) -> InferredRelationshipResult:
        """Query LLM endpoint and return deterministic, schema-validated relationship."""
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

        if not self.is_local:
            prompt_tokens = estimate_tokens(user_prompt) + estimate_tokens(SYSTEM_PROMPT) + 150
            self.rate_limiter.acquire(prompt_tokens, on_wait=self.on_wait)

        with trace_span(
            "llm.classify_relationship",
            attributes={
                "model": self.model,
                "source.title": source_title,
                "target.title": target_title,
            },
        ) as span:
            strict_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "inferred_relationship",
                    "strict": True,
                    "schema": InferredRelationshipResult.strict_json_schema(),
                },
            }

            messages: list[dict[str, str]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            attempt = 0
            use_strict = True
            max_retries = self.rate_limiter.max_retries

            while attempt <= max_retries:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    "response_format": strict_format if use_strict else {"type": "json_object"},
                }

                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )

                        if resp.status_code == 429:
                            if attempt < max_retries:
                                retry_after = parse_retry_after(resp)
                                self.rate_limiter.wait_for_retry(
                                    attempt, retry_after, on_wait=self.on_wait
                                )
                                attempt += 1
                                continue
                            resp.raise_for_status()

                        if resp.status_code == 400 and use_strict:
                            use_strict = False
                            continue

                        resp.raise_for_status()
                        data = resp.json()

                        usage = data.get("usage", {})
                        p_tok = int(usage.get("prompt_tokens", 0))
                        c_tok = int(usage.get("completion_tokens", 0))
                        t_tok = int(usage.get("total_tokens", p_tok + c_tok))
                        self.total_prompt_tokens += p_tok
                        self.total_completion_tokens += c_tok
                        span.set_attribute("gen_ai.usage.prompt_tokens", p_tok)
                        span.set_attribute("gen_ai.usage.completion_tokens", c_tok)
                        span.set_attribute("tokens.prompt", p_tok)
                        span.set_attribute("tokens.completion", c_tok)
                        span.set_attribute("tokens.total", t_tok)

                        raw_content = data["choices"][0]["message"]["content"]
                        try:
                            res = self._parse_json_result(raw_content)
                            span.set_attribute("rel_type", res.rel_type)
                            return res
                        except ValueError as val_err:
                            if attempt < max_retries:
                                attempt += 1
                                messages.append({"role": "assistant", "content": raw_content})
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            f"Output failed validation: {val_err}. "
                                            "Return ONLY a valid JSON object matching the schema."
                                        ),
                                    }
                                )
                                continue
                            return InferredRelationshipResult(
                                rel_type="NONE",
                                confidence=0.0,
                                reason=f"Validation failed after retries: {val_err}",
                                direction="source_to_target",
                            )

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < max_retries:
                        retry_after = parse_retry_after(e.response)
                        self.rate_limiter.wait_for_retry(attempt, retry_after, on_wait=self.on_wait)
                        attempt += 1
                        continue
                    return InferredRelationshipResult(
                        rel_type="NONE",
                        confidence=0.0,
                        reason=f"Inference HTTP error {e.response.status_code}: {e}",
                        direction="source_to_target",
                    )
                except Exception as e:
                    return InferredRelationshipResult(
                        rel_type="NONE",
                        confidence=0.0,
                        reason=f"Inference failed: {e}",
                        direction="source_to_target",
                    )

            return InferredRelationshipResult(
                rel_type="NONE",
                confidence=0.0,
                reason="Exceeded maximum rate limit retries (HTTP 429)",
                direction="source_to_target",
            )

    def _parse_json_result(self, raw_content: str) -> InferredRelationshipResult:
        """Validate JSON content directly into InferredRelationshipResult model."""
        try:
            return InferredRelationshipResult.model_validate_json(raw_content)
        except Exception as e_direct:
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                try:
                    return InferredRelationshipResult.model_validate_json(match.group(0))
                except Exception as e_regex:
                    raise ValueError(f"Schema validation error: {e_regex}") from e_regex
            raise ValueError(f"Invalid JSON or schema validation error: {e_direct}") from e_direct


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
