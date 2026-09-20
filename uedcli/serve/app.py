"""FastAPI app factory for `uedcli serve` — the read-only HTTP/WS surface over the model-side
library (spec, "Architecture"). Binds localhost only (enforced by the `serve` verb, not here);
holds all domain logic — the client draws only what these routes hand it."""
from __future__ import annotations

import base64
import logging
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
from ..preview_native import resolve_actor_sprites, resolve_mesh_scene_polys, resolve_mover_scene_polys
from . import build_pin
from .errors import error_to_status
from .levels import levels_payload
from .lightmap import build_lightmap_atlas
from .scene import (
    _BuiltGeometry,
    _LoadedTrunk,
    ScenePayload,
    _resolve_hidden_ed,
    build_scene_payload,
    build_wireframe_payload,
    filtered_geometry_polys,
)
from .textures import build_atlas
from .watch import TrunkWatcher

logger = logging.getLogger(__name__)


def _scene_inputs(project):
    """`(search_files, index, defaults)` — the same trio `level photo --native`'s `render_shots`
    call site assembles (`cli/commands/level.py` ~732-745): the composed package search path, the
    schema-aware class/mover resolver, and the class-defaults resolver `build_scene` needs to light
    world BSP surfaces. Recomputed per request (cheap: no CSG solve here) rather than memoized on
    the app, so a `--project`'s on-disk games config can change without a `serve` restart.

    Caveat (shared-cache spec, accepted trade-off): once `_geometry_ref` is populated (by a
    Rebuild) or `_payload_ref` is warm, a fresh `defaults`/`search_files`/`index` computed here has
    no effect on what a route actually returns — `_read_geometry()`/`_get_payload()` serve straight
    from their cached refs without ever consulting this call's result. A games-config edit
    therefore needs a Rebuild (or a `serve` restart) to take effect, not just the next request.
    Accepted because games-config edits are rare (one-time project setup) next to trunk edits (this
    tool's whole reason to be cheap and frequent). This caveat used to be FALSE for `/scene`
    specifically — before `_get_payload` existed, `scene()` fed this call's fresh `defaults`/`index`
    straight into `build_scene_payload`/`build_wireframe_payload` on every request, so a warm
    geometry cache didn't save that route from redoing every actor's class resolution from scratch
    each time (see `_get_payload`'s comment)."""
    user_config = config.load_user_config()
    search_files = config.composed_search_files(project, user_config)
    index = resources.mover_index(None, "uedcli serve", project=project)
    defaults = ClassDefaults(packages.schema_resolver(project, user_config))
    return search_files, index, defaults


