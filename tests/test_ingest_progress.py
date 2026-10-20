"""Tests for the structured ingest stage contract shared with the Obsidian plugin."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from pkmrag.ingest.pipeline import IngestPipeline
from pkmrag.mcp.events import EventBroadcaster
from pkmrag.mcp.http_ops import _progress_message
from pkmrag.mcp.http_server import create_http_app
from pkmrag.mcp.server_state import ServerState
from pkmrag.models import IngestProgress, IngestStage

_MEGABYTE = 1024 * 1024


class _StubEmbedder:
    """Embedding provider stub that never touches the network."""

    def __init__(self, cached: bool = True) -> None:
        self._cached = cached
        self.warm_up_calls = 0

    @property
    def model_name(self) -> str:
        return "BAAI/bge-small-en-v1.5"

    @property
    def dimension(self) -> int:
        return 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 384 for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [0.0] * 384

    def model_is_cached(self) -> bool:
        return self._cached

    def warm_up(self, progress_callback: Optional[Any] = None) -> None:
        self.warm_up_calls += 1
        if progress_callback is not None and not self._cached:
            progress_callback(50 * _MEGABYTE, 64 * _MEGABYTE)


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Alpha.md").write_text("# Alpha\nLinks to [[Beta]]. #tag")
    (vault / "Beta.md").write_text("# Beta\nPlain note.")
    return vault


def test_pipeline_reports_structured_stages(tmp_path: Path) -> None:
    """Verify the pipeline reports scan, graph and vector stages."""
    vault = _make_vault(tmp_path)
    events: list[IngestProgress] = []

    pipeline = IngestPipeline(vault, embedder=_StubEmbedder())
    pipeline.run(progress_callback=events.append)

    stages = [event.stage for event in events]
    assert stages[0] == IngestStage.SCAN
    assert IngestStage.GRAPH in stages
    assert IngestStage.VECTOR in stages
    assert all(event.unit == "items" for event in events)


def test_pipeline_skips_download_stage_when_model_is_cached(tmp_path: Path) -> None:
    """Verify a cached model never announces a download stage."""
    vault = _make_vault(tmp_path)
    events: list[IngestProgress] = []

    embedder = _StubEmbedder(cached=True)
    pipeline = IngestPipeline(vault, embedder=embedder)
    pipeline.run(progress_callback=events.append)

    assert IngestStage.MODEL_DOWNLOAD not in [event.stage for event in events]
    assert embedder.warm_up_calls == 1


def test_pipeline_reports_model_download_in_bytes(tmp_path: Path) -> None:
    """Verify an uncached model reports byte-based download progress."""
    vault = _make_vault(tmp_path)
    events: list[IngestProgress] = []

    pipeline = IngestPipeline(vault, embedder=_StubEmbedder(cached=False))
    pipeline.run(progress_callback=events.append)

    downloads = [event for event in events if event.stage == IngestStage.MODEL_DOWNLOAD]
    assert downloads
    assert all(event.unit == "bytes" for event in downloads)
    assert downloads[0].cur == 0
    assert downloads[-1].cur == 50 * _MEGABYTE
    assert downloads[-1].total == 64 * _MEGABYTE


def test_progress_message_preserves_the_model_name() -> None:
    """Verify the rendered message keeps the model name casing intact."""
    update = IngestProgress(
        stage=IngestStage.MODEL_DOWNLOAD,
        phase="Downloading embedding model (BAAI/bge-small-en-v1.5)",
        cur=32 * _MEGABYTE,
        total=64 * _MEGABYTE,
        unit="bytes",
    )
    message = _progress_message(update)
    assert "BAAI/bge-small-en-v1.5" in message
    assert "32.0 MB / 64.0 MB" in message


def test_progress_message_counts_items() -> None:
    """Verify item based stages report the item counter."""
    update = IngestProgress(
        stage=IngestStage.GRAPH,
        phase="Ingesting graph notes",
        cur=1,
        total=2,
    )
    assert _progress_message(update) == "Ingesting graph notes (1/2)"


def test_server_state_tracks_the_stage(tmp_path: Path) -> None:
    """Verify the active job exposes the stage through the health payload."""
    state = ServerState(tmp_path, EventBroadcaster())

    state.set_job(job_type="ingest", stage=IngestStage.SCAN.value, phase="initializing")
    assert state.active_job is not None
    assert state.active_job.stage == "scan"

    state.update_job(stage=IngestStage.MODEL_DOWNLOAD.value, unit="bytes", percent=42)
    health = state.get_health_status()
    assert health["active_job"] is not None
    assert health["active_job"]["stage"] == "model_download"
    assert health["active_job"]["unit"] == "bytes"
    assert health["active_job"]["percent"] == 42


def test_ingest_progress_event_carries_the_stage(tmp_path: Path) -> None:
    """Verify the broadcast ingest_progress payload exposes the structured stage."""
    vault = _make_vault(tmp_path)
    app = create_http_app(vault, token="test_token")

    with patch.object(EventBroadcaster, "broadcast", new_callable=AsyncMock) as broadcast:
        client = TestClient(app)
        headers = {"Authorization": "Bearer test_token"}
        resp = client.post("/api/v1/ingest", json={"target": "graph"}, headers=headers)
        assert resp.status_code == 200

        deadline = time.time() + 30
        payloads: list[dict[str, Any]] = []
        while time.time() < deadline:
            payloads = [
                call.args[1]
                for call in broadcast.call_args_list
                if call.args and call.args[0] == "ingest_progress"
            ]
            if payloads:
                break
            time.sleep(0.1)

    assert payloads, "no ingest_progress event was broadcast"
    first = payloads[0]
    assert first["stage"] == IngestStage.SCAN.value
    assert first["unit"] == "items"
    assert first["phase"] == "Scanning vault files"
