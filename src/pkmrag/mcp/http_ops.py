"""Operational REST route handlers for vault ingestion, AI discovery, and settings."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pkmrag.discovery import GapDiscoveryEngine
from pkmrag.inference.factory import resolve_provider
from pkmrag.ingest import IngestPipeline
from pkmrag.mcp.events import EventBroadcaster
from pkmrag.vault_config import VaultRuntimeConfig, load_vault_config, save_vault_config

if TYPE_CHECKING:
    from pkmrag.mcp.server_state import ServerState


def register_ops_routes(
    app: Starlette,
    vault_path: Path,
    broadcaster: EventBroadcaster,
    server_state: ServerState,
) -> None:
    """Register operational REST endpoints for ingestion, AI discovery, and LLM config."""

    async def ingest_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        rebuild = bool(body.get("rebuild", False))
        dialect = str(body.get("dialect", "auto"))
        target = str(body.get("target", "all"))
        loop = asyncio.get_running_loop()

        server_state.set_job(
            job_type="ingest",
            phase="initializing",
            cur=0,
            total=100,
            percent=0,
            message="Starting vault ingestion...",
        )

        def _run_ingest() -> None:
            pipeline = IngestPipeline(
                vault_path=vault_path,
                rebuild=rebuild,
                dialect=dialect,
                target=target,
            )

            def _on_prog(phase: str, cur: int, tot: int) -> None:
                percent = int(round((cur / max(tot, 1)) * 100))
                msg = f"{phase.capitalize()} ({cur}/{tot})"
                server_state.update_job(
                    phase=phase, cur=cur, total=tot, percent=percent, message=msg
                )
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "ingest_progress",
                        {
                            "phase": phase,
                            "cur": cur,
                            "total": tot,
                            "percent": percent,
                            "message": msg,
                        },
                    ),
                    loop,
                )

            try:
                stats = pipeline.run(progress_callback=_on_prog)
                server_state.reload_stores()
                server_state.clear_job()
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "ingest_complete",
                        {"status": "ok", "stats": stats.model_dump()},
                    ),
                    loop,
                )
            except Exception as exc:
                server_state.clear_job()
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "ingest_error",
                        {"status": "error", "message": str(exc)},
                    ),
                    loop,
                )

        asyncio.create_task(asyncio.to_thread(_run_ingest))
        return JSONResponse(
            {
                "status": "started",
                "message": "Vault ingestion started in background.",
                "rebuild": rebuild,
            }
        )

    async def discover_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        threshold = float(body["threshold"]) if "threshold" in body else None
        limit = int(body.get("limit", 20))
        dry_run = bool(body.get("dry_run", False))
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
                                "desc": desc,
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
                    on_progress=_on_prog,
                )
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
                        },
                    ),
                    loop,
                )
            except Exception as exc:
                server_state.clear_job()
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast(
                        "discover_error",
                        {"status": "error", "message": str(exc)},
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
            }
        )

    async def llm_test_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        provider = resolve_provider(
            vault_path=vault_path,
            provider_type=body.get("provider"),
            model=body.get("model"),
            base_url=body.get("base_url"),
            api_key=body.get("api_key"),
        )

        success, message, latency_ms = await asyncio.to_thread(provider.test_connection)
        return JSONResponse(
            {
                "success": success,
                "message": message,
                "latency_ms": latency_ms,
                "model": provider.model,
                "provider": provider.name,
            }
        )

    async def settings_get_handler(request: Request) -> Response:
        cfg = load_vault_config(vault_path)
        return JSONResponse(cfg.model_dump())

    async def settings_post_handler(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json() if await request.body() else {}
        except Exception:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

        existing = load_vault_config(vault_path).model_dump()
        for k, v in body.items():
            if v is not None and k in existing:
                existing[k] = v

        try:
            updated_cfg = VaultRuntimeConfig.model_validate(existing)
            save_vault_config(vault_path, updated_cfg)
            return JSONResponse(updated_cfg.model_dump())
        except Exception as e:
            return JSONResponse({"error": f"Validation error: {e}"}, status_code=400)

    app.add_route("/api/v1/ingest", ingest_handler, methods=["POST"])
    app.add_route("/api/v1/discover", discover_handler, methods=["POST"])
    app.add_route("/api/v1/llm/test", llm_test_handler, methods=["POST"])
    app.add_route("/api/v1/settings", settings_get_handler, methods=["GET"])
    app.add_route("/api/v1/settings", settings_post_handler, methods=["POST"])