def create_app(project, level: str, *, fault_route: bool = False) -> FastAPI:
    """Build the app for one project, initially serving `level` -- no longer fixed for the app's
    lifetime (quad-layout Part 7): `PUT /api/level` switches which level this SAME running app
    serves, in-process, via the `_current_level`/`_watcher` holder cells below (no restart, no page-
    reload trick). `fault_route=True` mounts `/api/_boom` (raises a real domain error, for testing
    the exception handler) — never set outside tests; the shipped app never mounts it."""
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

    # The level this app currently serves (quad-layout Part 7, Task 25) — a single-element list
    # mutated BY INDEX (`_current_level[0] = ...`) in `PUT /api/level`'s closure, the same holder-
    # cell idiom `_trunk_ref`/`_geometry_ref` below already use (a plain local reassignment inside a
    # nested function needs `nonlocal`; mutating a list element in place doesn't).
    _current_level: list[str] = [level]

    def _valid_level_name(name: str) -> bool:
        # Single-segment guards against a name that isn't a real level dir (traversal is already
        # impossible — Starlette's {level_name} is [^/]+ and uvicorn pre-decodes %2F).
        return "/" not in name and name not in ("", ".", "..") and (maps_root / name).is_dir()

    def _require_level(level_name: str) -> None:
        # Route param validated like the `serve` verb's own up-front check, so a bad/nonexistent name
        # returns a clean "level not found" (exit-2-equivalent 422) rather than falling through to
        # build_scene's misleading "no CSG brush actors" (no-half-answer rule). `level_name !=
        # _current_level[0]`: every route below except `PUT /api/level` itself operates on ONLY the
        # currently-served level, and with the shared trunk/geometry cache keyed on nothing but that
        # one level, a syntactically-valid-but-different level name would otherwise silently serve
        # THIS level's cached data instead of its own (shared-cache spec's `_require_level` finding).
        if level_name != _current_level[0] or not _valid_level_name(level_name):
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
                await ws.send_json({"type": "changes_available", "level": _current_level[0]})
            except Exception:
                dead.add(ws)
        connections.difference_update(dead)

    # Shared in-process scene cache (`dev/docs/board/to-build/uedcli-serve-share-one-in-process-
    # scene-cache/`): three independently-atomic slots -- `_trunk_ref` (Load-owned), `_geometry_ref`
    # (Rebuild-owned, gui-explicit-rebuild spec §0), and `_payload_ref` (added after a live perf bug,
    # see below). `_generation` guards against a slow build in flight when an invalidation lands
    # publishing a stale result over a state that's since moved on (a real race a plain
    # double-checked-locking sketch has no defense against -- see `_build_and_publish_geometry`
    # below); bumped by `_on_trunk_settled` (the watcher settling), which no longer clears any of the
    # three refs (Task 3) -- a mere trunk change on disk must not silently discard an already-pinned
    # Rebuild or payload; only an explicit Load/Rebuild reassigns a ref outright.
    #
    # `_payload_ref`/`_get_payload` cache `build_scene_payload`/`build_wireframe_payload`'s OUTPUT,
    # keyed on the IDENTITY of the `(trunk_state, geometry)` pair that produced it -- NOT on
    # `_generation`, since neither `_trunk_ref` nor `_geometry_ref` is cleared by a generation bump
    # any more (unlike the sibling scene-cache spec's original model, where a `_generation` mismatch
    # meant "the ref got cleared, rebuild"). A payload is only ever stale once `/load` or `/rebuild`
    # reassigns one of those refs to a NEW object, which identity comparison catches directly.
    # Measured on a real WanChai-scale request (2288 actors): `/scene` stayed ~28s even on a WARM
    # repeat (`/atlas`, which never calls `build_scene_payload`, took ~2.4s on the identical warm
    # cache). Root cause wasn't `build_scene_payload`'s own per-actor loop -- it already amortizes
    # `_is_hidden_ed`'s class resolution to one `ClassDefaults.for_class` call per DISTINCT class
    # within a single call. It was the CALLER: `scene()` built a brand-new `ClassDefaults`/
    # `ClassIndex` via `_scene_inputs()` on EVERY request, so that per-class memo was thrown away and
    # rebuilt from scratch (a package load + Super-chain walk + defaults decode per distinct class,
    # ~0.1-0.3s cold each) on every single `/scene` GET, warm trunk/geometry cache or not. Caching
    # the payload itself means a warm request never calls `build_scene_payload`/
    # `build_wireframe_payload` (or touches `defaults`/`index`) at all -- profiled fix: a synthetic
    # 2288-actor/19-class level went from ~1.8s on every repeat call to ~1.8s once, ~0.06s every call
    # after (`_scratch/profile_scene.py`).
    _generation = [0]
    _trunk_lock = threading.Lock()
    _payload_lock = threading.Lock()
    _trunk_ref: list[_LoadedTrunk | None] = [None]
    # `_scene_inputs_ref` caches `(search_files, index, defaults)` for the THREE READ ROUTES ONLY
    # (`/scene`, `/atlas`, `/lightmap`) -- board `gui-serve-rebuilds-classindex-on-every-request`
    # spec's "Proposed fix". Its lifetime is tied to `_trunk_ref`'s, not the process's: stashed
    # only where `_trunk_ref[0]` itself gets (re)assigned (`/load`'s handler, `_get_trunk`'s
    # once-only bootstrap branch below), read by `_current_scene_inputs()`. `/load` and `/rebuild`
    # deliberately do NOT read from this slot -- they call `_scene_inputs()` fresh every time,
    # unchanged, because they genuinely consume a fresh `index`/`defaults` to re-derive real state
    # (the trunk itself; the CSG/lighting solve) where a stale one could silently produce a
    # different, wrong result -- not merely a slower-but-correct one (spec §3).
    _scene_inputs_ref: list[tuple | None] = [None]
    _geometry_ref: list[_BuiltGeometry | None] = [None]
    # `_payload_ref` caches `build_scene_payload`/`build_wireframe_payload`'s output as
    # `(trunk_state, geometry, payload)` -- `_get_payload` below compares the first two by identity
    # against the CURRENT `_trunk_ref[0]`/`_read_geometry()` to decide if the cached `payload` is
    # still valid (see the cache-slot comment above).
    _payload_ref: list[tuple[_LoadedTrunk, _BuiltGeometry | None, ScenePayload] | None] = [None]
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

    def _bootstrap_geometry_if_empty(level_name: str) -> None:
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
        pin = build_pin.load_pointer(project, level_name)
        if pin is None:
            _build_status[0] = "no_build"
            return
        resolved = build_pin.resolve_pin(project, level_name, pin)
        if resolved is None:
            _build_status[0] = "evicted"   # spec §1's eviction caveat -- degrade, never raise
            return
        polys, texture_table, owners = resolved
        geom_hash, light_hash = pin
        _geometry_ref[0] = _BuiltGeometry(geom_hash=geom_hash, light_hash=light_hash, polys=polys,
                                          texture_table=texture_table, owners=owners)
        _build_status[0] = "built"

    def _current_scene_inputs():
        """`(search_files, index, defaults)` for `/scene`/`/atlas`/`/lightmap` only -- reuses
        whatever was built alongside the CURRENT `_trunk_ref[0]` instead of rebuilding a fresh,
        memo-less `ClassIndex`/`ClassDefaults` on every read (board
        `gui-serve-rebuilds-classindex-on-every-request`). Safe because these three routes only
        ever CONSUME the trunk `_scene_inputs_ref` was seeded alongside: on a `_get_payload` cache
        HIT, `index`/`defaults` are never even touched; on a MISS (a fresh trunk with no cached
        payload yet -- always true right after a Load), `build_scene_payload`/
        `build_wireframe_payload` DO consume them, but they get exactly the same `index`/`defaults`
        that Load itself just resolved the trunk's own actors with (both writes happen together,
        see the two `_scene_inputs_ref[0] = ...` call sites) -- reusing that pairing is exactly as
        fresh as what these routes already effectively run against today. `/load`/`/rebuild` never
        call this -- they call `_scene_inputs()` directly, unconditionally (see the
        `_scene_inputs_ref` cache-slot comment above).

        Cold path (`_trunk_ref[0]` still `None` -- nothing to pair with yet, e.g. the very first
        request in the process is one of these three routes, before any `/load`): builds fresh via
        `_scene_inputs()`, same cost as today; not a regression, since there is nothing to reuse
        yet. `_get_trunk`'s own bootstrap branch stashes ITS result into `_scene_inputs_ref` once
        it wins `_trunk_lock`, so a second read route racing behind it reuses that instead of also
        building its own."""
        cached = _scene_inputs_ref[0]
        if cached is not None and _trunk_ref[0] is not None:
            return cached
        return _scene_inputs(project)

    def _get_trunk(level_name: str, search_files, index, defaults) -> _LoadedTrunk:
        # NOTE on parameters: the plan's own illustrative pseudocode named this `_get_trunk(search_files,
        # index)` and called `resolve_actor_sprites(lvl, index, search_files)` -- but the REAL
        # `resolve_actor_sprites` signature (`preview_native.py:380`) is `(level, search_files,
        # class_defaults)`, and `class_defaults` (a `ClassDefaults`, with `.for_class`) is not
        # interchangeable with `index` (a `ClassIndex`, no `.for_class` -- would raise
        # `AttributeError` on the very first call). Fixed to the verified real signature; flagged in
        # the build report rather than silently carried over. `index` is now a real, separate
        # parameter again (board `mesh-actors-should-render-independent-of-geometry-build`):
        # `resolve_mesh_scene_polys`/`resolve_mover_scene_polys` (mesh-actor/Mover triangles, both
        # Load-owned like sprites) need a `ClassIndex`, not a `ClassDefaults` -- every caller already
        # has one from `_scene_inputs()`.
        #
        # `level_name` is the caller's own already-`_require_level`-validated name, not re-read from
        # `_current_level[0]` here (review finding): a concurrent `PUT /api/level` between the
        # caller's validation and this call could otherwise silently build against a DIFFERENT
        # level's directory than the one the caller checked.
        while True:
            cached = _trunk_ref[0]
            if cached is not None:
                return cached
            with _trunk_lock:
                cached = _trunk_ref[0]
                if cached is not None:
                    return cached
                gen_before = _generation[0]
                lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level_name)
                sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
                mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
                    lvl, index, search_files)
                mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
                    lvl, index, search_files)
                if _generation[0] != gen_before:
                    continue    # invalidated mid-build: discard, loop back and retry from the top
                built = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites,
                                     mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                                     mesh_texture_table=mesh_texture_table,
                                     mover_polys=mover_polys, mover_owners=mover_owners,
                                     mover_texture_table=mover_texture_table)
                # Written BEFORE `_trunk_ref[0]` (review finding): `_current_scene_inputs()` gates
                # solely on `_trunk_ref[0] is not None`, unsynchronized -- if `_trunk_ref[0]` were
                # set first, a concurrent reader could observe the NEW trunk paired with the
                # PREVIOUS `_scene_inputs_ref[0]` (a real race, not a benign one: `_get_payload`'s
                # own identity check misses on the new trunk and builds+caches a payload from that
                # stale index/defaults, persisting until the next Load/Rebuild). Writing this first
                # makes "trunk populated" always imply "matching scene-inputs already populated"
                # for a lock-free reader, same reasoning `_read_geometry`'s own comment relies on.
                _scene_inputs_ref[0] = (search_files, index, defaults)   # seeds _current_scene_inputs too
                _trunk_ref[0] = built
                # The AUTOMATIC INITIAL LOAD (spec §"Two independent axes"): this branch only ever
                # runs once per process (gated by `_trunk_ref[0] is None` above), exactly the "first
                # time this level is opened" moment the bootstrap-from-disk-pointer rule targets.
                _bootstrap_geometry_if_empty(level_name)
                return built

    def _read_geometry() -> _BuiltGeometry | None:
        # Pure read, NEVER calls `build_scene()` -- the whole point of the gui-explicit-rebuild spec
        # (§4): nothing may auto-solve as a side effect of a route being fetched, only an explicit
        # Rebuild (`_build_and_publish_geometry` below). No lock needed: a single list-index read of
        # a cell only ever replaced by one atomic assignment, same "single-reference-swap is atomic"
        # reasoning `_trunk_ref`/`_geometry_ref` already relied on before this split.
        return _geometry_ref[0]

    def _build_and_publish_geometry(level_name: str, search_files, index, defaults) -> _BuiltGeometry:
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
                trunk_state = _get_trunk(level_name, search_files, index, defaults)
                # `include_meshes=False`/`include_movers=False`: the GUI resolves mesh-actor and
                # Mover triangles itself, independently of this CSG-solved pipeline (`_get_trunk`'s
                # `resolve_mesh_scene_polys`/`resolve_mover_scene_polys` calls, above), so
                # `geometry.polys` never carries either (boards `mesh-actors-should-render-
                # independent-of-geometry-build`/`mover-triangles-not-build-state-independent`, owner
                # decision "Option A" for both, 2026-09-18) — see `scene.py`'s
                # `build_scene_payload`/`filtered_geometry_polys` docstrings.
                polys, texture_table, owners = _build_scene(
                    trunk_state.level, search_files, index, defaults=defaults, project=project,
                    level_name=level_name, visibility="editor", include_meshes=False,
                    include_movers=False)
                if _generation[0] != gen_before:
                    continue    # invalidated mid-build: discard, retry against the new state
                built = _BuiltGeometry(geom_hash=None, light_hash=None,   # OQ1 -- see scene.py
                                       polys=polys, texture_table=texture_table, owners=owners)
                _geometry_ref[0] = built
                _build_status[0] = "built"
                return built

    def _get_payload(level_name: str, search_files, index, defaults
                     ) -> tuple[ScenePayload, _BuiltGeometry | None, _LoadedTrunk]:
        # Caches `build_scene_payload`/`build_wireframe_payload`'s result so a warm request never
        # re-resolves `_is_hidden_ed`'s class defaults or `_brush_highlight`'s CSG classification,
        # both of which `defaults`/`index` fresh from THIS request's own `_scene_inputs()` call
        # would otherwise force from scratch (see the cache-slot comment above). Keyed on the
        # IDENTITY of `(trunk_state, geometry)` -- not `_generation` -- since neither `_trunk_ref`
        # nor `_geometry_ref` is cleared by a generation bump in this (gui-explicit-rebuild) model;
        # they only change via an explicit `/load` or `/rebuild` reassigning the ref outright, which
        # identity comparison catches directly. No retry-on-invalidation loop is needed the way
        # `_get_trunk`/`_build_and_publish_geometry` need one: this function does no slow work of
        # its own that a concurrent Load/Rebuild could invalidate mid-flight in a way that matters —
        # it captures `trunk_state`/`geometry` up front and builds a payload for exactly that pair,
        # which stays correct (just possibly superseded) even if the global refs move on before it
        # finishes; the NEXT caller's identity check catches that and rebuilds for the new pair.
        # `_payload_lock` is its own lock, not `solve_lock`/`_trunk_lock` — this function calls
        # `_get_trunk`/`_read_geometry`, and reusing either lock here would deadlock the way a
        # recursive `_get_trunk`/`_build_and_publish_geometry` call would (see their own comments).
        #
        # Returns `(payload, geometry, trunk_state)` — the identity-matched pair that produced
        # `payload`, not just the boolean `geometry_pinned` a caller used to derive from its OWN
        # separate `_read_geometry()`/`_get_trunk()` call (review finding: `/atlas`/`/lightmap` each
        # called `_read_geometry()` independently instead of going through this identity-matched
        # read, so a `/rebuild` landing mid-flight could desync what they built from what `/scene`
        # built from). Every caller (`/scene`, `/atlas`, `/lightmap`) now reads `geometry`/
        # `trunk_state` from THIS return, never a second unsynchronized read of their own: a second
        # read taken before or after this call can observe a DIFFERENT geometry state if a `/rebuild`
        # completes while a caller is blocked on `_payload_lock` behind a slow (~28-37s) build — a
        # real race a review caught, not a hypothetical one, since that lock-contention window is
        # exactly this function's own slow path.
        trunk_state = _get_trunk(level_name, search_files, index, defaults)
        geometry = _read_geometry()
        cached = _payload_ref[0]
        if cached is not None and cached[0] is trunk_state and cached[1] is geometry:
            return cached[2], geometry, trunk_state
        with _payload_lock:
            trunk_state = _get_trunk(level_name, search_files, index, defaults)
            geometry = _read_geometry()
            cached = _payload_ref[0]
            if cached is not None and cached[0] is trunk_state and cached[1] is geometry:
                return cached[2], geometry, trunk_state
            if geometry is None:
                payload = build_wireframe_payload(trunk_state, index, defaults)
            else:
                payload = build_scene_payload(trunk_state, geometry, index, defaults)
            _payload_ref[0] = (trunk_state, geometry, payload)
            return payload, geometry, trunk_state

    async def _on_trunk_settled() -> None:
        # gui-explicit-rebuild spec §0/§2: supersedes the sibling scene-cache spec's own TRIGGER,
        # not its slot shape -- Load owns `_trunk_ref`, Rebuild owns `_geometry_ref`, and a mere
        # trunk change settling on disk touches NEITHER any more (contrast the sibling spec's original
        # design, which cleared both here so the next request would auto-rebuild). `_payload_ref`
        # is untouched too, for the same reason -- it goes stale automatically (caught by `_get_payload`'s
        # own identity check) once an explicit `/load` or `/rebuild` actually reassigns `_trunk_ref`/
        # `_geometry_ref`, never merely because the trunk changed on disk. Still bumps
        # `_generation[0]` -- repurposed from "guard an automatic rebuild" to "guard a Rebuild's
        # publish against a stale mid-flight solve" (`_build_and_publish_geometry`'s own generation
        # check) -- and flips `_changes_available[0]` for the client to show as a banner, never an
        # auto-refetch (spec §2, superseding the old silent `"reload"` push). Neither takes
        # `solve_lock` (event-loop-freeze hazard, same reasoning as `_broadcast_changes_available`).
        _generation[0] += 1
        _changes_available[0] = True
        await _broadcast_changes_available()

    # `_watcher` is a holder cell too (quad-layout Part 7, Task 25): a level switch must STOP this
    # exact watcher instance and START a new one bound to the new level's directory, but `_lifespan`
    # is defined once, at `create_app` time -- its `finally: watcher.stop()` would otherwise close
    # over whatever a bare `watcher` local NAMED at that moment, not whatever `PUT /api/level` later
    # replaces it with.
    _watcher: list[TrunkWatcher] = [TrunkWatcher(maps_root / _current_level[0], _on_trunk_settled)]

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        _watcher[0].start()
        try:
            yield
        finally:
            _watcher[0].stop()

    app = FastAPI(lifespan=_lifespan)
    # Exposed on app.state for tests only (e.g. exercising `_broadcast_changes_available`'s
    # concurrent-mutation safety directly) — not part of the HTTP surface.
    app.state.connections = connections
    app.state.broadcast_changes_available = _broadcast_changes_available
    app.state.get_trunk = _get_trunk
    app.state.read_geometry = _read_geometry
    app.state.build_and_publish_geometry = _build_and_publish_geometry
    app.state.get_payload = _get_payload
    app.state.on_trunk_settled = _on_trunk_settled
    app.state.changes_available = _changes_available
    app.state.generation = _generation
    app.state.build_status = _build_status
    app.state.current_level = _current_level
    app.state.watcher = _watcher

    @app.exception_handler(Exception)
    async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # No Python exception reaches the user (CLAUDE.md): every raised exception — classified or
        # not — renders as structured JSON, never a bare traceback.
        try:
            status, message = error_to_status(exc)
        except TypeError:
            # An unclassified exception is exactly the case worth a server-side trace — the client
            # only ever sees "internal error", so this is the ONE place that can still tell a
            # developer what actually broke (review finding: this used to log nothing).
            logger.exception("unclassified_domain_error", extra={"path": request.url.path})
            status, message = 500, "internal error"
        return JSONResponse(status_code=status, content={"error": message})

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "level": _current_level[0]}

    @app.get("/api/levels")
    def levels() -> dict:
        # GET /api/levels (quad-layout Part 7, Task 24) -- reuses level_sources.list_levels, the
        # same enumeration `level list`/`level list --json` already use, not a second one.
        return levels_payload(maps_root, _current_level[0])

    @app.put("/api/level")
    async def switch_level(request: Request) -> dict:
        # The in-process level switch (quad-layout Part 7, Task 25): validates the requested level,
        # stops the OLD watcher, resets EVERY cache slot this app now carries (`_trunk_ref`,
        # `_geometry_ref`, `_payload_ref` -- all three cache data scoped to the OLD level; none of it
        # is valid for the new one), starts a new watcher bound to the new level's directory, and
        # updates the holder cells. No process restart, no page-reload trick.
        #
        # `async def`, the one exception to this file's sync-route convention (every other route is
        # deliberately sync `def` so Starlette runs the blocking ~24s CSG solve in its threadpool,
        # never the event loop -- see `/scene`'s own comment). `TrunkWatcher.start()`/`stop()` call
        # `asyncio.ensure_future(...)`/`task.cancel()`, which need the event loop THIS request runs
        # on; a threadpool worker thread (what a sync route here would run in) has no running event
        # loop, so a sync version of this route would raise `RuntimeError: There is no current event
        # loop in thread ...` the moment it called `new_watcher.start()`.
        body = await request.json()
        new_level = body.get("level") if isinstance(body, dict) else None
        if not isinstance(new_level, str) or not _valid_level_name(new_level):
            raise CommandError(f"level not found: {new_level!r}")

        _watcher[0].stop()

        # Bump `_generation` before clearing the slots so a slow build/trunk-read for the OLD level
        # still in flight discards its result on completion (the same generation-guard mechanism
        # `_on_trunk_settled`/`_build_and_publish_geometry` already use) instead of publishing over
        # the new level's freshly-emptied slots.
        _generation[0] += 1
        _trunk_ref[0] = None
        _geometry_ref[0] = None
        _payload_ref[0] = None
        _scene_inputs_ref[0] = None
        _changes_available[0] = False
        _build_status[0] = "no_build"

        _current_level[0] = new_level
        new_watcher = TrunkWatcher(maps_root / new_level, _on_trunk_settled)
        new_watcher.start()
        _watcher[0] = new_watcher

        # No WS broadcast here (a deliberate choice, not an oversight): `"changes_available"` means
        # exactly one thing today (a settled trunk change waiting on an explicit Load, spec §2) --
        # broadcasting it for a LEVEL SWITCH would tell every other connected viewer to refresh
        # `/status` for what they still think is their own level, which just changed under them. A
        # second viewer's own next request against a level name that no longer matches
        # `_current_level[0]` gets `_require_level`'s ordinary "level not found", which is honest;
        # true multi-viewer-aware level switching is out of scope here (this app has always been
        # one-level-per-process, Slice 1's own docstring).
        return {"level": new_level}

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
        # slot is already warm. `resolve_actor_sprites`/`resolve_mesh_scene_polys`/
        # `resolve_mover_scene_polys` ride along, same as `_get_trunk`'s own build, since sprite/
        # mesh/Mover resolution are all Load-owned (spec §"Two independent axes"; mesh/Mover
        # independence: boards `mesh-actors-should-render-independent-of-geometry-build`/
        # `mover-triangles-not-build-state-independent`).
        _require_level(level_name)
        search_files, index, defaults = _scene_inputs(project)
        lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level_name)
        sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
        mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
            lvl, index, search_files)
        mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
            lvl, index, search_files)
        loaded = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                              sprite_table=sprite_table, actor_sprites=actor_sprites,
                              mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                              mesh_texture_table=mesh_texture_table,
                              mover_polys=mover_polys, mover_owners=mover_owners,
                              mover_texture_table=mover_texture_table)
        # Written BEFORE `_trunk_ref[0]` (review finding, same reasoning as `_get_trunk`'s bootstrap
        # branch): `_current_scene_inputs()` gates solely on `_trunk_ref[0] is not None`, so a
        # concurrent `/scene`/`/atlas`/`/lightmap` must never be able to observe the NEW trunk
        # paired with the PREVIOUS `_scene_inputs_ref[0]` -- that would feed a stale index/defaults
        # into `_get_payload`'s payload-cache-miss branch (trunk identity just changed, so it always
        # misses right after a Load) and cache a wrong payload until the next Load/Rebuild.
        _scene_inputs_ref[0] = (search_files, index, defaults)   # seeds /scene, /atlas, /lightmap
        _trunk_ref[0] = loaded
        _changes_available[0] = False
        # Bootstrap-from-disk-pointer: a no-op if a Rebuild already populated the slot this session
        # (spec §1's last bullet -- an on-disk pointer must never overwrite an in-memory pin a
        # Rebuild already set), otherwise the same "unlock all modes with no Rebuild needed" check
        # the automatic initial Load already runs (spec test #8).
        _bootstrap_geometry_if_empty(level_name)
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
        geometry = _build_and_publish_geometry(level_name, search_files, index, defaults)
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
        search_files, index, defaults = _current_scene_inputs()
        # `_get_payload` internally picks `build_wireframe_payload` (cold-open / no Rebuild yet --
        # genuinely no solved geometry, not an error; every actor's own AUTHORED brush shape still
        # rides on `SceneActor.brush`, spec §4) vs `build_scene_payload`, the same way this route's
        # own inline branch used to, before payload caching existed. `geometry_pinned` comes from
        # `_get_payload`'s OWN return, not a separate `_read_geometry()` call here — a second,
        # unsynchronized read could observe a different geometry state than the one that actually
        # produced `payload` if a `/rebuild` completes while this call was blocked on
        # `_get_payload`'s lock (review finding: that contention window is exactly this route's
        # slow path, not a negligible one).
        payload, geometry, _trunk_state = _get_payload(level_name, search_files, index, defaults)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors],
            "geometry_pinned": geometry is not None,
        }

    @app.get("/api/level/{level_name}/atlas")
    def atlas(level_name: str) -> dict:
        # Routed through `_get_payload` (review finding, item 4) -- the SAME identity-matched
        # `(trunk_state, geometry)` pair `/scene` built its payload from, not a second independent
        # `_get_trunk()`/`_read_geometry()` read: two unsynchronized reads here could observe a
        # DIFFERENT geometry state than `/scene`'s if a `/rebuild` lands mid-flight between them.
        # With geometry pinned: `geometry.texture_table + trunk_state.sprite_table +
        # trunk_state.mesh_texture_table + trunk_state.mover_texture_table`, in the same order
        # `scene.py::build_scene_payload` uses when it wraps `trunk.actor_sprites`/`trunk.mesh_polys`/
        # `trunk.mover_polys` into `SceneActor.sprite`/`ScenePoly` mesh/Mover entries, so a
        # `tex_index` from /scene names the same rect here. With NO geometry pinned: sprites, mesh
        # textures AND Mover textures are all Load-owned (unaffected by whether geometry exists -- a
        # point actor's icon, a mesh actor's own texture, and a Mover's own texture should all still
        # show in wireframe mode), so the atlas is built from `trunk_state.sprite_table +
        # trunk_state.mesh_texture_table + trunk_state.mover_texture_table`
        # (`build_wireframe_payload`'s own sprites/mesh/Mover polys carry `tex_index` offset the same
        # way, matching this — boards `mesh-actors-should-render-independent-of-geometry-build`/
        # `mover-triangles-not-build-state-independent`).
        _require_level(level_name)
        search_files, index, defaults = _current_scene_inputs()
        _payload, geometry, trunk_state = _get_payload(level_name, search_files, index, defaults)
        texture_table = ((geometry.texture_table if geometry is not None else [])
                         + trunk_state.sprite_table + trunk_state.mesh_texture_table
                         + trunk_state.mover_texture_table)
        png_bytes, manifest, width, height = build_atlas(texture_table)
        return {
            "width": width,
            "height": height,
            "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    @app.get("/api/level/{level_name}/lightmap")
    def lightmap(level_name: str) -> dict:
        # Routed through `_get_payload` too (review finding, item 4 — same identity-matched pair as
        # /scene and /atlas). The poly list this route packs must also be the SAME FILTERED set
        # `/scene` built its payload from (review finding, item 2): `build_scene_payload` drops a
        # hidden `CSG_Add` brush's own surfaces from `ScenePayload.polys`, which shifts every LATER
        # poly's array position — the client indexes this route's manifest by that same (filtered)
        # position, so packing the raw UNFILTERED `geometry.polys` here silently mis-indexed
        # lightmaps on any level with such a brush. `filtered_geometry_polys` is the ONE filter
        # function `build_scene_payload` itself uses, so the two routes' filtering can't drift.
        # `intensity` is the atlas's global multiplier scale — the client's `lightMapIntensity`. No
        # geometry pinned: there are no lit polys to pack -- `build_lightmap_atlas([])` already
        # returns a valid degenerate response (1x1 PNG, empty manifest, intensity 1.0 — the same
        # shape a solved-but-unlit level gets), so no special-casing is needed here.
        _require_level(level_name)
        search_files, index, defaults = _current_scene_inputs()
        _payload, geometry, trunk_state = _get_payload(level_name, search_files, index, defaults)
        if geometry is None:
            polys: list[tuple] = []
        else:
            hidden_ed = _resolve_hidden_ed(trunk_state.level, defaults)
            polys = [poly for poly, _owner in filtered_geometry_polys(trunk_state.level, geometry, hidden_ed)]
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
