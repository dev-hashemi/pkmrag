"""Ollama local model inference provider for offline relationship classification."""

from __future__ import annotations

from typing import Callable, Optional

from pkmrag.config import settings
from pkmrag.inference.limiter import RateLimiter
from pkmrag.inference.provider import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local inference provider communicating with Ollama via OpenAI-compatible API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        rate_limiter: Optional[RateLimiter] = None,
        on_wait: Optional[Callable[[float, str], None]] = None,
        is_local: bool = True,
        max_retries: Optional[int] = None,
    ) -> None:
        url = base_url or settings.ollama_base_url
        mdl = model or settings.ollama_model
        super().__init__(
            api_key="ollama",
            base_url=url,
            model=mdl,
            timeout=timeout,
            rate_limiter=rate_limiter,
            on_wait=on_wait,
            is_local=is_local,
            max_retries=max_retries,
        )
        self.name = f"ollama ({self.model})"
