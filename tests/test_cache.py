"""Unit tests for SQLite-backed L1 query caching and dependency invalidation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orbit.cache.manager import CacheManager
from orbit.cache.sqlite_cache import SQLiteQueryCache
from orbit.models import SearchResult


def _make_dummy_result(chunk_id: str, note_path: str, score: float = 0.9) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        note_path=note_path,
        note_title=Path(note_path).stem,
        heading="Introduction",
        text=f"Sample text content for {note_path}",
        score=score,
    )


def test_composite_key_differentiation() -> None:
    """Verify composite cache key changes when any filter parameter changes."""
    k1 = SQLiteQueryCache.compute_key("caching", mode="hybrid")
    k2 = SQLiteQueryCache.compute_key("caching", mode="dense")
    k3 = SQLiteQueryCache.compute_key("caching", mode="hybrid", near="Storage")
    k4 = SQLiteQueryCache.compute_key("caching", mode="hybrid", folder="Core")
    k5 = SQLiteQueryCache.compute_key("caching", mode="hybrid", tags=["db", "arch"])
    # Tag order invariant:
    k6 = SQLiteQueryCache.compute_key("caching", mode="hybrid", tags=["arch", "db"])
    # Case & whitespace invariant:
    k7 = SQLiteQueryCache.compute_key("  Caching  ", mode="hybrid")

    assert k1 != k2
    assert k1 != k3
    assert k1 != k4
    assert k1 != k5
    assert k5 == k6
    assert k1 == k7


def test_sqlite_cache_put_get_hit(tmp_path: Path) -> None:
    """Verify cache stores and retrieves search results with high fidelity."""
    db_file = tmp_path / "cache.db"
    cache = SQLiteQueryCache(db_file)

    key = SQLiteQueryCache.compute_key("hybrid search")
    results = [_make_dummy_result("c1", "Notes/Search.md", 0.95)]

    assert cache.get(key) is None

    cache.put(key, query="hybrid search", results=results, note_paths=["Notes/Search.md"])

    cached = cache.get(key)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].chunk_id == "c1"
    assert cached[0].note_path == "Notes/Search.md"
    assert cached[0].score == 0.95

    stats = cache.get_stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.total_entries == 1
    assert stats.hit_rate == 0.5
    cache.close()


def test_reverse_dependency_invalidation(tmp_path: Path) -> None:
    """Verify modifying a note evicts only the queries that depend on it."""
    db_file = tmp_path / "cache.db"
    cache = SQLiteQueryCache(db_file)

    k_auth = SQLiteQueryCache.compute_key("auth workflow")
    k_db = SQLiteQueryCache.compute_key("database storage")

    res_auth = [
        _make_dummy_result("c1", "Auth.md"),
        _make_dummy_result("c2", "Users.md"),
    ]
    res_db = [
        _make_dummy_result("c3", "Database.md"),
        _make_dummy_result("c4", "Storage.md"),
    ]

    cache.put(k_auth, "auth workflow", res_auth, ["Auth.md", "Users.md"])
    cache.put(k_db, "database storage", res_db, ["Database.md", "Storage.md"])

    assert cache.get(k_auth) is not None
    assert cache.get(k_db) is not None

    # Mutate Users.md -> should evict auth query but preserve database query
    evicted = cache.evict_for_notes(["Users.md"])
    assert evicted == 1

    assert cache.get(k_auth) is None
    assert cache.get(k_db) is not None
    cache.close()


def test_lru_eviction(tmp_path: Path) -> None:
    """Verify oldest entries are evicted when cache exceeds capacity."""
    db_file = tmp_path / "cache.db"
    cache = SQLiteQueryCache(db_file, max_entries=5)

    for i in range(8):
        k = SQLiteQueryCache.compute_key(f"query {i}")
        cache.put(k, f"query {i}", [_make_dummy_result(f"c{i}", f"Note_{i}.md")], [f"Note_{i}.md"])
        time.sleep(0.01)

    stats = cache.get_stats()
    assert stats.total_entries <= 5
    assert stats.evictions > 0
    cache.close()


def test_cache_ttl_expiration(tmp_path: Path) -> None:
    """Verify expired cache items are purged on access."""
    db_file = tmp_path / "cache.db"
    cache = SQLiteQueryCache(db_file, ttl_seconds=1)

    key = SQLiteQueryCache.compute_key("temporary query")
    cache.put(key, "temporary query", [_make_dummy_result("c1", "Temp.md")], ["Temp.md"])

    assert cache.get(key) is not None
    time.sleep(1.1)
    assert cache.get(key) is None
    cache.close()


def test_cache_concurrency_wal(tmp_path: Path) -> None:
    """Verify thread safety under concurrent reader and writer workers."""
    db_file = tmp_path / "cache.db"
    cache = SQLiteQueryCache(db_file)

    def writer(idx: int) -> None:
        key = SQLiteQueryCache.compute_key(f"threaded query {idx % 5}")
        cache.put(
            key,
            f"threaded query {idx % 5}",
            [_make_dummy_result(f"c{idx}", f"Note_{idx % 5}.md")],
            [f"Note_{idx % 5}.md"],
        )

    def reader(idx: int) -> None:
        key = SQLiteQueryCache.compute_key(f"threaded query {idx % 5}")
        cache.get(key)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = []
        for i in range(50):
            futures.append(ex.submit(writer, i))
            futures.append(ex.submit(reader, i))
        for f in futures:
            f.result()

    stats = cache.get_stats()
    assert stats.total_entries > 0
    cache.close()


def test_cache_manager_integration(tmp_path: Path) -> None:
    """Verify CacheManager coordinates get, put, invalidation, and clear."""
    vault = tmp_path / "vault"
    vault.mkdir()

    mgr = CacheManager(vault)
    res = [_make_dummy_result("c1", "A.md")]
    mgr.put("search q", "hybrid", res, limit=5)

    hit = mgr.get("search q", mode="hybrid", limit=5)
    assert hit is not None
    assert len(hit) == 1

    # Invalidate note
    evicted = mgr.invalidate_notes(["A.md"])
    assert evicted == 1
    assert mgr.get("search q", mode="hybrid", limit=5) is None

    # Invalidate all
    mgr.put("second q", "dense", res, limit=5)
    assert mgr.get("second q", mode="dense", limit=5) is not None
    mgr.invalidate_all()
    assert mgr.get("second q", mode="dense", limit=5) is None
    mgr.close()
