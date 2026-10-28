"""HTTP route handlers for AI gap discovery execution and token estimation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pkmrag.discovery import GapDiscoveryEngine
from pkmrag.mcp.events import EventBroadcaster

if TYPE_CHECKING:
    from pkmrag.mcp.server_state import ServerState


def register_discover_routes(
    app: Starlette,
    vault_path: Path,
    broadcaster: EventBroadcaster,
    server_state: ServerState,
) -> None:
    """Register REST endpoints for discovery estimation and asynchronous execution."""

    async def discover_estimate_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        threshold = float(body["threshold"]) if "threshold" in body else None
        limit = int(body.get("limit", 20))
        note_path = body.get("note_path") or body.get("focus_path")
        provider_type = body.get("provider")
        model = body.get("model")
        base_url = body.get("base_url")
        api_key = body.get("api_key")

        engine = GapDiscoveryEngine(vault_path, read_only=True)
        try:
            estimate = await asyncio.to_thread(
                engine.estimate,
                similarity_threshold=threshold,
                focus_path=note_path,
                limit=limit,
                provider_type=provider_type,
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
            return JSONResponse(estimate.model_dump())
        except Exception as exc:
            return JSONResponse({"error": f"Estimation failed: {exc}"}, status_code=500)
        finally:
            engine.close()

    async def discover_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        threshold = float(body["threshold"]) if "threshold" in body else None
        limit = int(body.get("limit", 20))
        dry_run = bool(body.get("dry_run", False))
        note_path = body.get("note_path") or body.get("focus_path")
        provider_type = body.get("provider")
        model = body.get("model")
        base_url = body.get("base_url")
        api_key = body.get("api_key")
        loop = asyncio.get_running_loop()

        server_state.set_job(
            job_type="discover",
            phase="initializing",
            cur=0,
            total=100,
            percent=0,
            message="Starting AI discovery...",
            note_path=note_path,
        )

        def _run_discovery() -> None:
            engine = GapDiscoveryEngine(vault_path)
            try:

                def _on_prog(cur: int, tot: int, desc: str) -> None:
                    percent = int(round((cur / max(tot, 1)) * 100))
                    server_state.update_job(
                        phase="discovery",
                        cur=cur,
                        total=tot,
                        percent=percent,
                        message=desc,
                    )
                    asyncio.run_coroutine_threadsafe(
                        broadcaster.broadcast(
                            "discover_progress",
                            {
                                "phase": "discovery",
                                "cur": cur,
                                "total": tot,
                                "percent": percent,
                                "message": desc,
                                "desc": desc,
                                "note_path": note_path,
                            },
                        ),
                        loop,
                    )

                cands, infs, stats = engine.discover(
                    similarity_threshold=threshold,
                    limit=limit,
                    dry_run=dry_run,
                    provider_type=provider_type,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    focus_path=note_path,
                    on_progress=_on_prog,
                )
                server_state.record_discovery(note_path=note_path)
                server_state.reload_stores()
                server_state.clear_job()
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "discover_complete",
                        {
                            "status": "ok",
                            "candidates_count": len(cands),
                            "inferred_count": len(infs),
                            "duration_ms": stats.duration_ms,
                            "note_path": note_path,
                        },
                    ),
                    loop,
                )
            except Exception as exc:
                server_state.clear_job()
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "discover_error",
                        {"status": "error", "message": str(exc), "note_path": note_path},
                    ),
                    loop,
                )
            finally:
                engine.close()

        asyncio.create_task(asyncio.to_thread(_run_discovery))
        return JSONResponse(
            {
                "status": "started",
                "message": "AI semantic gap discovery started in background.",
                "note_path": note_path,
            }
        )

    app.add_route("/api/v1/discover", discover_handler, methods=["POST"])
    app.add_route("/api/v1/discover/estimate", discover_estimate_handler, methods=["POST"])
