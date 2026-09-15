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
from . import build_pin
from .errors import error_to_status
from .lightmap import build_lightmap_atlas
from .scene import _BuiltGeometry, _LoadedTrunk, build_scene_payload, build_wireframe_payload
from .textures import build_atlas
from .watch import TrunkWatcher


def _scene_inputs(project):
    """`(search_files, index, defaults)` — the same trio `level photo --native`'s `render_shots`
    call site assembles (`cli/commands/level.py` ~732-745): the composed package search path, the
    schema-aware class/mover resolver, and the class-defaults resolver `build_scene` needs to light
    world BSP surfaces. Recomputed per request (cheap: no CSG solve here) rather than memoized on
    the app, so a `--project`'s on-disk games config can change without a `serve` restart.

    Caveat (shared-cache spec, accepted trade-off): once `_geometry_ref` is populated (by a
    Rebuild), a fresh `defaults`/`search_files` computed here has no effect on what a route
    actually returns — `_read_geometry()` serves straight from `_geometry_ref` without ever
    consulting this call's result. A games-config edit therefore needs a Rebuild (or a `serve`
    restart) to take effect, not just the next request. Accepted because games-config edits are
    rare (one-time project setup) next to trunk edits (this tool's whole reason to be cheap and
    frequent)."""
    user_config = config.load_user_config()
    search_files = config.composed_search_files(project, user_config)
    index = resources.mover_index(None, "uedcli serve", project=project)
    defaults = ClassDefaults(packages.schema_resolver(project, user_config))
    return search_files, index, defaults


