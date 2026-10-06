"""High-level query cache manager coordinating cache lookup and invalidation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pkmrag.cache.sqlite_cache import SQLiteQueryCache
from pkmrag.config import settings
from pkmrag.models import CacheStats, SearchResult


class CacheManager:
    """Manages query caching lifecycle, key generation, and dependency invalidation."""

    def __init__(
        self,
        vault_path: Path | str,
        enabled: Optional[bool] = None,
        max_entries: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
        db_path: Optional[Path | str] = None,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.enabled = settings.cache_enabled if enabled is None else enabled
        self.max_entries = settings.cache_max_entries if max_entries is None else max_entries
        self.ttl_seconds = settings.cache_ttl_seconds if ttl_seconds is None else ttl_seconds

        target_db = Path(db_path) if db_path else settings.get_cache_db_path(self.vault_path)
        self._cache = (
            SQLiteQueryCache(
                db_path=target_db,
                max_entries=self.max_entries,
                ttl_seconds=self.ttl_seconds,
            )
            if self.enabled
            else None
        )

    def get(
        self,
        query: str,
        mode: str = "hybrid",
        near: Optional[str] = None,
        limit: int = 5,
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Optional[list[SearchResult]]:
        """Look up cached search results for the given query and filter parameters."""
        if not self.enabled or self._cache is None:
            return None
        key = SQLiteQueryCache.compute_key(
            query=query, mode=mode, near=near, limit=limit, folder=folder, tags=tags
        )
        return self._cache.get(key)

    def put(
        self,
        query: str,
        mode: str,
        results: list[SearchResult],
        near: Optional[str] = None,
        limit: int = 5,
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Store search results and associated note path dependencies in the cache."""
        if not self.enabled or self._cache is None or not results:
            return
        key = SQLiteQueryCache.compute_key(
            query=query, mode=mode, near=near, limit=limit, folder=folder, tags=tags
        )
        note_paths = list({r.note_path for r in results})
        if near:
            note_paths.append(near)
        self._cache.put(key, query=query, results=results, note_paths=note_paths)

    def invalidate_notes(self, note_paths: list[str]) -> int:
        """Evict cached queries that returned any of the specified notes."""
        if not self.enabled or self._cache is None or not note_paths:
            return 0
        return self._cache.evict_for_notes(note_paths)

    def invalidate_all(self) -> None:
        """Purge the entire query cache."""
        if self._cache is not None:
            self._cache.clear()

    def get_stats(self) -> CacheStats:
        """Fetch current cache metrics."""
        if self._cache is None:
            return CacheStats()
        return self._cache.get_stats()

    def close(self) -> None:
        """Clean up cache resources."""
        if self._cache is not None:
            self._cache.close()
