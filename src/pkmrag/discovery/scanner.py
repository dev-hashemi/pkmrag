"""Vector and graph scanning that produces semantic gap candidates."""

from __future__ import annotations

from typing import NamedTuple, Optional

from pkmrag.config import settings
from pkmrag.discovery.relatedness import ChunkInput, score_note_chunks
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

CHUNK_COLUMNS = ["id", "note_path", "note_title", "heading", "text", "vector"]
ANN_LIMIT = 20
CHUNK_MATCH_FLOOR = 0.65


class ChunkRow(NamedTuple):
    """A single indexed chunk with its embedding and heading context."""

    chunk_id: str
    note_path: str
    note_title: str
    heading: str
    text: str
    vector: list[float]


class PairMatch(NamedTuple):
    """Scored and classified candidate note pair."""

    final_score: float
    best_sim: float
    best_src_chunk: str
    best_dst_chunk: str
    best_src_text: str
    best_dst_text: str
    src_title: str
    dst_title: str
    matched_chunks: list[ChunkPairMatch]
    relationship_type: str
    ui_summary: str


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

        pairs = self._collect_pairs(rows, threshold)
        candidates = self._filter_pairs(pairs, hops, focus)
        candidates.sort(key=lambda c: c.similarity, reverse=True)
        return candidates

    def _resolve_focus(self, focus_path: Optional[str]) -> Optional[str]:
        """Resolve a note identifier to its canonical graph path."""
        if not focus_path:
            return None
        return resolve_note_path(self.graph_store.conn, focus_path) or focus_path

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
        headings = table["heading"].to_pylist()
        texts = table["text"].to_pylist()
        vectors = table["vector"].to_pylist()
        return [
            ChunkRow(
                chunk_id=str(chunk_id),
                note_path=str(path),
                note_title=str(title or ""),
                heading=str(heading or ""),
                text=str(text),
                vector=vector,
            )
            for chunk_id, path, title, heading, text, vector in zip(
                ids, paths, titles, headings, texts, vectors, strict=True
            )
        ]

    def _collect_pairs(
        self,
        rows: list[ChunkRow],
        threshold: float,
    ) -> dict[tuple[str, str], PairMatch]:
        """Discover candidate note pairs via ANN and compute calibrated relatedness."""
        chunks_by_note: dict[str, list[ChunkInput]] = {}
        titles_by_note: dict[str, str] = {}
        candidate_pair_keys: set[tuple[str, str]] = set()

        for r in rows:
            if r.note_path not in chunks_by_note:
                chunks_by_note[r.note_path] = []
                titles_by_note[r.note_path] = r.note_title
            chunks_by_note[r.note_path].append(ChunkInput(r.chunk_id, r.heading, r.text, r.vector))

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
                        continue

                    sim = 1.0 - float(match.get("_distance", 1.0))
                    if sim < CHUNK_MATCH_FLOOR:
                        continue

                    pair_key = (min(row.note_path, other_path), max(row.note_path, other_path))
                    candidate_pair_keys.add(pair_key)

                    if other_path not in chunks_by_note:
                        other_rows = self._load_chunks(other_path)
                        chunks_by_note[other_path] = [
                            ChunkInput(orow.chunk_id, orow.heading, orow.text, orow.vector)
                            for orow in other_rows
                        ]
                        titles_by_note[other_path] = str(match.get("note_title", "") or "")

        best: dict[tuple[str, str], PairMatch] = {}
        with trace_span("gap.score_candidates", attributes={"pairs": len(candidate_pair_keys)}):
            for path_a, path_b in candidate_pair_keys:
                chunks_a = chunks_by_note.get(path_a, [])
                chunks_b = chunks_by_note.get(path_b, [])
                score = score_note_chunks(chunks_a, chunks_b)

                if score.final_score < threshold or not score.matched_chunks:
                    continue

                best_match = score.matched_chunks[0]
                best[(path_a, path_b)] = PairMatch(
                    final_score=score.final_score,
                    best_sim=score.best_similarity,
                    best_src_chunk=best_match.source_chunk_id,
                    best_dst_chunk=best_match.target_chunk_id,
                    best_src_text=best_match.source_chunk_text,
                    best_dst_text=best_match.target_chunk_text,
                    src_title=titles_by_note.get(path_a, ""),
                    dst_title=titles_by_note.get(path_b, ""),
                    matched_chunks=score.matched_chunks,
                    relationship_type=score.relationship_type,
                    ui_summary=score.ui_summary,
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
            focus_hops = (
                get_neighbor_hops(self.graph_store.conn, focus, max_hops=hops)
                if focus is not None
                else None
            )
            focus_inferred = (
                get_inferred_neighbor_paths(self.graph_store.conn, focus)
                if focus is not None
                else None
            )

            hop_cache: dict[str, dict[str, int]] = {}
            for (src, dst), pair in pairs.items():
                if focus is not None and focus_hops is not None and focus_inferred is not None:
                    other = dst if src == focus else src
                    if other in focus_hops:
                        continue
                    if other in focus_inferred:
                        continue
                else:
                    if src not in hop_cache:
                        hop_cache[src] = get_neighbor_hops(
                            self.graph_store.conn, src, max_hops=hops
                        )
                    if dst in hop_cache[src]:
                        continue
                    if has_inferred_relationship(self.graph_store.conn, src, dst):
                        continue

                candidates.append(
                    SemanticGapCandidate(
                        source_path=src,
                        target_path=dst,
                        source_title=pair.src_title,
                        target_title=pair.dst_title,
                        similarity=pair.final_score,
                        source_chunk_id=pair.best_src_chunk,
                        target_chunk_id=pair.best_dst_chunk,
                        source_chunk_text=pair.best_src_text,
                        target_chunk_text=pair.best_dst_text,
                        chunk_similarity=pair.best_sim,
                        matched_chunks=pair.matched_chunks,
                        relationship_type=pair.relationship_type,
                        ui_summary=pair.ui_summary,
                    )
                )

            filter_span.set_attribute("candidates.count", len(candidates))
            filter_span.set_attribute("pruned_by_graph", len(pairs) - len(candidates))

        return candidates
