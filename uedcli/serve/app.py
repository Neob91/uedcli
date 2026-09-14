"""FastAPI app factory for `uedcli serve` — the read-only HTTP/WS surface over the model-side
library (spec, "Architecture"). Binds localhost only (enforced by the `serve` verb, not here);
holds all domain logic — the client draws only what these routes hand it."""
from __future__ import annotations

import base64
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.requests import Request

from .. import config, packages, trunk
from ..classdefaults import ClassDefaults
from ..cli import resources
from ..cli.errors import CommandError
from ..preview_native import build_scene as _build_scene
from .errors import error_to_status
from .scene import build_scene_payload
from .textures import build_atlas
from .watch import TrunkWatcher


def _scene_inputs(project):
    """`(search_files, index, defaults)` — the same trio `level photo --native`'s `render_shots`
    call site assembles (`cli/commands/level.py` ~732-745): the composed package search path, the
    schema-aware class/mover resolver, and the class-defaults resolver `build_scene` needs to light
    world BSP surfaces. Recomputed per request (cheap: no CSG solve here) rather than memoized on
    the app, so a `--project`'s on-disk games config can change without a `serve` restart."""
    user_config = config.load_user_config()
    search_files = config.composed_search_files(project, user_config)
    index = resources.mover_index(None, "uedcli serve", project=project)
    defaults = ClassDefaults(packages.schema_resolver(project, user_config))
    return search_files, index, defaults


def create_app(project, level: str, *, fault_route: bool = False) -> FastAPI:
    """Build the app for one project/level (fixed for the app's lifetime — Slice 1 has no level
    picker). `fault_route=True` mounts `/api/_boom` (raises a real domain error, for testing the
    exception handler) — never set outside tests; the shipped app never mounts it."""
    # Trunk watcher + WebSocket live-reload (Task 4): AI edits hit the trunk instantly; a rapid
    # multi-verb burst coalesces to ONE reload push (`TrunkWatcher`'s debounce), not one per verb
    # (spec, "File watcher → live reload").
    connections: set[WebSocket] = set()
    # Serializes the ~24s CSG solve so the client's concurrent /scene + /atlas fetches don't both
    # cold-solve and race the `preview_cache` write: the first solves+caches under the lock, the
    # second blocks then reads the cache. Held only around the solve, in a threadpool thread (the
    # routes are sync `def`), so the event loop — WS pushes, /api/health, other viewers — stays free.
    solve_lock = threading.Lock()

    maps_root = Path(config.project_maps_dir(project))

    def _require_level(level_name: str) -> None:
        # Route param validated like the `serve` verb's own up-front check, so a bad/nonexistent name
        # returns a clean "level not found" (exit-2-equivalent 422) rather than falling through to
        # build_scene's misleading "no CSG brush actors" (no-half-answer rule). Single-segment guards
        # against a name that isn't a real level dir (traversal is already impossible — Starlette's
        # {level_name} is [^/]+ and uvicorn pre-decodes %2F).
        if "/" in level_name or level_name in ("", ".", "..") or not (maps_root / level_name).is_dir():
            raise CommandError(f"level not found: {level_name!r}")

    async def _broadcast_reload() -> None:
        # Iterate a SNAPSHOT: `await ws.send_json` yields the event loop, and a client connecting
        # or disconnecting in that window mutates `connections` from a concurrently-running
        # coroutine (`ws_endpoint`) — iterating the live set directly raises "Set changed size
        # during iteration" and drops the whole broadcast (review finding, multi-viewer scenario).
        dead = set()
        for ws in list(connections):
            try:
                await ws.send_json({"type": "reload", "level": level})
            except Exception:
                dead.add(ws)
        connections.difference_update(dead)

    watcher = TrunkWatcher(maps_root / level, _broadcast_reload)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        watcher.start()
        try:
            yield
        finally:
            watcher.stop()

    app = FastAPI(lifespan=_lifespan)
    # Exposed on app.state for tests only (e.g. exercising `_broadcast_reload`'s concurrent-
    # mutation safety directly) — not part of the HTTP surface.
    app.state.connections = connections
    app.state.broadcast_reload = _broadcast_reload

    @app.exception_handler(Exception)
    async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # No Python exception reaches the user (CLAUDE.md): every raised exception — classified or
        # not — renders as structured JSON, never a bare traceback.
        try:
            status, message = error_to_status(exc)
        except TypeError:
            status, message = 500, "internal error"
        return JSONResponse(status_code=status, content={"error": message})

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "level": level}

    # Sync `def` (NOT async): Starlette runs a sync route in its threadpool, so the blocking ~24s
    # solve never freezes the event loop (review finding — an async route would hang WS pushes,
    # /health, and every other viewer during a cold solve or a geometry-changing reload).
    @app.get("/api/level/{level_name}/scene")
    def scene(level_name: str) -> dict:
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        with solve_lock:
            payload = build_scene_payload(project, level_name, index, defaults, search_files)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors],
        }

    @app.get("/api/level/{level_name}/atlas")
    def atlas(level_name: str) -> dict:
        # The SAME cached solve the scene route uses (`build_scene` keyed on project/level_name is
        # a `preview_cache` hit here) — never a second decode path; only its `texture_table` half
        # is needed, so the payload's polys are discarded. `solve_lock` makes a concurrent /scene
        # cold-solve+cache first, so this becomes the cache hit rather than a second cold solve.
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        lvl, *_ = trunk.read_level_with_bodies(maps_root / level_name)
        with solve_lock:
            _polys, texture_table = _build_scene(lvl, search_files, index, defaults=defaults,
                                                 project=project, level_name=level_name)
        png_bytes, manifest, width, height = build_atlas(texture_table)
        return {
            "width": width,
            "height": height,
            "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    if fault_route:
        @app.get("/api/_boom")
        async def _boom():
            raise CommandError("Actor not found: Foo")

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        connections.add(websocket)
        try:
            while True:
                await websocket.receive_text()   # the client sends nothing meaningful; just detects disconnect
        except WebSocketDisconnect:
            pass
        finally:
            connections.discard(websocket)   # also drop on any other receive error, not just clean disconnect

    return app
