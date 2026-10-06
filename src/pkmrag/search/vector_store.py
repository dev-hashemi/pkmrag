"""Embedded LanceDB vector and full-text search storage engine."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import lancedb
import pyarrow as pa
from lancedb.index import FTS

from pkmrag.config import settings
from pkmrag.models import ChunkMetadata

TABLE_NAME = "chunks"


class VectorStore:
    """Manages LanceDB lifecycle, chunk indexing, dense vector search, and BM25 FTS."""

    def __init__(
        self,
        db_path: Path | str,
        dimension: Optional[int] = None,
        rebuild: bool = False,
    ) -> None:
        self.db_dir = Path(db_path).resolve()
        self.dimension = dimension or settings.embedding_dim

        if rebuild and self.db_dir.exists():
            shutil.rmtree(self.db_dir, ignore_errors=True)

        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_dir))
        self._schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("note_path", pa.string()),
                pa.field("note_title", pa.string()),
                pa.field("heading", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.dimension)),
                pa.field("chunk_index", pa.int32()),
                pa.field("mtime", pa.float64()),
            ]
        )
        self.table = self._init_table(rebuild=rebuild)

    def _init_table(self, rebuild: bool = False) -> Any:
        """Create or open the chunks LanceDB table."""
        table_names = self.db.list_tables().tables
        if TABLE_NAME in table_names and not rebuild:
            return self.db.open_table(TABLE_NAME)
        table = self.db.create_table(TABLE_NAME, schema=self._schema, mode="overwrite")
        table.create_index("text", config=FTS(), replace=True)
        return table

    def upsert_chunks(
        self,
        note_path: str,
        chunks: list[ChunkMetadata],
        vectors: list[list[float]],
        mtime: float,
    ) -> None:
        """Replace all indexed chunks for a specific note."""
        self.delete_note_chunks(note_path)
        if not chunks or not vectors:
            return

        records: list[dict[str, Any]] = []
        for chunk, vec in zip(chunks, vectors):
            records.append(
                {
                    "id": chunk.chunk_id,
                    "note_path": chunk.note_path,
                    "note_title": chunk.note_title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "vector": vec,
                    "chunk_index": chunk.chunk_index,
                    "mtime": mtime,
                }
            )

        self.table.add(records)

    def delete_note_chunks(self, note_path: str) -> None:
        """Delete all chunks belonging to a given note."""
        if self.table.count_rows() == 0:
            return
        escaped_path = note_path.replace("'", "''")
        self.table.delete(f"note_path = '{escaped_path}'")

    def create_fts_index(self) -> None:
        """Create or refresh native Full-Text Search index on text column."""
        self.table.create_index("text", config=FTS(), replace=True)

    def search_dense(
        self,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Run dense approximate nearest neighbor vector search."""
        if self.table.count_rows() == 0:
            return []
        results = self.table.search(query_vector).limit(limit).to_list()
        return list(results)

    def search_sparse(
        self,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Run sparse BM25 full-text search."""
        if not query_text.strip() or self.table.count_rows() == 0:
            return []
        try:
            results = self.table.search(query_text, query_type="fts").limit(limit).to_list()
            return list(results)
        except Exception:
            # Fallback if FTS index empty or unindexed characters
            return []

    def get_tracked_notes(self) -> dict[str, float]:
        """Retrieve mapping of note_path -> mtime currently in vector store."""
        if self.table.count_rows() == 0:
            return {}
        batch = self.table.search().select(["note_path", "mtime"]).to_arrow()
        path_col = batch["note_path"].to_pylist()
        mtime_col = batch["mtime"].to_pylist()
        return dict(zip(path_col, mtime_col))

    def get_total_chunks(self) -> int:
        """Return total number of chunks indexed in the table."""
        return int(self.table.count_rows())

    def close(self) -> None:
        """Cleanly close LanceDB references."""
        pass

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
