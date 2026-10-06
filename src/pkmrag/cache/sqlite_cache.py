"""SQLite-backed L1 query cache with composite hashing and dependency tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from pkmrag.models import CacheStats, SearchResult

logger = logging.getLogger("pkmrag.cache")

SCHEMA_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_accessed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_dependencies (
    cache_key TEXT NOT NULL,
    note_path TEXT NOT NULL,
    PRIMARY KEY (cache_key, note_path)
);

CREATE INDEX IF NOT EXISTS idx_cache_deps_note ON cache_dependencies(note_path);

CREATE TABLE IF NOT EXISTS cache_counters (
    metric TEXT PRIMARY KEY,
    val INTEGER NOT NULL DEFAULT 0
);
"""


class SQLiteQueryCache:
    """Thread-safe SQLite query cache with LRU eviction and reverse dependency tracking."""

    def __init__(
        self,
        db_path: Path | str,
        max_entries: int = 1000,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        """Run DDL and initialize counter metrics."""
        with self._lock:
            self._conn.executescript(SCHEMA_DDL)
            for m in ("hits", "misses", "evictions"):
                self._conn.execute(
                    "INSERT OR IGNORE INTO cache_counters (metric, val) VALUES (?, 0);", (m,)
                )
            self._conn.commit()

    @staticmethod
    def compute_key(
        query: str,
        mode: str = "hybrid",
        near: Optional[str] = None,
        limit: int = 5,
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Build canonical composite cache key from query and all filter parameters."""
        norm_q = " ".join(query.strip().lower().split())
        norm_mode = mode.strip().lower()
        norm_near = (near or "").strip().lower()
        norm_folder = (folder or "").strip("/").lower()
        tag_parts = [t.strip().lstrip("#").lower() for t in (tags or []) if t.strip()]
        norm_tags = ",".join(sorted(tag_parts))
        raw_repr = f"{norm_q}|{norm_mode}|{norm_near}|{limit}|{norm_folder}|{norm_tags}"
        return hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[list[SearchResult]]:
        """Retrieve cached search results if present and not expired."""
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT result_json, created_at FROM query_cache WHERE cache_key = ?;",
                    (cache_key,),
                )
                row = cursor.fetchone()
                if not row:
                    self._increment_counter("misses")
                    return None

                res_json, created_at = row[0], float(row[1])
                now = time.time()
                if self.ttl_seconds is not None and (now - created_at) > self.ttl_seconds:
                    cursor.execute("DELETE FROM query_cache WHERE cache_key = ?;", (cache_key,))
                    cursor.execute(
                        "DELETE FROM cache_dependencies WHERE cache_key = ?;", (cache_key,)
                    )
                    self._conn.commit()
                    self._increment_counter("misses")
                    return None

                cursor.execute(
                    "UPDATE query_cache SET last_accessed_at = ? WHERE cache_key = ?;",
                    (now, cache_key),
                )
                self._increment_counter("hits")
                self._conn.commit()

            raw_list = json.loads(res_json)
            return [SearchResult.model_validate(item) for item in raw_list]
        except Exception as e:
            logger.warning("Cache get error: %s", e)
            return None

    def put(
        self,
        cache_key: str,
        query: str,
        results: list[SearchResult],
        note_paths: list[str],
    ) -> None:
        """Persist search results and inverted note dependencies into cache."""
        try:
            raw_json = json.dumps([r.model_dump() for r in results])
            now = time.time()
            clean_paths = sorted({p.strip() for p in note_paths if p.strip()})

            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO query_cache "
                    "(cache_key, query_text, result_json, created_at, last_accessed_at) "
                    "VALUES (?, ?, ?, ?, ?);",
                    (cache_key, query, raw_json, now, now),
                )
                cursor.execute("DELETE FROM cache_dependencies WHERE cache_key = ?;", (cache_key,))
                if clean_paths:
                    cursor.executemany(
                        "INSERT OR IGNORE INTO cache_dependencies (cache_key, note_path) "
                        "VALUES (?, ?);",
                        [(cache_key, p) for p in clean_paths],
                    )

                self._prune_lru(cursor)
                self._conn.commit()
        except Exception as e:
            logger.warning("Cache put error: %s", e)

    def _prune_lru(self, cursor: sqlite3.Cursor) -> None:
        """Prune oldest entries when cache exceeds capacity."""
        cursor.execute("SELECT COUNT(*) FROM query_cache;")
        count = cursor.fetchone()[0]
        if count > self.max_entries:
            prune_count = max(1, count - self.max_entries + int(self.max_entries * 0.1))
            cursor.execute(
                "DELETE FROM query_cache WHERE cache_key IN ("
                "SELECT cache_key FROM query_cache ORDER BY last_accessed_at ASC LIMIT ?);",
                (prune_count,),
            )
            cursor.execute(
                "DELETE FROM cache_dependencies WHERE cache_key NOT IN "
                "(SELECT cache_key FROM query_cache);"
            )
            self._increment_counter("evictions", count=prune_count)

    def evict_for_notes(self, note_paths: list[str]) -> int:
        """Evict all cached queries referencing the specified note paths."""
        if not note_paths:
            return 0
        try:
            with self._lock:
                cursor = self._conn.cursor()
                placeholders = ",".join("?" for _ in note_paths)
                cursor.execute(
                    f"SELECT DISTINCT cache_key FROM cache_dependencies "
                    f"WHERE note_path IN ({placeholders});",
                    note_paths,
                )
                matching = [row[0] for row in cursor.fetchall()]
                if not matching:
                    return 0

                key_ph = ",".join("?" for _ in matching)
                cursor.execute(f"DELETE FROM query_cache WHERE cache_key IN ({key_ph});", matching)
                cursor.execute(
                    f"DELETE FROM cache_dependencies WHERE cache_key IN ({key_ph});", matching
                )
                self._increment_counter("evictions", count=len(matching))
                self._conn.commit()
                return len(matching)
        except Exception as e:
            logger.warning("Cache eviction error: %s", e)
            return 0

    def clear(self) -> None:
        """Purge all entries and dependencies from cache."""
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM query_cache;")
                cursor.execute("DELETE FROM cache_dependencies;")
                cursor.execute("UPDATE cache_counters SET val = 0;")
                self._conn.commit()
        except Exception as e:
            logger.warning("Cache clear error: %s", e)

    def _increment_counter(self, metric: str, count: int = 1) -> None:
        self._conn.execute(
            "UPDATE cache_counters SET val = val + ? WHERE metric = ?;",
            (count, metric),
        )

    def get_stats(self) -> CacheStats:
        """Compute live cache statistics and hit rate."""
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM query_cache;")
                total = cursor.fetchone()[0]

                cursor.execute("SELECT metric, val FROM cache_counters;")
                counters = dict(cursor.fetchall())
                hits = counters.get("hits", 0)
                misses = counters.get("misses", 0)
                evictions = counters.get("evictions", 0)

            total_reqs = hits + misses
            hit_rate = round(hits / total_reqs, 4) if total_reqs > 0 else 0.0
            size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0

            return CacheStats(
                total_entries=total,
                hits=hits,
                misses=misses,
                hit_rate=hit_rate,
                evictions=evictions,
                db_size_bytes=size_bytes,
            )
        except Exception as e:
            logger.warning("Cache get_stats error: %s", e)
            return CacheStats()

    def close(self) -> None:
        """Safely close SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
