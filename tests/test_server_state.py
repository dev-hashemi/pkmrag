"""Unit tests for ServerState and dynamic DB lifecycle management."""

from __future__ import annotations

from pathlib import Path

from pkmrag.mcp.events import EventBroadcaster
from pkmrag.mcp.server_state import ServerState


def test_server_state_initial_unindexed(tmp_path: Path) -> None:
    broadcaster = EventBroadcaster()
    state = ServerState(tmp_path, broadcaster)

    assert not state.is_indexed()
    assert state.graph_store is None
    assert state.vector_store is None
    assert state.active_job is None

    health = state.get_health_status(token_enabled=True)
    assert health["status"] == "healthy"
    assert health["is_indexed"] is False
    assert health["auth_enabled"] is True
    assert health["active_job"] is None


def test_server_state_job_tracking(tmp_path: Path) -> None:
    broadcaster = EventBroadcaster()
    state = ServerState(tmp_path, broadcaster)

    state.set_job(
        job_type="ingest",
        phase="scanning",
        cur=10,
        total=100,
        percent=10,
        message="Scanning files",
    )
    assert state.active_job is not None
    assert state.active_job["type"] == "ingest"
    assert state.active_job["percent"] == 10

    state.update_job(phase="embedding", cur=50, total=100, percent=50, message="Embedding notes")
    assert state.active_job["phase"] == "embedding"
    assert state.active_job["percent"] == 50

    health = state.get_health_status()
    assert health["active_job"] is not None
    assert health["active_job"]["type"] == "ingest"
    assert health["active_job"]["percent"] == 50

    state.clear_job()
    assert state.active_job is None
    assert state.get_health_status()["active_job"] is None
