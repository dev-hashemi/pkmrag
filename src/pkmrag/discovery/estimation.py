"""Pre-flight token and candidate estimation for AI gap discovery."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Optional

from pkmrag.inference.factory import resolve_provider
from pkmrag.inference.limiter import estimate_tokens
from pkmrag.inference.provider import SYSTEM_PROMPT
from pkmrag.models_discovery import CandidatePairSummary, DiscoveryEstimate

if TYPE_CHECKING:
    from pkmrag.discovery.engine import GapDiscoveryEngine


def estimate_discovery(
    engine: GapDiscoveryEngine,
    similarity_threshold: Optional[float] = None,
    focus_path: Optional[str] = None,
    limit: int = 20,
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> DiscoveryEstimate:
    """Estimate candidate count and prompt/completion tokens prior to running AI discovery."""
    candidates = engine.find_gap_candidates(
        min_similarity=similarity_threshold,
        focus_path=focus_path,
    )
    eval_candidates = candidates[:limit]

    provider = engine.inference_provider
    if provider is None:
        provider = resolve_provider(
            vault_path=engine.vault_path,
            provider_type=provider_type,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )

    system_tokens = estimate_tokens(SYSTEM_PROMPT)
    total_prompt_tokens = 0
    pairs_summary: list[CandidatePairSummary] = []

    for cand in eval_candidates:
        src_title = PurePosixPath(cand.source_path).stem
        dst_title = PurePosixPath(cand.target_path).stem
        user_prompt = (
            f"Note A Title: {src_title}\n"
            f"Note A Excerpt:\n{cand.source_chunk_text[:1500]}\n\n"
            f"Note B Title: {dst_title}\n"
            f"Note B Excerpt:\n{cand.target_chunk_text[:1500]}\n\n"
            "Classify the relationship between Note A and Note B:"
        )
        total_prompt_tokens += estimate_tokens(user_prompt) + system_tokens + 150
        pairs_summary.append(
            CandidatePairSummary(
                source_path=cand.source_path,
                target_path=cand.target_path,
                source_title=src_title,
                target_title=dst_title,
                similarity=round(cand.similarity, 4),
            )
        )

    completion_tokens = 120 * len(eval_candidates)
    return DiscoveryEstimate(
        candidate_count=len(candidates),
        evaluated_count=len(eval_candidates),
        estimated_prompt_tokens=total_prompt_tokens,
        estimated_completion_tokens=completion_tokens,
        total_tokens=total_prompt_tokens + completion_tokens,
        provider=provider.name,
        model=provider.model,
        candidate_pairs=pairs_summary,
    )
