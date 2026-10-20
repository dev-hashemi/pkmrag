"""Vector and graph scanning that produces semantic gap candidates."""

from __future__ import annotations

from typing import NamedTuple, Optional

from pkmrag.config import settings
from pkmrag.graph.store import GraphStore
from pkmrag.graph.traversal import (
    get_inferred_neighbor_paths,
    get_neighbor_hops,
    has_inferred_relationship,
    resolve_note_path,
)
from pkmrag.models import SemanticGapCandidate
from pkmrag.search.vector_store import VectorStore
from pkmrag.telemetry import trace_span

# Chunk columns required to build a candidate pair.
CHUNK_COLUMNS = ["id", "note_path", "note_title", "text", "vector"]

# Nearest neighbours retrieved per chunk during the ANN sweep.
ANN_LIMIT = 20

# (similarity, chunk_id_src, chunk_id_dst, text_src, text_dst, title_src, title_dst)
PairMatch = tuple[float, str, str, str, str, str, str]


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
    ) -> dict[tuple[str, str], PairMatch]:
        """Group high-similarity chunk pairs by canonical note pair."""
        best: dict[tuple[str, str], PairMatch] = {}

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
                    if sim < threshold:
                        continue

                    # Canonical pair key (min, max) eliminates bidirectional duplicates.
                    pair_key = (min(row.note_path, other_path), max(row.note_path, other_path))
                    current = best.get(pair_key)
                    if current is not None and sim <= current[0]:
                        continue

                    other_id = str(match.get("id", ""))
                    other_text = str(match.get("text", ""))
                    other_title = str(match.get("note_title", "") or "")
                    if row.note_path == pair_key[0]:
                        best[pair_key] = (
                            sim,
                            row.chunk_id,
                            other_id,
                            row.text,
                            other_text,
                            row.note_title,
                            other_title,
                        )
                    else:
                        best[pair_key] = (
                            sim,
                            other_id,
                            row.chunk_id,
                            other_text,
                            row.text,
                            other_title,
                            row.note_title,
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
                chunk_src,
                chunk_dst,
                text_src,
                text_dst,
                title_src,
                title_dst,
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
                    )
                )

            filter_span.set_attribute("candidates.count", len(candidates))
            filter_span.set_attribute("pruned_by_graph", len(pairs) - len(candidates))

        return candidates
