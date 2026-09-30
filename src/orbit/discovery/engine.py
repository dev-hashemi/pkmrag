"""Semantic gap detection engine discovering unlinked note pairs with high vector similarity."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

from orbit.config import load_vault_env, settings
from orbit.graph.store import GraphStore
from orbit.graph.traversal import (
    add_inferred_relationship,
    has_inferred_relationship,
)
from orbit.inference.base import InferenceProvider
from orbit.models import DiscoveryStats, InferredRelationship, SemanticGapCandidate
from orbit.search.vector_store import VectorStore


class GapDiscoveryEngine:
    """Discovers semantically similar note pairs lacking explicit graph relationships."""

    def __init__(
        self,
        vault_path: Path | str,
        graph_store: Optional[GraphStore] = None,
        vector_store: Optional[VectorStore] = None,
        inference_provider: Optional[InferenceProvider] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        load_vault_env(self.vault_path)
        self.graph_store = (
            graph_store
            if graph_store is not None
            else GraphStore(settings.get_db_dir(self.vault_path), read_only=False)
        )
        self.vector_store = (
            vector_store
            if vector_store is not None
            else VectorStore(settings.get_vector_dir(self.vault_path))
        )
        self.inference_provider = inference_provider

    def close(self) -> None:
        """Close graph store connection."""
        self.graph_store.close()

    def find_gap_candidates(
        self,
        min_similarity: Optional[float] = None,
        max_hops: Optional[int] = None,
    ) -> list[SemanticGapCandidate]:
        """Scan vector embeddings, group by canonical note pair, and filter out linked notes."""
        threshold = settings.similarity_threshold if min_similarity is None else min_similarity
        hops = settings.graph_distance_threshold if max_hops is None else max_hops
        if self.vector_store.table.count_rows() == 0:
            return []

        # Pull all chunks to iterate their vectors
        arrow_table = (
            self.vector_store.table.search()
            .select(["id", "note_path", "text", "vector"])
            .to_arrow()
        )
        total_chunks = len(arrow_table)
        if total_chunks < 2:
            return []

        ids = arrow_table["id"].to_pylist()
        note_paths = arrow_table["note_path"].to_pylist()
        texts = arrow_table["text"].to_pylist()
        vectors = arrow_table["vector"].to_pylist()

        # Step 1: Find high-similarity chunk pairs and group by canonical note pair
        # candidate_map: (note_a, note_b) -> (max_sim, chunk_a_id, chunk_b_id, text_a, text_b)
        best_pair_matches: dict[tuple[str, str], tuple[float, str, str, str, str]] = {}

        for i in range(total_chunks):
            v_i = vectors[i]
            note_i = note_paths[i]
            id_i = ids[i]
            text_i = texts[i]

            # Search LanceDB for top 20 nearest neighbors using cosine metric
            matches = (
                self.vector_store.table.search(v_i).distance_type("cosine").limit(20).to_list()
            )

            for m in matches:
                note_j = str(m.get("note_path", ""))
                if not note_j or note_j == note_i:
                    continue  # Skip self-note chunks

                dist = float(m.get("_distance", 1.0))
                sim = 1.0 - dist
                if sim < threshold:
                    continue

                id_j = str(m.get("id", ""))
                text_j = str(m.get("text", ""))

                # Canonical pair key (min, max) to eliminate bidirectional duplicates
                pair_key = (min(note_i, note_j), max(note_i, note_j))
                if pair_key not in best_pair_matches or sim > best_pair_matches[pair_key][0]:
                    if note_i == pair_key[0]:
                        best_pair_matches[pair_key] = (sim, id_i, id_j, text_i, text_j)
                    else:
                        best_pair_matches[pair_key] = (sim, id_j, id_i, text_j, text_i)

        # Step 2: Filter out note pairs already connected in LadybugDB within max_hops
        # or already evaluated in INFERRED_REL
        filtered_candidates: list[SemanticGapCandidate] = []
        hop_cache: dict[str, dict[str, int]] = {}

        for (src, dst), (sim, c_src, c_dst, t_src, t_dst) in best_pair_matches.items():
            if src not in hop_cache:
                hop_cache[src] = self.graph_store.get_neighbor_hops(src, max_hops=hops)

            if dst in hop_cache[src]:
                continue  # Already connected within max_hops via LINKS_TO

            # Check if an inferred relationship already exists in the graph
            if has_inferred_relationship(self.graph_store.conn, src, dst):
                continue  # Already evaluated

            filtered_candidates.append(
                SemanticGapCandidate(
                    source_path=src,
                    target_path=dst,
                    similarity=round(sim, 4),
                    source_chunk_id=c_src,
                    target_chunk_id=c_dst,
                    source_chunk_text=t_src,
                    target_chunk_text=t_dst,
                )
            )

        # Sort descending by similarity
        filtered_candidates.sort(key=lambda c: c.similarity, reverse=True)
        return filtered_candidates

    def evaluate_and_persist(
        self,
        candidates: list[SemanticGapCandidate],
        provider: InferenceProvider,
        min_confidence: float = 0.70,
        limit: int = 20,
    ) -> tuple[list[InferredRelationship], int]:
        """Classify candidate pairs using InferenceProvider and persist valid edges."""
        evaluated = 0
        inferred: list[InferredRelationship] = []

        for cand in candidates[:limit]:
            evaluated += 1
            src_title = PurePosixPath(cand.source_path).stem
            dst_title = PurePosixPath(cand.target_path).stem

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
    ) -> tuple[list[SemanticGapCandidate], list[InferredRelationship], DiscoveryStats]:
        """Orchestrate end-to-end candidate discovery and optional LLM classification."""
        start_time = time.perf_counter()
        candidates = self.find_gap_candidates(
            min_similarity=similarity_threshold,
            max_hops=max_hops,
        )

        inferred: list[InferredRelationship] = []
        eff_provider = provider or self.inference_provider
        if not dry_run and candidates:
            if eff_provider is None:
                from orbit.inference.provider import OpenAICompatibleProvider

                eff_provider = OpenAICompatibleProvider()
            inferred, _ = self.evaluate_and_persist(
                candidates,
                provider=eff_provider,
                limit=limit,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000

        stats = DiscoveryStats(
            vault_path=str(self.vault_path),
            total_notes_scanned=self.graph_store.get_stats().get("notes", 0),
            vector_candidates_found=len(candidates),
            graph_filtered_candidates=len(candidates),
            relationships_inferred=len(inferred),
            duration_ms=round(duration_ms, 2),
        )

        return candidates, inferred, stats

    run_discovery = discover
