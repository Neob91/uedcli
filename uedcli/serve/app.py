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
from ..preview_native import resolve_actor_sprites
from .errors import error_to_status
from .lightmap import build_lightmap_atlas
from .scene import _BuiltGeometry, _LoadedTrunk, build_scene_payload
from .textures import build_atlas
from .watch import TrunkWatcher


def _scene_inputs(project):
    """`(search_files, index, defaults)` — the same trio `level photo --native`'s `render_shots`
    call site assembles (`cli/commands/level.py` ~732-745): the composed package search path, the
    schema-aware class/mover resolver, and the class-defaults resolver `build_scene` needs to light
    world BSP surfaces. Recomputed per request (cheap: no CSG solve here) rather than memoized on
    the app, so a `--project`'s on-disk games config can change without a `serve` restart.

    Caveat (shared-cache spec, accepted trade-off): once `_get_geometry()`'s cache is warm, a
    fresh `defaults`/`search_files` computed here has no effect on what a route actually returns —
    a warm build is served straight from `_geometry_ref` without ever consulting this call's
    result. A games-config edit therefore needs an unrelated trunk change (or a `serve` restart) to
    take effect, not just the next request. Accepted because games-config edits are rare (one-time
    project setup) next to trunk edits (this tool's whole reason to be cheap and frequent)."""
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
        # {level_name} is [^/]+ and uvicorn pre-decodes %2F). `level_name != level`: `create_app`
        # fixes ONE level for the app's lifetime (no picker), and with the shared trunk/geometry
        # cache below keyed on nothing but that fixed `level`, a syntactically-valid-but-different
        # level name would otherwise silently serve THIS level's cached data instead of its own
        # (shared-cache spec's `_require_level` finding).
        if ("/" in level_name or level_name in ("", ".", "..") or level_name != level
                or not (maps_root / level_name).is_dir()):
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

    # Shared in-process scene cache (`dev/docs/board/to-build/uedcli-serve-share-one-in-process-
    # scene-cache/`): two independently-atomic slots so `/scene`, `/atlas`, `/lightmap` do one
    # trunk-read + one `build_scene`/`resolve_actor_sprites` call each per settled trunk state,
    # instead of each route redoing all of it independently. `_generation` guards against a slow
    # build in flight when an invalidation lands publishing a stale result over the fresh `None`
    # (a real race a plain double-checked-locking sketch has no defense against — see `_get_geometry`
    # below); bumped by `_on_trunk_settled` in the SAME step it clears both refs.
    _generation = [0]
    _trunk_lock = threading.Lock()
    _trunk_ref: list[_LoadedTrunk | None] = [None]
    _geometry_ref: list[_BuiltGeometry | None] = [None]

    def _get_trunk(search_files, defaults) -> _LoadedTrunk:
        # NOTE on parameters: the plan's own illustrative pseudocode named this `_get_trunk(search_files,
        # index)` and called `resolve_actor_sprites(lvl, index, search_files)` -- but the REAL
        # `resolve_actor_sprites` signature (`preview_native.py:380`) is `(level, search_files,
        # class_defaults)`, and `class_defaults` (a `ClassDefaults`, with `.for_class`) is not
        # interchangeable with `index` (a `ClassIndex`, no `.for_class` -- would raise
        # `AttributeError` on the very first call). Fixed to the verified real signature; flagged in
        # the build report rather than silently carried over.
        while True:
            cached = _trunk_ref[0]
            if cached is not None:
                return cached
            with _trunk_lock:
                cached = _trunk_ref[0]
                if cached is not None:
                    return cached
                gen_before = _generation[0]
                lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level)
                sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
                if _generation[0] != gen_before:
                    continue    # invalidated mid-build: discard, loop back and retry from the top
                built = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites)
                _trunk_ref[0] = built
                return built

    def _get_geometry(search_files, index, defaults) -> _BuiltGeometry:
        # `while True: ... continue` instead of the plan's illustrative recursive `return
        # _get_geometry()`: `solve_lock`/`_trunk_lock` are plain `threading.Lock`s, not reentrant --
        # a recursive call's own `with solve_lock:` would deadlock against the still-held outer lock
        # (the outer `with` doesn't release until the recursive call's entire body, including that
        # nested acquisition, has already returned). `continue` from inside a `with` block runs
        # `__exit__` (releasing the lock) before control reaches the top of the loop, so the retry's
        # re-acquisition never contends with itself. Same shape as `_get_trunk` above.
        while True:
            cached = _geometry_ref[0]
            if cached is not None:
                return cached
            with solve_lock:
                cached = _geometry_ref[0]
                if cached is not None:
                    return cached
                gen_before = _generation[0]
                trunk_state = _get_trunk(search_files, defaults)
                polys, texture_table, owners = _build_scene(
                    trunk_state.level, search_files, index, defaults=defaults, project=project,
                    level_name=level, visibility="editor")
                if _generation[0] != gen_before:
                    continue    # invalidated mid-build (during the trunk fetch OR the build itself)
                built = _BuiltGeometry(geom_hash=None, light_hash=None,   # OQ1 -- see scene.py
                                       polys=polys, texture_table=texture_table, owners=owners)
                _geometry_ref[0] = built
                return built

    async def _on_trunk_settled() -> None:
        # Order matters (spec, "Invalidation ordering"): bump the generation and clear BOTH slots
        # before broadcasting. The bump/clear order between themselves doesn't matter (no lock, no
        # other code reads `_generation` except a build checking it after its own slow work) -- what
        # matters is that all three happen before the WS broadcast, and that none of them takes
        # `solve_lock` (event-loop-freeze hazard, same reasoning as `_broadcast_reload` above). The
        # bump is what makes a build already in flight when this fires discard itself instead of
        # publishing stale data (the generation guard in `_get_trunk`/`_get_geometry` above).
        _generation[0] += 1
        _trunk_ref[0] = None
        _geometry_ref[0] = None
        await _broadcast_reload()

    watcher = TrunkWatcher(maps_root / level, _on_trunk_settled)

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
    app.state.get_trunk = _get_trunk
    app.state.get_geometry = _get_geometry
    app.state.on_trunk_settled = _on_trunk_settled

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
        trunk_state = _get_trunk(search_files, defaults)
        geometry = _get_geometry(search_files, index, defaults)
        payload = build_scene_payload(trunk_state, geometry, index, defaults)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors],
        }

    @app.get("/api/level/{level_name}/atlas")
    def atlas(level_name: str) -> dict:
        # `_get_trunk`/`_get_geometry` are the SAME shared cache `/scene` reads -- an unchanged
        # trunk means this is a cache hit, not a second decode path. Only `geometry.texture_table`
        # is needed here, plus `trunk_state.sprite_table` (point-actor sprite billboards) -- appended
        # in the same order `scene.py::build_scene_payload` uses when it wraps `trunk.actor_sprites`
        # into `SceneActor.sprite`, so a `tex_index` from /scene names the same rect here. Appending
        # it is what keeps this route's OWN data unchanged by the refactor (today's /atlas already
        # returns sprite rects via its own `resolve_actor_sprites` call; dropping the append would be
        # the actual regression, not adding it).
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        trunk_state = _get_trunk(search_files, defaults)
        geometry = _get_geometry(search_files, index, defaults)
        texture_table = geometry.texture_table + trunk_state.sprite_table
        png_bytes, manifest, width, height = build_atlas(texture_table)
        return {
            "width": width,
            "height": height,
            "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    @app.get("/api/level/{level_name}/lightmap")
    def lightmap(level_name: str) -> dict:
        # Same shared cache as /scene and /atlas (a warm `_get_geometry()` never re-solves); only
        # its poly list is needed here (the baked lumel grids), the texture table is discarded.
        # `intensity` is the atlas's global multiplier scale — the client's `lightMapIntensity`.
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        geometry = _get_geometry(search_files, index, defaults)
        png_bytes, manifest, width, height, intensity = build_lightmap_atlas(geometry.polys)
        return {
            "width": width,
            "height": height,
            "intensity": intensity,
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
