"""Semantic gap detection engine discovering unlinked note pairs with high vector similarity."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from pkmrag.config import load_vault_env, settings
from pkmrag.discovery.scanner import GapScanner
from pkmrag.graph.paths import find_shortest_bridge
from pkmrag.graph.store import GraphStore
from pkmrag.graph.traversal import add_inferred_relationship
from pkmrag.inference.base import InferenceProvider
from pkmrag.models import DiscoveryStats, InferredRelationship, SemanticGapCandidate
from pkmrag.search.vector_store import VectorStore
from pkmrag.telemetry import trace_span


class GapDiscoveryEngine:
    """Discovers semantically similar note pairs lacking explicit graph relationships."""

    def __init__(
        self,
        vault_path: Path | str,
        graph_store: Optional[GraphStore] = None,
        vector_store: Optional[VectorStore] = None,
        inference_provider: Optional[InferenceProvider] = None,
        read_only: bool = False,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        load_vault_env(self.vault_path)
        self._owns_graph_store = graph_store is None
        self.graph_store = (
            graph_store
            if graph_store is not None
            else GraphStore(settings.get_db_dir(self.vault_path), read_only=read_only)
        )
        self.vector_store = (
            vector_store
            if vector_store is not None
            else VectorStore(settings.get_vector_dir(self.vault_path))
        )
        self.inference_provider = inference_provider
        self.scanner = GapScanner(self.graph_store, self.vector_store)

    def close(self) -> None:
        """Close graph store connection when this engine owns it."""
        if self._owns_graph_store:
            self.graph_store.close()

    def find_gap_candidates(
        self,
        min_similarity: Optional[float] = None,
        max_hops: Optional[int] = None,
        focus_path: Optional[str] = None,
    ) -> list[SemanticGapCandidate]:
        """Scan embeddings for similar note pairs, excluding already connected ones.

        Passing ``focus_path`` restricts the sweep to a single note, which keeps the
        cost proportional to that note rather than to the size of the vault.
        """
        return self.scanner.scan(
            min_similarity=min_similarity,
            max_hops=max_hops,
            focus_path=focus_path,
        )

    def enrich_candidates(
        self,
        candidates: list[SemanticGapCandidate],
        max_hops: int = 10,
    ) -> list[SemanticGapCandidate]:
        """Populate hop distance and shortest bridge path for each candidate pair."""
        enriched: list[SemanticGapCandidate] = []
        for cand in candidates:
            bridge = find_shortest_bridge(
                self.graph_store.conn,
                cand.source_path,
                cand.target_path,
                max_hops=max_hops,
            )
            enriched.append(
                cand.model_copy(
                    update={
                        "hops": bridge.hops,
                        "bridge_path": bridge.path,
                    }
                )
            )
        return enriched

    def evaluate_and_persist(
        self,
        candidates: list[SemanticGapCandidate],
        provider: InferenceProvider,
        min_confidence: float = 0.70,
        limit: int = 20,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> tuple[list[InferredRelationship], int]:
        """Classify candidate pairs using InferenceProvider and persist valid edges."""
        evaluated = 0
        inferred: list[InferredRelationship] = []
        total = min(len(candidates), limit)

        for cand in candidates[:limit]:
            evaluated += 1
            src_title = PurePosixPath(cand.source_path).stem
            dst_title = PurePosixPath(cand.target_path).stem

            if on_progress:
                on_progress(evaluated, total, f"Classifying: {src_title} ↔ {dst_title}")

            # Pass surgical excerpt (up to 1500 chars)
            res = provider.classify_relationship(
                source_title=src_title,
                source_excerpt=cand.source_chunk_text[:1500],
                target_title=dst_title,
                target_excerpt=cand.target_chunk_text[:1500],
            )

            if res.rel_type == "NONE" or res.confidence < min_confidence:
                continue

            # Determine directionality
            if res.direction == "target_to_source":
                src_path, dst_path = cand.target_path, cand.source_path
            else:
                src_path, dst_path = cand.source_path, cand.target_path

            rel = InferredRelationship(
                source_path=src_path,
                target_path=dst_path,
                rel_type=res.rel_type,
                confidence=round(res.confidence, 4),
                reason=res.reason,
                model=provider.name,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            add_inferred_relationship(self.graph_store.conn, rel)
            inferred.append(rel)

        return inferred, evaluated

    def discover(
        self,
        similarity_threshold: Optional[float] = None,
        max_hops: Optional[int] = None,
        limit: int = 20,
        dry_run: bool = False,
        provider: Optional[InferenceProvider] = None,
        provider_type: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        rpm: Optional[int] = None,
        tpm: Optional[int] = None,
        enrich: bool = False,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> tuple[list[SemanticGapCandidate], list[InferredRelationship], DiscoveryStats]:
        """Orchestrate end-to-end candidate discovery and optional LLM classification."""
        start_time = time.perf_counter()
        with trace_span("pkmrag.discover", attributes={"limit": limit, "dry_run": dry_run}) as span:
            candidates = self.find_gap_candidates(
                min_similarity=similarity_threshold,
                max_hops=max_hops,
            )
            if enrich and candidates:
                candidates = self.enrich_candidates(candidates)

            inferred: list[InferredRelationship] = []
            eff_provider = provider or self.inference_provider
            if not dry_run and candidates:
                if eff_provider is None:
                    from pkmrag.inference.factory import resolve_provider

                    def on_wait(delay: float, reason: str) -> None:
                        if on_progress:
                            on_progress(-1, -1, f"Rate limit wait ({reason}): {delay:.1f}s")

                    eff_provider = resolve_provider(
                        vault_path=self.vault_path,
                        provider_type=provider_type,
                        model=model,
                        base_url=base_url,
                        api_key=api_key,
                        rpm=rpm,
                        tpm=tpm,
                        on_wait=on_wait,
                    )

                inferred, _ = self.evaluate_and_persist(
                    candidates,
                    provider=eff_provider,
                    limit=limit,
                    on_progress=on_progress,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            p_tok = int(getattr(eff_provider, "total_prompt_tokens", 0) or 0)
            c_tok = int(getattr(eff_provider, "total_completion_tokens", 0) or 0)
            span.set_attribute("discovery.candidates", len(candidates))
            span.set_attribute("discovery.inferred", len(inferred))
            span.set_attribute("gen_ai.usage.prompt_tokens", p_tok)
            span.set_attribute("gen_ai.usage.completion_tokens", c_tok)

            stats = DiscoveryStats(
                vault_path=str(self.vault_path),
                total_notes_scanned=self.graph_store.get_stats().get("notes", 0),
                vector_candidates_found=len(candidates),
                graph_filtered_candidates=len(candidates),
                relationships_inferred=len(inferred),
                duration_ms=round(duration_ms, 2),
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
            )

            return candidates, inferred, stats

    run_discovery = discover
