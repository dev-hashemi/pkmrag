"""Factory for instantiating and resolving inference providers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pkmrag.config import settings
from pkmrag.inference.base import InferenceProvider
from pkmrag.inference.limiter import RateLimiter
from pkmrag.inference.ollama import OllamaProvider
from pkmrag.inference.provider import OpenAICompatibleProvider
from pkmrag.vault_config import load_vault_config


def resolve_provider(
    vault_path: Optional[Path] = None,
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    rpm: Optional[int] = None,
    tpm: Optional[int] = None,
    on_wait: Optional[Callable[[float, str], None]] = None,
) -> InferenceProvider:
    """Build configured InferenceProvider merging vault config and overrides."""
    vcfg = load_vault_config(vault_path) if vault_path else None

    eff_type = (provider_type or (vcfg.llm_provider if vcfg else settings.llm_provider)).lower()
    eff_model = model or (vcfg.llm_model if vcfg else settings.llm_model) or None
    eff_base_url = base_url or (vcfg.llm_base_url if vcfg else None) or None
    eff_api_key = api_key or (vcfg.llm_api_key if vcfg else None) or None
    eff_rpm = rpm if rpm is not None else (vcfg.llm_rpm if vcfg else settings.llm_rpm)
    eff_tpm = tpm if tpm is not None else (vcfg.llm_tpm if vcfg else settings.llm_tpm)

    limiter = RateLimiter(rpm=eff_rpm, tpm=eff_tpm, max_retries=settings.llm_max_retries)
    if eff_type == "ollama":
        return OllamaProvider(
            base_url=eff_base_url,
            model=eff_model,
            rate_limiter=limiter,
            on_wait=on_wait,
        )

    return OpenAICompatibleProvider(
        api_key=eff_api_key,
        base_url=eff_base_url,
        model=eff_model,
        rate_limiter=limiter,
        on_wait=on_wait,
    )