def create_app(project, level: str, *, fault_route: bool = False) -> FastAPI:
    """Build the app for one project/level (fixed for the app's lifetime — Slice 1 has no level
    picker). `fault_route=True` mounts `/api/_boom` (raises a real domain error, for testing the
    exception handler) — never set outside tests; the shipped app never mounts it."""
    # Trunk watcher + WebSocket signal (sibling scene-cache spec, Task 4): AI edits hit the trunk
    # instantly; a rapid multi-verb burst coalesces to ONE push (`TrunkWatcher`'s debounce), not one
    # per verb. gui-explicit-rebuild spec §2 supersedes what that push MEANS: a `"changes_available"`
    # banner signal for an explicit Load, never a silent auto-reload (Task 3 below).
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

    async def _broadcast_changes_available() -> None:
        # Iterate a SNAPSHOT: `await ws.send_json` yields the event loop, and a client connecting
        # or disconnecting in that window mutates `connections` from a concurrently-running
        # coroutine (`ws_endpoint`) — iterating the live set directly raises "Set changed size
        # during iteration" and drops the whole broadcast (review finding, multi-viewer scenario).
        #
        # `type` is `"changes_available"`, not the old `"reload"` (gui-explicit-rebuild spec §2,
        # Task 3): the client's job is to show a banner/badge for an explicit Load, never to
        # silently auto-refetch — a real, tested wire-format change, not a silent regression.
        dead = set()
        for ws in list(connections):
            try:
                await ws.send_json({"type": "changes_available", "level": level})
            except Exception:
                dead.add(ws)
        connections.difference_update(dead)

    # Shared in-process scene cache (`dev/docs/board/to-build/uedcli-serve-share-one-in-process-
    # scene-cache/`): two independently-atomic slots -- `_trunk_ref` (Load-owned) and
    # `_geometry_ref` (Rebuild-owned, gui-explicit-rebuild spec §0). `_generation` guards against a
    # slow build in flight when an invalidation lands publishing a stale result over a state that's
    # since moved on (a real race a plain double-checked-locking sketch has no defense against --
    # see `_build_and_publish_geometry` below); bumped by `_on_trunk_settled` (the watcher settling),
    # which no longer clears either ref (Task 3) -- a mere trunk change on disk must not silently
    # discard an already-pinned Rebuild.
    _generation = [0]
    _trunk_lock = threading.Lock()
    _trunk_ref: list[_LoadedTrunk | None] = [None]
    _geometry_ref: list[_BuiltGeometry | None] = [None]
    # gui-explicit-rebuild spec §2: flipped by `_on_trunk_settled` when a trunk change lands after
    # the level is already open, cleared by an explicit Load (Task 5) -- the client's "changes
    # available" banner signal, never an auto-refetch trigger.
    _changes_available: list[bool] = [False]
    # `/status`'s `build_status` (spec §1/§4): WHY the geometry slot is empty, not just that it is --
    # `"no_build"` (never populated, no usable on-disk pointer either) vs `"evicted"` (an on-disk
    # pointer exists but Load's bootstrap check, Task 5, found no matching `preview_cache` entry) are
    # both "no geometry pinned" to `_read_geometry()`, but a client needs to tell them apart to show
    # the right message. `"built"` is derived from `_read_geometry() is not None`, never stored here
    # separately, so the two can't disagree.
    _build_status: list[str] = ["no_build"]

    def _bootstrap_geometry_if_empty() -> None:
        # gui-explicit-rebuild spec §4: "at Load (including the automatic initial one) ... populate
        # the in-memory pin FROM [the on-disk pointer] immediately" -- a `preview_cache` lookup, no
        # `build_scene()` call, so this is safe to run from BOTH `_get_trunk`'s own first-population
        # branch (the automatic initial Load) and the explicit `POST /load` route (Task 5's own
        # re-population step). The `_geometry_ref[0] is not None` guard makes it a no-op on any call
        # after the first -- in particular, a Rebuild that already populated the slot this session is
        # NEVER overwritten by a stale on-disk pointer (spec §1's last bullet). No lock: a
        # `preview_cache` lookup is fast, not a slow operation racing an invalidation the way
        # `build_scene()` is (plan's Open Questions #7 -- a narrow, accepted redundant-work risk on
        # truly concurrent first calls, not a correctness one: same pin either way).
        if _geometry_ref[0] is not None:
            return
        pin = build_pin.load_pointer(project, level)
        if pin is None:
            _build_status[0] = "no_build"
            return
        resolved = build_pin.resolve_pin(project, level, pin)
        if resolved is None:
            _build_status[0] = "evicted"   # spec §1's eviction caveat -- degrade, never raise
            return
        polys, texture_table, owners = resolved
        geom_hash, light_hash = pin
        _geometry_ref[0] = _BuiltGeometry(geom_hash=geom_hash, light_hash=light_hash, polys=polys,
                                          texture_table=texture_table, owners=owners)
        _build_status[0] = "built"

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
                # The AUTOMATIC INITIAL LOAD (spec §"Two independent axes"): this branch only ever
                # runs once per process (gated by `_trunk_ref[0] is None` above), exactly the "first
                # time this level is opened" moment the bootstrap-from-disk-pointer rule targets.
                _bootstrap_geometry_if_empty()
                return built

    def _read_geometry() -> _BuiltGeometry | None:
        # Pure read, NEVER calls `build_scene()` -- the whole point of the gui-explicit-rebuild spec
        # (§4): nothing may auto-solve as a side effect of a route being fetched, only an explicit
        # Rebuild (`_build_and_publish_geometry` below). No lock needed: a single list-index read of
        # a cell only ever replaced by one atomic assignment, same "single-reference-swap is atomic"
        # reasoning `_trunk_ref`/`_geometry_ref` already relied on before this split.
        return _geometry_ref[0]

    def _build_and_publish_geometry(search_files, index, defaults) -> _BuiltGeometry:
        # The ONLY function in this app that ever calls `build_scene()` -- reached ONLY from
        # `POST /rebuild` (gui-explicit-rebuild spec §3). Deliberately has no "already cached? return
        # early" short-circuit (unlike the sibling scene-cache spec's retired `_get_geometry`):
        # Rebuild always re-derives from the CURRENT trunk view, even though `build_scene`'s own
        # internal `preview_cache` lookup makes a same-hash repeat a cheap hit, not a genuine re-solve
        # (spec §3.3 "never accumulates" / plan Task 2's "always re-derives" test).
        #
        # `while True: ... continue` instead of a recursive retry: `solve_lock`/`_trunk_lock` are
        # plain `threading.Lock`s, not reentrant -- a recursive call's own `with solve_lock:` would
        # deadlock against the still-held outer lock. `continue` from inside a `with` block runs
        # `__exit__` (releasing the lock) before control reaches the top of the loop, so the retry's
        # re-acquisition never contends with itself. Same shape the sibling spec's `_get_trunk` uses.
        while True:
            with solve_lock:
                gen_before = _generation[0]
                trunk_state = _get_trunk(search_files, defaults)
                polys, texture_table, owners = _build_scene(
                    trunk_state.level, search_files, index, defaults=defaults, project=project,
                    level_name=level, visibility="editor")
                if _generation[0] != gen_before:
                    continue    # invalidated mid-build: discard, retry against the new state
                built = _BuiltGeometry(geom_hash=None, light_hash=None,   # OQ1 -- see scene.py
                                       polys=polys, texture_table=texture_table, owners=owners)
                _geometry_ref[0] = built
                _build_status[0] = "built"
                return built

    async def _on_trunk_settled() -> None:
        # gui-explicit-rebuild spec §0/§2: supersedes the sibling scene-cache spec's own TRIGGER,
        # not its slot shape -- Load owns `_trunk_ref`, Rebuild owns `_geometry_ref`, and a mere
        # trunk change settling on disk touches NEITHER any more (contrast the sibling spec's original
        # design, which cleared both here so the next request would auto-rebuild). Still bumps
        # `_generation[0]` -- repurposed from "guard an automatic rebuild" to "guard a Rebuild's
        # publish against a stale mid-flight solve" (`_build_and_publish_geometry`'s own generation
        # check) -- and flips `_changes_available[0]` for the client to show as a banner, never an
        # auto-refetch (spec §2, superseding the old silent `"reload"` push). Neither takes
        # `solve_lock` (event-loop-freeze hazard, same reasoning as `_broadcast_changes_available`).
        _generation[0] += 1
        _changes_available[0] = True
        await _broadcast_changes_available()

    watcher = TrunkWatcher(maps_root / level, _on_trunk_settled)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        watcher.start()
        try:
            yield
        finally:
            watcher.stop()

    app = FastAPI(lifespan=_lifespan)
    # Exposed on app.state for tests only (e.g. exercising `_broadcast_changes_available`'s
    # concurrent-mutation safety directly) — not part of the HTTP surface.
    app.state.connections = connections
    app.state.broadcast_changes_available = _broadcast_changes_available
    app.state.get_trunk = _get_trunk
    app.state.read_geometry = _read_geometry
    app.state.build_and_publish_geometry = _build_and_publish_geometry
    app.state.on_trunk_settled = _on_trunk_settled
    app.state.changes_available = _changes_available
    app.state.generation = _generation
    app.state.build_status = _build_status

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

    @app.get("/api/level/{level_name}/status")
    def status(level_name: str) -> dict:
        # gui-explicit-rebuild spec §1/§4: folds the Load axis's "changes available" signal and the
        # Rebuild axis's mode-gating signal into one route (this plan's own design choice, not a
        # spec mandate -- see the plan's Open Questions #3/#4) -- a client showing either banner
        # needs both at once anyway. `geometry_pinned` is the literal mode-gate condition ("no
        # in-memory geometry pin currently held" unlocks only wireframe); `build_status` is `"built"`
        # whenever `geometry_pinned` (derived, never stored separately, so the two can't disagree),
        # else whatever `_build_status[0]` last recorded by the bootstrap-from-disk-pointer check
        # (`_bootstrap_geometry_if_empty`, below) -- `"no_build"` (never populated, no usable pointer
        # either) or `"evicted"` (a pointer exists but names hashes `preview_cache` no longer holds).
        _require_level(level_name)
        pinned = _read_geometry() is not None
        return {
            "changes_available": _changes_available[0],
            "geometry_pinned": pinned,
            "build_status": "built" if pinned else _build_status[0],
        }

    @app.post("/api/level/{level_name}/load")
    def load(level_name: str) -> dict:
        # The explicit Load action (spec §2, P1: a plain refresh, no staging to conflict with).
        # Re-reads the trunk UNCONDITIONALLY (unlike `_get_trunk`'s own double-checked-lock gate,
        # which only populates an EMPTY slot) -- an explicit Load must see a change even when the
        # slot is already warm. `resolve_actor_sprites` rides along, same as `_get_trunk`'s own
        # build, since sprite resolution is Load-owned (spec §"Two independent axes").
        _require_level(level_name)
        search_files, _index, defaults = _scene_inputs(project)
        lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level)
        sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
        _trunk_ref[0] = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites)
        _changes_available[0] = False
        # Bootstrap-from-disk-pointer: a no-op if a Rebuild already populated the slot this session
        # (spec §1's last bullet -- an on-disk pointer must never overwrite an in-memory pin a
        # Rebuild already set), otherwise the same "unlock all modes with no Rebuild needed" check
        # the automatic initial Load already runs (spec test #8).
        _bootstrap_geometry_if_empty()
        return {"status": "ok"}

    # Sync `def` (NOT async): the blocking ~24s CSG+lighting solve runs in Starlette's threadpool,
    # not the event loop -- WS pushes, /health, and every other viewer stay responsive during it.
    @app.post("/api/level/{level_name}/rebuild")
    def rebuild(level_name: str) -> dict:
        # The explicit Rebuild action (spec §3): the ONLY route in this app that ever calls
        # `build_scene()`, via `_build_and_publish_geometry` -- which itself calls `_get_trunk()`
        # (performing the automatic initial Load if this is the very first route hit in the process
        # at all, spec §3 test #6: "no Load first" still works). In-memory only -- never touches
        # `build_pin`'s on-disk pointer file, which is Save-owned (P2, out of this plan's scope).
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        geometry = _build_and_publish_geometry(search_files, index, defaults)
        return {"status": "ok", "geom_hash": geometry.geom_hash, "light_hash": geometry.light_hash}

    # Sync `def` (NOT async): Starlette runs a sync route in its threadpool, so the blocking ~24s
    # solve never freezes the event loop (review finding — an async route would hang WS pushes,
    # /health, and every other viewer during a cold solve or a geometry-changing reload). None of
    # these three routes below ever triggers that solve any more (gui-explicit-rebuild spec §4) --
    # ONLY `POST /rebuild` above calls `_build_and_publish_geometry`; a route here reads whatever is
    # already pinned (possibly nothing) via `_read_geometry()`, which never builds.
    @app.get("/api/level/{level_name}/scene")
    def scene(level_name: str) -> dict:
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        trunk_state = _get_trunk(search_files, defaults)
        geometry = _read_geometry()
        if geometry is None:
            # Cold-open / no Rebuild yet: genuinely no solved geometry, not an error. Every actor's
            # own AUTHORED brush shape still rides on `SceneActor.brush` -- what lets wireframe mode
            # render with zero dependency on `_BuiltGeometry` (spec §4).
            payload = build_wireframe_payload(trunk_state, index, defaults)
        else:
            payload = build_scene_payload(trunk_state, geometry, index, defaults)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors],
            "geometry_pinned": geometry is not None,
        }

    @app.get("/api/level/{level_name}/atlas")
    def atlas(level_name: str) -> dict:
        # `_get_trunk` is the SAME shared cache `/scene` reads -- an unchanged trunk means this is a
        # cache hit, not a second decode path. With geometry pinned: `geometry.texture_table +
        # trunk_state.sprite_table`, in the same order `scene.py::build_scene_payload` uses when it
        # wraps `trunk.actor_sprites` into `SceneActor.sprite`, so a `tex_index` from /scene names
        # the same rect here. With NO geometry pinned: sprites are Load-owned (unaffected by
        # whether geometry exists -- a point actor's icon should still show in wireframe mode), so
        # the atlas is built from ONLY `trunk_state.sprite_table` (`build_wireframe_payload`'s own
        # sprites carry `tex_index` with no offset, matching this).
        _require_level(level_name)
        search_files, _index, defaults = _scene_inputs(project)
        trunk_state = _get_trunk(search_files, defaults)
        geometry = _read_geometry()
        texture_table = ((geometry.texture_table if geometry is not None else [])
                         + trunk_state.sprite_table)
        png_bytes, manifest, width, height = build_atlas(texture_table)
        return {
            "width": width,
            "height": height,
            "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    @app.get("/api/level/{level_name}/lightmap")
    def lightmap(level_name: str) -> dict:
        # Same shared cache as /scene and /atlas; only the poly list is needed here (the baked
        # lumel grids), the texture table is discarded. `intensity` is the atlas's global
        # multiplier scale — the client's `lightMapIntensity`. No geometry pinned: there are no lit
        # polys to pack -- `build_lightmap_atlas([])` already returns a valid degenerate response
        # (1x1 PNG, empty manifest, intensity 1.0 — the same shape a solved-but-unlit level gets),
        # so no special-casing is needed here.
        _require_level(level_name)
        geometry = _read_geometry()
        polys = geometry.polys if geometry is not None else []
        png_bytes, manifest, width, height, intensity = build_lightmap_atlas(polys)
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
