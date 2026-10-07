"""Thread-safe dynamic server state managing DB stores, active background jobs, and health."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from pkmrag import __version__
from pkmrag.cache import CacheManager
from pkmrag.config import settings
from pkmrag.graph.paths import get_vault_overview
from pkmrag.graph.store import GraphStore
from pkmrag.mcp.events import EventBroadcaster
from pkmrag.search.service import SearchService
from pkmrag.search.vector_store import VectorStore

logger = logging.getLogger("pkmrag.mcp.state")


class ServerState:
    """Manages dynamic graph/vector stores and tracks active asynchronous background jobs."""

    def __init__(self, vault_path: Path, broadcaster: EventBroadcaster) -> None:
        self.vault_path = vault_path
        self.broadcaster = broadcaster
        self._lock = threading.Lock()
        self.graph_store: Optional[GraphStore] = None
        self.vector_store: Optional[VectorStore] = None
        self.cache_manager = CacheManager(vault_path)
        self.search_service: Optional[SearchService] = None
        self.active_job: Optional[dict[str, Any]] = None
        self.reload_stores()

    def is_indexed(self) -> bool:
        """Check whether deterministic graph and semantic vector stores exist on disk."""
        db_dir = settings.get_db_dir(self.vault_path)
        vec_dir = settings.get_vector_dir(self.vault_path)
        return db_dir.exists() and vec_dir.exists()

    def reload_stores(self) -> None:
        """Safely re-open database stores and search service upon ingest completion."""
        with self._lock:
            db_dir = settings.get_db_dir(self.vault_path)
            vec_dir = settings.get_vector_dir(self.vault_path)

            if self.graph_store is not None:
                try:
                    self.graph_store.close()
                except Exception as e:
                    logger.debug("Error closing old graph store: %s", e)
                self.graph_store = None

            self.graph_store = GraphStore(db_dir, read_only=False) if db_dir.exists() else None
            self.vector_store = VectorStore(vec_dir) if vec_dir.exists() else None
            self.search_service = SearchService(
                self.vault_path,
                graph_store=self.graph_store,
                vector_store=self.vector_store,
                cache_manager=self.cache_manager,
            )
            logger.info("ServerState stores reloaded. Indexed: %s", self.is_indexed())

    def set_job(
        self,
        job_type: str,
        phase: str = "starting",
        cur: int = 0,
        total: int = 100,
        percent: int = 0,
        message: str = "",
    ) -> None:
        """Register or start an active background job."""
        with self._lock:
            self.active_job = {
                "type": job_type,
                "phase": phase,
                "cur": cur,
                "total": total,
                "percent": percent,
                "message": message,
                "started_at": time.time(),
            }

    def update_job(
        self,
        phase: Optional[str] = None,
        cur: Optional[int] = None,
        total: Optional[int] = None,
        percent: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """Update live progress metrics of the active background job."""
        with self._lock:
            if not self.active_job:
                return
            if phase is not None:
                self.active_job["phase"] = phase
            if cur is not None:
                self.active_job["cur"] = cur
            if total is not None:
                self.active_job["total"] = total
            if percent is not None:
                self.active_job["percent"] = percent
            if message is not None:
                self.active_job["message"] = message

    def clear_job(self) -> None:
        """Clear active background job state on completion or failure."""
        with self._lock:
            self.active_job = None

    def get_health_status(self, token_enabled: bool = False) -> dict[str, Any]:
        """Produce comprehensive health and readiness telemetry for the HTTP health probe."""
        indexed = self.is_indexed()
        stats: dict[str, int] = {}
        if indexed and self.graph_store is not None:
            try:
                overview = get_vault_overview(self.graph_store.conn, limit=1)
                stats = {
                    "notes": overview.total_notes,
                    "links": overview.total_links,
                    "tags": overview.total_tags,
                }
            except Exception:
                pass

        with self._lock:
            active_job_copy = dict(self.active_job) if self.active_job else None

        return {
            "status": "healthy",
            "version": __version__,
            "vault": self.vault_path.name,
            "vault_path": str(self.vault_path),
            "transport": "sse",
            "auth_enabled": token_enabled,
            "is_indexed": indexed,
            "active_job": active_job_copy,
            "stats": stats,
        }
