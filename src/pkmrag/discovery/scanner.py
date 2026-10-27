"""Vector and graph scanning that produces semantic gap candidates."""

from __future__ import annotations

from collections import Counter
from typing import NamedTuple, Optional

from pkmrag.config import settings
from pkmrag.graph.store import GraphStore
from pkmrag.graph.traversal import (
    get_inferred_neighbor_paths,
    get_neighbor_hops,
    has_inferred_relationship,
    resolve_note_path,
)
from pkmrag.models import ChunkPairMatch, SemanticGapCandidate
from pkmrag.search.vector_store import VectorStore
from pkmrag.telemetry import trace_span

CHUNK_COLUMNS = ["id", "note_path", "note_title", "text", "vector"]
ANN_LIMIT = 20
COVERAGE_ALPHA = 0.3
CHUNK_MATCH_FLOOR = 0.65

ChunkMatch = tuple[float, str, str, str, str, str, str]
PairMatch = tuple[float, float, str, str, str, str, str, str, list[ChunkPairMatch]]


class ChunkRow(NamedTuple):
    """A single indexed chunk with its embedding."""

    chunk_id: str
    note_path: str
    note_title: str
    text: str
    vector: list[float]


class GapScanner:
    """Finds semantically similar note pairs that lack a graph connection."""

    def __init__(self, graph_store: GraphStore, vector_store: VectorStore) -> None:
        self.graph_store = graph_store
        self.vector_store = vector_store

    def scan(
        self,
        min_similarity: Optional[float] = None,
        max_hops: Optional[int] = None,
        focus_path: Optional[str] = None,
    ) -> list[SemanticGapCandidate]:
        """Scan embeddings for similar note pairs, excluding already connected ones.

        When ``focus_path`` is given the sweep is restricted to that note's chunks,
        which makes the cost proportional to the note instead of the whole vault.
        """
        threshold = settings.similarity_threshold if min_similarity is None else min_similarity
        hops = settings.graph_distance_threshold if max_hops is None else max_hops
        if self.vector_store.table.count_rows() == 0:
            return []

        focus = self._resolve_focus(focus_path)
        rows = self._load_chunks(focus)
        if not rows:
            return []

        chunk_counts = (
            dict(Counter(r.note_path for r in rows))
            if focus is None
            else self._count_chunks_per_note()
        )

        pairs = self._collect_pairs(rows, threshold, chunk_counts)
        candidates = self._filter_pairs(pairs, hops, focus)
        candidates.sort(key=lambda c: c.similarity, reverse=True)
        return candidates

    def _resolve_focus(self, focus_path: Optional[str]) -> Optional[str]:
        """Resolve a note identifier to its canonical graph path."""
        if not focus_path:
            return None
        return resolve_note_path(self.graph_store.conn, focus_path) or focus_path

    def _count_chunks_per_note(self) -> dict[str, int]:
        """Return total chunk count per note across the vector store."""
        table = self.vector_store.table.search().select(["note_path"]).to_arrow()
        return dict(Counter(table["note_path"].to_pylist()))

    def _load_chunks(self, focus: Optional[str]) -> list[ChunkRow]:
        """Load every chunk, or only the chunks belonging to the focus note."""
        query = self.vector_store.table.search()
        if focus is not None:
            escaped = focus.replace("'", "''")
            query = query.where(f"note_path = '{escaped}'")
        table = query.select(CHUNK_COLUMNS).to_arrow()
        ids = table["id"].to_pylist()
        paths = table["note_path"].to_pylist()
        titles = table["note_title"].to_pylist()
        texts = table["text"].to_pylist()
        vectors = table["vector"].to_pylist()
        return [
            ChunkRow(
                chunk_id=str(chunk_id),
                note_path=str(path),
                note_title=str(title or ""),
                text=str(text),
                vector=vector,
            )
            for chunk_id, path, title, text, vector in zip(
                ids, paths, titles, texts, vectors, strict=True
            )
        ]

    def _collect_pairs(
        self,
        rows: list[ChunkRow],
        threshold: float,
        chunk_counts: dict[str, int],
    ) -> dict[tuple[str, str], PairMatch]:
        """Group chunk pairs by canonical note pair and compute coverage-weighted scores."""
        pair_data: dict[
            tuple[str, str],
            tuple[dict[tuple[str, str], ChunkMatch], dict[str, float], dict[str, float]],
        ] = {}

        with trace_span("gap.vector_ann", attributes={"similarity_threshold": threshold}):
            for row in rows:
                matches = (
                    self.vector_store.table.search(row.vector)
                    .distance_type("cosine")
                    .limit(ANN_LIMIT)
                    .to_list()
                )

                for match in matches:
                    other_path = str(match.get("note_path", ""))
                    if not other_path or other_path == row.note_path:
                        continue  # Skip self-note chunks

                    sim = 1.0 - float(match.get("_distance", 1.0))
                    if sim < CHUNK_MATCH_FLOOR:
                        continue

                    # Canonical pair key (min, max) eliminates bidirectional duplicates.
                    pair_key = (min(row.note_path, other_path), max(row.note_path, other_path))
                    other_id = str(match.get("id", ""))
                    other_text = str(match.get("text", ""))
                    other_title = str(match.get("note_title", "") or "")

                    if row.note_path == pair_key[0]:
                        c_a_id, c_b_id = row.chunk_id, other_id
                        txt_a, txt_b = row.text, other_text
                        t_a, t_b = row.note_title, other_title
                    else:
                        c_a_id, c_b_id = other_id, row.chunk_id
                        txt_a, txt_b = other_text, row.text
                        t_a, t_b = other_title, row.note_title

                    match_key = (c_a_id, c_b_id)
                    chunk_match = (sim, c_a_id, c_b_id, txt_a, txt_b, t_a, t_b)

                    if pair_key not in pair_data:
                        pair_data[pair_key] = (
                            {match_key: chunk_match},
                            {c_a_id: sim},
                            {c_b_id: sim},
                        )
                    else:
                        matches_map, sims_a, sims_b = pair_data[pair_key]
                        if match_key not in matches_map or sim > matches_map[match_key][0]:
                            matches_map[match_key] = chunk_match
                        if sim > sims_a.get(c_a_id, 0.0):
                            sims_a[c_a_id] = sim
                        if sim > sims_b.get(c_b_id, 0.0):
                            sims_b[c_b_id] = sim

        best: dict[tuple[str, str], PairMatch] = {}
        for pair_key, (matches_map, sims_a, sims_b) in pair_data.items():
            path_a, path_b = pair_key
            tot_a = chunk_counts.get(path_a, len(sims_a))
            tot_b = chunk_counts.get(path_b, len(sims_b))

            cov_a = len(sims_a) / max(1, tot_a)
            cov_b = len(sims_b) / max(1, tot_b)
            coverage = min(cov_a, cov_b)

            all_sims = list(sims_a.values()) + list(sims_b.values())
            avg_sim = sum(all_sims) / len(all_sims)

            final_score = avg_sim * (COVERAGE_ALPHA + (1.0 - COVERAGE_ALPHA) * coverage)
            if final_score < threshold:
                continue

            sorted_chunks = sorted(matches_map.values(), key=lambda m: m[0], reverse=True)[:5]
            best_chunk = sorted_chunks[0]
            matched_list = [
                ChunkPairMatch(
                    source_chunk_id=m[1],
                    target_chunk_id=m[2],
                    source_chunk_text=m[3],
                    target_chunk_text=m[4],
                    similarity=round(m[0], 4),
                )
                for m in sorted_chunks
            ]

            best[pair_key] = (
                final_score,
                best_chunk[0],
                best_chunk[1],
                best_chunk[2],
                best_chunk[3],
                best_chunk[4],
                best_chunk[5],
                best_chunk[6],
                matched_list,
            )

        return best

    def _filter_pairs(
        self,
        pairs: dict[tuple[str, str], PairMatch],
        hops: int,
        focus: Optional[str],
    ) -> list[SemanticGapCandidate]:
        """Drop pairs already connected in the graph or already evaluated by the LLM."""
        candidates: list[SemanticGapCandidate] = []

        with trace_span(
            "gap.graph_filter",
            attributes={"max_hops": hops, "raw_candidates": len(pairs)},
        ) as filter_span:
            # Hop distance is symmetric, so a focus note needs a single neighbour map
            # instead of one lookup per candidate pair.
            focus_hops: dict[str, int] = {}
            focus_inferred: set[str] = set()
            if focus is not None and pairs:
                focus_hops = get_neighbor_hops(self.graph_store.conn, focus, max_hops=hops)
                focus_inferred = get_inferred_neighbor_paths(self.graph_store.conn, focus)

            hop_cache: dict[str, dict[str, int]] = {}
            for (src, dst), (
                sim,
                chunk_sim,
                chunk_src,
                chunk_dst,
                text_src,
                text_dst,
                title_src,
                title_dst,
                matched_chunks,
            ) in pairs.items():
                if focus is not None:
                    other = dst if src == focus else src
                    if other in focus_hops:
                        continue  # Already connected within max_hops via LINKS_TO
                    if other in focus_inferred:
                        continue  # Already evaluated
                else:
                    if src not in hop_cache:
                        hop_cache[src] = get_neighbor_hops(
                            self.graph_store.conn, src, max_hops=hops
                        )
                    if dst in hop_cache[src]:
                        continue  # Already connected within max_hops via LINKS_TO
                    if has_inferred_relationship(self.graph_store.conn, src, dst):
                        continue  # Already evaluated

                candidates.append(
                    SemanticGapCandidate(
                        source_path=src,
                        target_path=dst,
                        source_title=title_src,
                        target_title=title_dst,
                        similarity=round(sim, 4),
                        source_chunk_id=chunk_src,
                        target_chunk_id=chunk_dst,
                        source_chunk_text=text_src,
                        target_chunk_text=text_dst,
                        chunk_similarity=round(chunk_sim, 4),
                        matched_chunks=matched_chunks,
                    )
                )

            filter_span.set_attribute("candidates.count", len(candidates))
            filter_span.set_attribute("pruned_by_graph", len(pairs) - len(candidates))

        return candidates
