"""FastAPI app factory for `uedcli serve` — the read-only HTTP/WS surface over the model-side
library (spec, "Architecture"). Binds localhost only (enforced by the `serve` verb, not here);
holds all domain logic — the client draws only what these routes hand it."""
from __future__ import annotations

import asyncio
import base64
import functools
import logging
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from .. import build_cache, config, packages, trunk
from ..classdefaults import ClassDefaults
from ..cli import resources
from ..cli.errors import CommandError
from ..preview_native import build_scene
from ..preview_native import resolve_actor_sprites, resolve_mesh_scene_polys, resolve_mover_scene_polys
from . import build_pin, edits, sessions
from .claims import ClaimRegistry
from .errors import error_to_status
from .levels import levels_payload
from .lightmap import build_lightmap_atlas
from .scene import (
    _BuiltGeometry,
    _LoadedTrunk,
    _resolve_hidden_ed,
    build_scene_payload,
    build_wireframe_payload,
    filtered_geometry_polys,
)
from .snapshots import StagingStore
from .textures import build_atlas
from .watch import TrunkWatcher

logger = logging.getLogger(__name__)

# How often `ws_endpoint` re-checks its own claim token between client messages (Task 15). Short
# enough that a superseded connection notices quickly and tests don't need to wait long; cheap
# enough (`ClaimRegistry.check` is a dict lookup under a lock) that a tighter interval costs nothing
# real even with many open connections.
_WS_CLAIM_POLL_INTERVAL_S = 0.1


class _BuildResultCache:
    """In-memory LRU in front of build_cache's on-disk store, keyed by content hash -- shared
    across every session and level, since identical hashes mean identical content regardless of who
    asked. Without this, every /scene|/atlas|/lightmap call re-does disk I/O + deserialization on
    every request (a real, previously-fixed perf regression -- see the spec's Build cache section)."""
    def __init__(self, max_entries: int = 8) -> None:
        self._max = max_entries
        self._data: OrderedDict[tuple, object] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: tuple, value) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class _SessionKeyedStore:
    """Adapts `_staging_store` for `edits.py`'s `stage_locations`/`save_staged` (Task 13). Those two
    functions bind ONE `level_name` parameter to two different real uses internally: `_trunk_dir`
    (needs the real level name) and `store.<method>(level_name, ...)` (needs the real session id,
    since staged edits are keyed per-session, not per-level). Wraps the real `StagingStore` and
    substitutes the session id closed over at construction for whatever `level_name` argument
    `edits.py` passes through to `.stage`/`.read_staged`/`.clear_actor` -- so a call like
    `stage_locations(project, session.level, moves, store=_SessionKeyedStore(_staging_store,
    session_id))` correctly loads the trunk from `session.level` while still keying the actual store
    writes by `session_id`.

    `discard_staged`/`check_load_conflicts` need no such wrapper: their own `level_name` parameter
    is used ONLY as the store key (neither ever touches the trunk), so a route can pass `session_id`
    straight through to them with the real `_staging_store`, no adapter required."""
    def __init__(self, store: StagingStore, session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    def stage(self, _level_name: str, actor_name: str, **kwargs) -> None:
        self._store.stage(self._session_id, actor_name, **kwargs)

    def read_staged(self, _level_name: str):
        return self._store.read_staged(self._session_id)

    def clear_actor(self, _level_name: str, actor_name: str) -> None:
        self._store.clear_actor(self._session_id, actor_name)


def _frontend_dist_dir() -> Path | None:
    """A built `web/dist` next to this package -- same relative path whether this is a source
    checkout (repo root's `web/dist`, once `npm run build` has run) or a Nuitka standalone binary
    (`bin/build-standalone` copies `web/dist` to this same relative spot next to the compiled
    package). Returns None if not built -- `serve` then stays API-only, exactly as it does today;
    no binary-vs-source branch, one code path either way."""
    candidate = Path(__file__).resolve().parents[2] / "web" / "dist"
    return candidate if candidate.is_dir() else None


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


@dataclass(frozen=True, kw_only=True)
class LevelContext:
    """Level-shared state — one per level name, created lazily by `_get_or_create_level_context`
    (plan Task 9, persistent-GUI-editing-sessions). Replaces the app's old single flat holder-cell
    set (`_trunk_ref`/`_generation`/`_trunk_lock`/one `TrunkWatcher`/`connections`/
    `_scene_inputs_ref`), so a second level can be served by the SAME running app without stepping
    on the first one's cache.

    Deliberately does NOT carry solved-build state (`geometry_ref`/`payload_ref`/`build_status`,
    nor a `solve_lock`) — that state is REMOVED ENTIRELY by this task, not moved here. It becomes
    per-session, disk-backed state in a later task (Task 11: session-scoped Rebuild). Between this
    task and that one, `POST /rebuild` is deliberately memoryless.

    `scene_inputs_ref` DOES stay here, despite living next to the removed fields in the old code:
    it caches the composed package search path + class-resolution machinery (`search_files`,
    `index`, `defaults`), which depends only on the level + project config, never on any session's
    staged edits — genuinely level-shared, exactly like `trunk_ref`/`generation`/`watcher`. Dropping
    it would reintroduce a real, already-fixed perf regression (see `scene.py::build_scene_payload`'s
    docstring: a WanChai-scale request stayed ~28s even on a warm repeat before this cache existed)."""
    level_name: str
    trunk_ref: list           # [_LoadedTrunk | None], mutated by index, never reassigned
    generation: list[int]
    changes_available: list[bool]
    trunk_lock: threading.Lock
    watcher: TrunkWatcher
    connections: set
    scene_inputs_ref: list    # [tuple | None]


def create_app(project, level: str | None = None, *, fault_route: bool = False) -> FastAPI:
    """Build the app for one project. `level`, if given, is the STARTUP level: its `LevelContext`
    (and `TrunkWatcher`) is created eagerly and `app.state.connections`/`broadcast_changes_available`/
    `on_trunk_settled`/`changes_available`/`generation` are bound to it, purely so pre-Task-12 tests
    (and any other zero-argument caller) keep working unchanged. `level=None` (plan Task 12: session
    CRUD): the process starts with ZERO `LevelContext`s — no eager session/trunk-watcher creation at
    startup, per the spec's "a session is created only by a real page load, never automatically".
    `level` is still recorded as `app.state.default_level` (e.g. for the frontend's fallback default
    on a bare URL with no session id) regardless of whether it's `None`. `/ws` (Task 15) is now
    genuinely session-scoped instead of bound to the startup level: it resolves its own
    `LevelContext` from the connecting session's `.level` via `_get_or_create_level_context`, so
    `level=None` is no longer a connect-time crash -- a session on any level can connect regardless
    of which (if any) level the app started with. `fault_route=True` mounts `/api/_boom`
    (raises a real domain error, for testing the exception handler) — never set outside tests; the
    shipped app never mounts it."""
    maps_root = Path(config.project_maps_dir(project))
    # One StagingStore per app (plan Task 3), not per-request -- same "construct once, cache on the
    # closure" convention as every other per-project state here. Its roots are the project's own
    # machine-local state dir (`config.state_subdir`, `create=True` so the first stage/save of a
    # session doesn't need a separate bootstrap step): a per-session manifest root and a shared
    # content-addressed blob root.
    # Shared with `sessions.py`'s own `sessions_root` (Task 6/11): both key off the same
    # `sessions/<sid>/` layout -- `StagingStore`'s per-session manifest, `sessions.py`'s
    # `index.json`, and `build_pin.py`'s per-session `build.json` all live side by side there.
    _sessions_root = config.state_subdir(project.root, "sessions", create=True)
    _staging_store = StagingStore(
        _sessions_root,
        config.state_subdir(project.root, "staging/blobs", create=True),
    )
    _claims = ClaimRegistry()
    # `_BuildResultCache`'s own docstring says it sits in front of `build_cache`'s on-disk store --
    # one instance per app, same "construct once, close over it" convention as
    # `_staging_store`/`_claims` above. `session_rebuild` populates it; `_resolve_session_geometry`
    # (final-review fix round, Finding 1) is the read side -- checked before falling back to
    # `build_cache.load_scene` on disk.
    _build_result_cache = _BuildResultCache()
    # Final-review fix round, Finding 3: `build_cache.evict_unreferenced` reads
    # `project.build_cache_max_bytes` ITSELF whenever the caller's own `max_bytes` override is
    # `None` -- there is no way to tell it "treat this as genuinely unconfigured, don't touch
    # `project` at all" from the outside without redesigning that fallback (out of scope here).
    # This app's own real `config.Project` always defines the field (default `None`, i.e. no
    # budget), but many tests construct a bare `SimpleNamespace(root=..., maps=None)` project
    # double that doesn't -- so eviction is skipped entirely for a `project` that can't represent a
    # budget at all. `StagingStore.evict_unreferenced_blobs` has no such internal project-read (its
    # `max_bytes` is a plain parameter, no fallback), so `_staging_blobs_max_bytes` below just
    # needs a safe default, not a skip-guard.
    _project_has_build_cache_budget = hasattr(project, "build_cache_max_bytes")
    _staging_blobs_max_bytes = getattr(project, "staging_blobs_max_bytes", None)

    def _valid_level_name(name: str) -> bool:
        # Single-segment guards against a name that isn't a real level dir (traversal is already
        # impossible — Starlette's {level_name} is [^/]+ and uvicorn pre-decodes %2F).
        return "/" not in name and name not in ("", ".", "..") and (maps_root / name).is_dir()

    def _require_level(level_name: str) -> None:
        # Route param validated like the `serve` verb's own up-front check, so a bad/nonexistent name
        # returns a clean "level not found" (exit-2-equivalent 422) rather than falling through to
        # build_scene's misleading "no CSG brush actors" (no-half-answer rule). Plan Task 9: no
        # longer compares against a single "currently served" level -- `LevelContext` is keyed per
        # level name in a dict, so ANY syntactically-valid on-disk level is now servable, each with
        # its own independent context. (This is the actual multi-level-serving change this task
        # makes -- the old comparison existed only to protect the single flat cache this task
        # replaces.)
        if not _valid_level_name(level_name):
            raise CommandError(f"level not found: {level_name!r}")

    def _require_session(session_id: str) -> sessions.SessionRecord:
        # Task 13: the shared "resolve a session id to its record, then validate its level" pattern
        # `session_rebuild` (Task 11) already open-coded once -- now shared across every
        # session-scoped route below instead of duplicated per-route.
        session = sessions.get_session(_sessions_root, session_id)
        if session is None:
            raise CommandError(f"session not found: {session_id!r}")
        _require_level(session.level)
        # Final-review fix round, Finding 4: "any request scoped to a session updates that
        # session's last_active_at" (spec) -- this is the one chokepoint every session-scoped route
        # below resolves its session through, so wiring it here covers all of them at once.
        # `touch_session` self-throttles (a no-op inside 30s of the last update), so calling it on
        # every request costs one cheap `get_session` re-read, not a write per request.
        sessions.touch_session(_sessions_root, session_id)
        return session

    async def _broadcast_changes_available(ctx: LevelContext) -> None:
        # Iterate a SNAPSHOT: `await ws.send_json` yields the event loop, and a client connecting
        # or disconnecting in that window mutates `ctx.connections` from a concurrently-running
        # coroutine (`ws_endpoint`) — iterating the live set directly raises "Set changed size
        # during iteration" and drops the whole broadcast (review finding, multi-viewer scenario).
        dead = set()
        for ws in list(ctx.connections):
            try:
                await ws.send_json({"type": "changes_available", "level": ctx.level_name})
            except Exception:
                dead.add(ws)
        ctx.connections.difference_update(dead)

    async def _on_trunk_settled(ctx: LevelContext) -> None:
        # gui-explicit-rebuild spec §0/§2: a mere trunk change settling on disk touches only the
        # generation counter (guarding a build-in-flight, see `_get_trunk` below) and the
        # `changes_available` banner flag -- never the trunk slot itself. Never takes
        # `ctx.trunk_lock` (event-loop-freeze hazard, same reasoning as `_broadcast_changes_available`).
        ctx.generation[0] += 1
        ctx.changes_available[0] = True
        await _broadcast_changes_available(ctx)

    _level_contexts: dict[str, LevelContext] = {}
    _level_contexts_lock = threading.Lock()

    def _get_or_create_level_context(level_name: str) -> LevelContext:
        """The per-level state this app now keys everything off of (plan Task 9). Lazily creates a
        `LevelContext` the first time a level name is seen, idempotent on every later call. Builds
        (but never STARTS) that level's own `TrunkWatcher` -- starting one needs a running event
        loop, which a plain call to this function (e.g. from a test, or a threadpool route handler)
        doesn't have. The app's STARTUP level's watcher is started/stopped by `_lifespan` below; a
        lazily-created second level's watcher is started by `ws_endpoint` (final-review fix round,
        Finding 5), the first async context that sees a session on it -- never stopped by this app
        (only the startup level's is, on shutdown), a known, accepted gap: stopping it would need
        tracking every lazily-created level's watcher for `_lifespan`'s shutdown to sweep, which
        nothing has asked for yet."""
        ctx = _level_contexts.get(level_name)
        if ctx is not None:
            return ctx
        with _level_contexts_lock:
            ctx = _level_contexts.get(level_name)
            if ctx is not None:
                return ctx
            # The watcher's callback looks the context up by name at call time (rather than
            # capturing it directly) so the watcher can be constructed as part of building the
            # context itself, with no partially-constructed placeholder needed.
            watcher = TrunkWatcher(maps_root / level_name,
                                   lambda: _on_trunk_settled(_level_contexts[level_name]))
            ctx = LevelContext(level_name=level_name, trunk_ref=[None], generation=[0],
                               changes_available=[False], trunk_lock=threading.Lock(),
                               watcher=watcher, connections=set(), scene_inputs_ref=[None])
            _level_contexts[level_name] = ctx
            return ctx

    def _current_scene_inputs(level_name: str):
        """`(search_files, index, defaults)` for `/scene`/`/atlas`/`/lightmap` only -- reuses
        whatever was built alongside the CURRENT `ctx.trunk_ref[0]` instead of rebuilding a fresh,
        memo-less `ClassIndex`/`ClassDefaults` on every read (board
        `gui-serve-rebuilds-classindex-on-every-request`). `/load`/`/rebuild` never call this --
        they call `_scene_inputs()` directly, unconditionally, since they genuinely need a fresh
        `index`/`defaults` to re-derive real state where a stale one could silently produce a
        different, wrong result -- not merely a slower-but-correct one.

        Cold path (`ctx.trunk_ref[0]` still `None` -- nothing to pair with yet): builds fresh via
        `_scene_inputs()`, same cost as today; not a regression, since there is nothing to reuse
        yet. `_get_trunk`'s own bootstrap branch stashes ITS result into `ctx.scene_inputs_ref`
        once it wins `ctx.trunk_lock`, so a second read route racing behind it reuses that instead
        of also building its own."""
        ctx = _get_or_create_level_context(level_name)
        cached = ctx.scene_inputs_ref[0]
        if cached is not None and ctx.trunk_ref[0] is not None:
            return cached
        return _scene_inputs(project)

    def _get_trunk(level_name: str, search_files, index, defaults) -> _LoadedTrunk:
        # NOTE on parameters: `resolve_actor_sprites`'s real signature (`preview_native.py:380`) is
        # `(level, search_files, class_defaults)` -- `defaults` (a `ClassDefaults`, with
        # `.for_class`) is not interchangeable with `index` (a `ClassIndex`, no `.for_class`).
        # `resolve_mesh_scene_polys`/`resolve_mover_scene_polys` (mesh-actor/Mover triangles, both
        # Load-owned like sprites) need a `ClassIndex`, not a `ClassDefaults`.
        ctx = _get_or_create_level_context(level_name)
        while True:
            cached = ctx.trunk_ref[0]
            if cached is not None:
                return cached
            with ctx.trunk_lock:
                cached = ctx.trunk_ref[0]
                if cached is not None:
                    return cached
                gen_before = ctx.generation[0]
                lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / level_name)
                sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
                mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
                    lvl, index, search_files, defaults)
                mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
                    lvl, index, search_files, defaults)
                if ctx.generation[0] != gen_before:
                    continue    # invalidated mid-build: discard, loop back and retry from the top
                built = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                     sprite_table=sprite_table, actor_sprites=actor_sprites,
                                     mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                                     mesh_texture_table=mesh_texture_table,
                                     mover_polys=mover_polys, mover_owners=mover_owners,
                                     mover_texture_table=mover_texture_table)
                # Written BEFORE `ctx.trunk_ref[0]` (same reasoning `_current_scene_inputs` relies
                # on): a lock-free reader must never observe the NEW trunk paired with the
                # PREVIOUS `ctx.scene_inputs_ref[0]`.
                ctx.scene_inputs_ref[0] = (search_files, index, defaults)
                ctx.trunk_ref[0] = built
                return built

    def _resolve_session_geometry(session_id: str, level_name: str) -> _BuiltGeometry | None:
        """Final-review fix round, Finding 1: the read side of session-scoped Rebuild --
        `session_scene`/`session_atlas`/`session_lightmap`'s way of turning "this session has a
        build pin" into a real `_BuiltGeometry`. Mirrors `session_status`'s own pin resolution
        (`build_pin.resolve_session_pin`), but split apart so the in-memory `_build_result_cache`
        can be checked BEFORE any disk read: `resolve_session_pin` always goes straight to
        `build_cache.load_scene`, which is exactly the redundant disk I/O `_BuildResultCache` exists
        to avoid on the common case (this session's own just-completed `session_rebuild` already
        populated it). Returns `None` for "no build pinned" (never rebuilt) or "evicted" (a pin
        exists but neither the memory cache nor disk has the content any more) -- the caller can't
        tell those two apart from this alone and doesn't need to; `session_status` is the route that
        reports which."""
        try:
            geom_hash, light_hash = build_pin.load_session_pointer(_sessions_root, session_id)
        except build_pin.SessionPointerCorruptError:
            return None
        key = (level_name, geom_hash, light_hash)
        cached = _build_result_cache.get(key)
        if cached is None:
            cached = build_cache.load_scene(project, level_name, geom_hash, light_hash)
            if cached is None:
                return None
            _build_result_cache.put(key, cached)
        polys, texture_table, owners = cached
        return _BuiltGeometry(geom_hash=geom_hash, light_hash=light_hash, polys=polys,
                              texture_table=texture_table, owners=owners)

    def _live_build_refs(level_name: str) -> tuple[set[str], set[tuple[str, str]]]:
        """Final-review fix round, Finding 3: the "live" reference sets `build_cache.evict_
        unreferenced` needs -- every `(geom_hash)`/`(geom_hash, light_hash)` currently pinned by any
        session editing `level_name`, plus the level's own saved pin (Save-promoted, `build_pin.
        write_level_pointer`) -- so eviction never deletes a cache entry a session or a save still
        points at, only genuinely orphaned ones."""
        geom_hashes: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        for rec in sessions.list_sessions(_sessions_root):
            if rec.level != level_name:
                continue
            try:
                geom_hash, light_hash = build_pin.load_session_pointer(_sessions_root, rec.id)
            except build_pin.SessionPointerCorruptError:
                continue
            geom_hashes.add(geom_hash)
            pairs.add((geom_hash, light_hash))
        level_pin = build_pin.load_level_pointer(project, level_name)
        if level_pin is not None:
            geom_hash, light_hash = level_pin
            geom_hashes.add(geom_hash)
            pairs.add((geom_hash, light_hash))
        return geom_hashes, pairs

    def _live_blob_hashes() -> set[str]:
        """Final-review fix round, Finding 3: the "live" set `StagingStore.evict_unreferenced_blobs`
        needs -- every blob hash any session's own `staged.json` currently names, across every
        session (blobs are content-addressed and shared, not per-level)."""
        return {
            entry.blob_hash
            for rec in sessions.list_sessions(_sessions_root)
            for entry in _staging_store.read_staged(rec.id).values()
        }

    # `_watcher` for the app's STARTUP level, started here rather than lazily -- `_lifespan` is
    # defined once, at `create_app` time, so it closes over this one context's watcher. A lazily-
    # created second level's watcher is started elsewhere, from `ws_endpoint` (final-review fix
    # round, Finding 5) -- the first async context that sees that level, since `.start()` needs a
    # running event loop this plain call doesn't have.
    # Plan Task 12: `level` is now optional -- with none given, there is no startup level and so no
    # `LevelContext` is created eagerly (the whole point: zero `LevelContext`s at process start).
    _startup_ctx = _get_or_create_level_context(level) if level is not None else None

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        if _startup_ctx is not None:
            _startup_ctx.watcher.start()
        try:
            yield
        finally:
            if _startup_ctx is not None:
                _startup_ctx.watcher.stop()

    app = FastAPI(lifespan=_lifespan)
    # Recorded regardless of whether a startup level was given (plan Task 12) -- e.g. for the
    # frontend's fallback default on a bare URL with no session id.
    app.state.default_level = level
    # Exposed on app.state for tests only (e.g. exercising `_broadcast_changes_available`'s
    # concurrent-mutation safety directly) — not part of the HTTP surface. Bound to the STARTUP
    # level's context, matching every pre-Task-9 test's zero-argument usage. Plan Task 12: these
    # simply don't exist on `app.state` when there is no startup level -- nothing reads them in that
    # case (every route that needs a `LevelContext` resolves one itself, per-level-name, via
    # `_get_or_create_level_context`/`app.state.get_or_create_level_context`).
    if _startup_ctx is not None:
        app.state.connections = _startup_ctx.connections
        app.state.broadcast_changes_available = functools.partial(_broadcast_changes_available, _startup_ctx)
        app.state.on_trunk_settled = functools.partial(_on_trunk_settled, _startup_ctx)
        app.state.changes_available = _startup_ctx.changes_available
        app.state.generation = _startup_ctx.generation
    app.state.get_trunk = _get_trunk
    app.state.get_or_create_level_context = _get_or_create_level_context
    # Task 11: session-scoped Rebuild's own dependencies -- exposed on `app.state` so tests reach
    # them directly (`sessions.create_session(app.state.sessions_root, ...)`,
    # `app.state.staging_store.stage(...)`, `app.state.claims.mint(...)`), per this plan's
    # "tests set up state via lower-level module functions" rule.
    app.state.sessions_root = _sessions_root
    app.state.staging_store = _staging_store
    app.state.claims = _claims
    app.state.build_result_cache = _build_result_cache

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
        return {"status": "ok"}

    @app.get("/api/levels")
    def levels() -> dict:
        # GET /api/levels (quad-layout Part 7, Task 24) -- reuses level_sources.list_levels, the
        # same enumeration `level list`/`level list --json` already use, not a second one.
        return levels_payload(maps_root, level)

    @app.get("/api/session/{session_id}/status")
    def session_status(session_id: str) -> dict:
        # Task 14: replaces the old per-level `/status` (Task 9's deliberate cold-only placeholder)
        # -- both fields it deferred are per-session state now: `geometry_pinned`/`build_status`
        # come from this session's own `build.json` (Task 11's `build_pin`), and
        # `changes_available` compares the level's trunk-generation counter against THIS session's
        # own high-water mark (`last_seen_generation`, bumped only by this session's own Load,
        # Task 13) instead of a level-wide flag every session shared.
        session = _require_session(session_id)
        ctx = _get_or_create_level_context(session.level)
        try:
            resolved = build_pin.resolve_session_pin(project, session.level, _sessions_root,
                                                      session_id)
        except build_pin.SessionPointerCorruptError:
            # The normal "never Rebuilt" case, not corruption -- same meaning `session_save`'s own
            # pin-promotion step already gives this exception.
            build_status = "no_build"
        else:
            build_status = "built" if resolved is not None else "evicted"
        return {
            "changes_available": ctx.generation[0] > session.last_seen_generation,
            "geometry_pinned": build_status == "built",
            "build_status": build_status,
        }

    # The SESSION-scoped Rebuild (Task 11; the per-level `/api/level/{level_name}/rebuild` route
    # that used to coexist with this one is deleted outright -- final-review fix round, Finding 2:
    # nothing calls it any more once this route exists, and CLAUDE.md's no-back-compat-cruft
    # convention says a superseded verb doesn't get to linger). Solves on a COPY of the shared trunk
    # `Level` (`edits.apply_staged_overlay`) instead of `LevelContext.trunk_ref`'s `Level` directly,
    # so two sessions rebuilding the same level concurrently never see each other's staged edits and
    # never mutate the shared trunk. The claim token is checked ONLY at write time, under
    # `claims.lock_for(session_id)`: a session superseded mid-solve (a newer claim minted while this
    # request's CSG+lighting solve was running) drops the result with 409 and writes nothing --
    # neither `build_pin`'s per-session pointer nor anything else. `build_scene` itself already
    # stores its geometry/scene into `build_cache` on disk when given `project=`/`level_name=` (see
    # its own docstring) -- no separate `build_cache.store_*` call belongs here.
    # Sync `def` (NOT async): the blocking CSG+lighting solve runs in Starlette's threadpool.
    @app.post("/api/session/{session_id}/rebuild")
    def session_rebuild(session_id: str, request: Request):
        # `_require_session` (not a hand-resolved `sessions.get_session`/`_require_level` pair, as
        # this route used to do before this fix round): same "clean, named 422" convention as every
        # other session route, and it's also the chokepoint that touches this session's
        # `last_active_at` (Finding 4).
        session = _require_session(session_id)
        search_files, index, defaults = _scene_inputs(project)
        trunk_state = _get_trunk(session.level, search_files, index, defaults)
        staged = _staging_store.read_staged(session_id)
        overlaid = edits.apply_staged_overlay(trunk_state.level, staged)
        # `include_meshes=False`/`include_movers=False`: same reasoning as the per-level route
        # above -- the GUI resolves mesh-actor/Mover triangles itself, independently of this
        # CSG-solved pipeline.
        polys, texture_table, owners, geom_hash, light_hash = build_scene(
            overlaid, search_files, index, defaults=defaults, project=project,
            level_name=session.level, visibility="editor", include_meshes=False,
            include_movers=False)

        # Task 11 fix round 1 (Finding 1): populate the in-memory `_BuildResultCache` with this
        # solve's result. `geom_hash`/`light_hash` are `build_scene`'s own OUTPUTS -- computed FROM
        # the solved content -- so there is no key available before the solve runs; this route can
        # only ever POPULATE the cache, never benefit from a pre-solve hit itself (the read side is
        # `_resolve_session_geometry`, called from `session_scene`/`session_atlas`/`session_lightmap`
        # below -- final-review fix round, Finding 1). Populated unconditionally, BEFORE the claim check
        # below decides whether this particular session's write survives: the cache is keyed by
        # CONTENT hash (`level_name`, `geom_hash`, `light_hash`), not by session, so a result
        # dropped as superseded for THIS session is still valid, reusable content for any other
        # caller who solves to the same hash -- there is no reason to make it wait on, or depend on,
        # an outcome that is about this session's claim, not about the content's validity.
        _build_result_cache.put((session.level, geom_hash, light_hash), (polys, texture_table, owners))

        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                # Superseded mid-solve (a newer claim minted while the solve above was running):
                # drop the result, write nothing.
                logger.info("session_rebuild_superseded", extra={"session_id": session_id})
                return JSONResponse(status_code=409,
                                    content={"error": "session superseded mid-solve"})
            # Fix round 1, Finding 1 (two-part): the claim check alone can't tell "session
            # legitimately deleted mid-solve" apart from "no one has claimed it yet" --
            # `ClaimRegistry.check`'s restart-safety rule (see its own docstring) auto-accepts any
            # token once `forget()` has cleared the recorded one, so a DELETE that raced this
            # solve would otherwise sail through the check above and `write_session_pointer` would
            # then RECREATE the just-removed `sessions/<sid>/` directory. Re-check existence here,
            # under the same lock DELETE now also takes (below) around its own forget+delete, so
            # the two critical sections never interleave arbitrarily.
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_rebuild_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409,
                                    content={"error": "session deleted mid-solve"})
            build_pin.write_session_pointer(_sessions_root, session_id, geom_hash, light_hash)
            # Final-review fix round, Finding 3: eviction runs opportunistically on the write path
            # that could push the build cache over budget -- right after the write that pins this
            # solve's result, still under the same per-session lock (a cheap directory scan against
            # a small cache dir, not worth a separate critical section). No override `max_bytes` is
            # passed -- `evict_unreferenced`'s own default reads `project.build_cache_max_bytes`
            # (None -> unconfigured -> no eviction pressure at all), which is exactly what a real
            # `config.Project` always defines.
            if _project_has_build_cache_budget:
                live_geom_hashes, live_pairs = _live_build_refs(session.level)
                build_cache.evict_unreferenced(project, session.level,
                                               live_geom_hashes=live_geom_hashes,
                                               live_pairs=live_pairs)

        return {"geom_hash": geom_hash, "light_hash": light_hash}

    # Sync `def` (NOT async): Starlette runs a sync route in its threadpool, so a slow trunk read
    # never freezes the event loop. Final-review fix round, Finding 1: these three routes now
    # actually resolve this session's pinned build (`_resolve_session_geometry`) instead of
    # unconditionally serving the cold/wireframe case -- `build_scene_payload` (the geometry-aware
    # payload builder) when a build is pinned, `build_wireframe_payload` (unchanged) when it isn't.
    # None of these three ever calls `build_scene` itself — only `POST /api/session/{id}/rebuild`
    # does; a pinned build's geometry always comes from the cache/disk read `_resolve_session_geometry`
    # does, never a fresh solve. These stay UNGATED reads (the spec's "only writes are gated" rule),
    # resolving `session.level` via `_require_session`.
    @app.get("/api/session/{session_id}/scene")
    def session_scene(session_id: str) -> dict:
        session = _require_session(session_id)
        search_files, index, defaults = _current_scene_inputs(session.level)
        trunk_state = _get_trunk(session.level, search_files, index, defaults)
        geometry = _resolve_session_geometry(session_id, session.level)
        if geometry is None:
            payload = build_wireframe_payload(trunk_state, index, defaults)
        else:
            payload = build_scene_payload(trunk_state, geometry, index, defaults)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors],
            "geometry_pinned": geometry is not None,
        }

    @app.get("/api/session/{session_id}/atlas")
    def session_atlas(session_id: str) -> dict:
        # Sprites, mesh textures AND Mover textures are all Load-owned (unaffected by whether
        # geometry exists), so those three always ride on `trunk_state`'s own texture tables.
        # With a build pinned, `geometry.texture_table` is prepended -- the same order
        # `build_scene_payload` uses when it offsets `ScenePoly.tex_index` into this atlas.
        session = _require_session(session_id)
        search_files, index, defaults = _current_scene_inputs(session.level)
        trunk_state = _get_trunk(session.level, search_files, index, defaults)
        geometry = _resolve_session_geometry(session_id, session.level)
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

    @app.get("/api/session/{session_id}/lightmap")
    def session_lightmap(session_id: str) -> dict:
        # No trunk read needed when nothing is pinned: unlike `/scene`/`/atlas`, this route never
        # touches actor/sprite data. With a build pinned, the packed poly list must be the SAME
        # filtered set `build_scene_payload` built its own payload from (`filtered_geometry_polys`
        # is the ONE filter function both go through, so the two routes' poly-index positions can't
        # drift) -- needs a real trunk read for `_resolve_hidden_ed`'s own `bHiddenEd` check.
        session = _require_session(session_id)
        geometry = _resolve_session_geometry(session_id, session.level)
        if geometry is None:
            polys: list[tuple] = []
        else:
            search_files, index, defaults = _current_scene_inputs(session.level)
            trunk_state = _get_trunk(session.level, search_files, index, defaults)
            hidden_ed = _resolve_hidden_ed(trunk_state.level, defaults)
            polys = [poly for poly, _owner in
                    filtered_geometry_polys(trunk_state.level, geometry, hidden_ed)]
        png_bytes, manifest, width, height, intensity = build_lightmap_atlas(polys)
        return {
            "width": width,
            "height": height,
            "intensity": intensity,
            "manifest": manifest,
            "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        }

    # Plan Task 3: thin HTTP adapters over `edits.py`'s stage/discard/save (Task 2) and
    # `StagingStore.read_staged` (Task 1) -- no business logic here, matching every route above.
    # Sync `def`: none of these does a slow CSG solve, but a trunk load/save is still blocking file
    # I/O, so it belongs in Starlette's threadpool, not the event loop.
    #
    # The Decimal/JSON boundary lives ONLY here: JSON has no `Decimal` type, so every incoming
    # `[x, y, z]` array is parsed via `Decimal(str(v))` -- never `Decimal(v)` on the already-lossy
    # parsed float -- before it reaches `edits.py`/`snapshots.py`, and every outgoing `Decimal`
    # tuple is serialized back to `[float(d) for d in loc]`. Neither of those two modules ever sees
    # a `float`.
    def _parse_location(arr) -> tuple[Decimal, Decimal, Decimal]:
        return tuple(Decimal(str(v)) for v in arr)

    def _serialize_location(loc: tuple[Decimal, Decimal, Decimal]) -> list[float]:
        return [float(d) for d in loc]

    def _serialize_conflicts(conflicts) -> list[dict]:
        return [
            {
                "name": c.name,
                "staged_location": _serialize_location(c.staged_location),
                "trunk_location": _serialize_location(c.trunk_location),
            }
            for c in conflicts
        ]

    # Task 13: `load`/`stage`/`discard`/`save` all require the `X-Claim-Token` header, same as
    # Task 11's `rebuild` -- every one of them mutates this session's own state (`load` bumps
    # `last_seen_generation`, `stage`/`discard` write `staged.json`, `save` writes the trunk plus
    # the level pin), so a stale token gets the identical 409 `rebuild` already gives. Unlike
    # `rebuild` (which checks only AFTER its expensive CSG solve), none of these four has an
    # expensive precursor -- the claim check runs BEFORE any write, under
    # `_claims.lock_for(session_id)`, so a stale token never performs a write at all (nothing to
    # discard on failure, unlike `rebuild`'s in-flight solve result). Fix round 1 (Task 13, Finding
    # 1): each of the four also re-checks `sessions.get_session(...) is None` under the SAME lock,
    # right after the claim check passes and before its first write side-effect -- the same
    # existence re-check `session_rebuild` already does, for the same reason (see its own comment
    # above): the claim-token check alone can't distinguish "deleted mid-request" from "never
    # claimed", so a DELETE racing this request's entry-to-lock window would otherwise resurrect
    # the just-removed session directory.
    @app.post("/api/session/{session_id}/load")
    def session_load(session_id: str, request: Request, body: dict | None = None) -> dict:
        # The explicit Load action (spec §2), re-keyed to session_id (Task 13). Plan Task 4:
        # symmetric with Save's staged-edit conflict check, in the reverse direction --
        # `edits.check_load_conflicts` reports (never blocks) when an external trunk change
        # collides with a staged edit. Load carries no data-loss risk (nothing is written to the
        # trunk here), so the refresh below always completes once the claim check passes.
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return JSONResponse(status_code=409, content={"error": "session superseded"})
            # Fix round 1 (Task 13, Finding 1): same two-part reasoning as `session_rebuild`'s own
            # existence re-check -- `_claims.check` alone can't tell "deleted mid-request" apart
            # from "never claimed", so a DELETE racing this request's own entry-to-lock window would
            # otherwise sail through the check above.
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_load_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            ctx = _get_or_create_level_context(session.level)
            resolutions = (body or {}).get("resolutions") or {}
            search_files, index, defaults = _scene_inputs(project)
            lvl, ranks, _bodies, folders = trunk.read_level_with_bodies(maps_root / session.level)
            conflicts = edits.check_load_conflicts(
                session_id, lvl, store=_staging_store, resolutions=resolutions)
            sprite_table, actor_sprites = resolve_actor_sprites(lvl, search_files, defaults)
            mesh_polys, mesh_owners, mesh_texture_table = resolve_mesh_scene_polys(
                lvl, index, search_files, defaults)
            mover_polys, mover_owners, mover_texture_table = resolve_mover_scene_polys(
                lvl, index, search_files, defaults)
            loaded = _LoadedTrunk(level=lvl, ranks=ranks, folders=folders,
                                  sprite_table=sprite_table, actor_sprites=actor_sprites,
                                  mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                                  mesh_texture_table=mesh_texture_table,
                                  mover_polys=mover_polys, mover_owners=mover_owners,
                                  mover_texture_table=mover_texture_table)
            # Written BEFORE `ctx.trunk_ref[0]` (same reasoning as `_get_trunk`'s bootstrap
            # branch): a concurrent `/scene`/`/atlas`/`/lightmap` must never observe the NEW trunk
            # paired with the PREVIOUS `ctx.scene_inputs_ref[0]`.
            ctx.scene_inputs_ref[0] = (search_files, index, defaults)   # seeds /scene,/atlas,/lightmap
            ctx.trunk_ref[0] = loaded
            ctx.changes_available[0] = False
            # Task 13's own plan text: Load bumps this session's high-water mark of the trunk
            # generation it has actually seen -- `sessions.py` (Task 6) already has this function,
            # unused until now.
            sessions.set_last_seen_generation(_sessions_root, session_id, ctx.generation[0])
            return {"status": "ok", "conflicts": _serialize_conflicts(conflicts)}

    @app.post("/api/session/{session_id}/stage")
    def session_stage(session_id: str, body: dict, request: Request) -> dict:
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return JSONResponse(status_code=409, content={"error": "session superseded"})
            # Fix round 1 (Task 13, Finding 1): the concrete repro the review found -- a DELETE
            # racing this request's own entry-to-lock window would otherwise sail through the
            # `_claims.check` above (it auto-accepts once `forget()` has cleared the recorded
            # token) and `edits.stage_locations` would then resurrect the just-removed
            # `sessions/<sid>/` directory via `atomic_write_json`'s unconditional `mkdir`. Re-check
            # existence here, under the same lock DELETE takes around its own forget+delete.
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_stage_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            actors = body.get("actors") or {}
            moves = {name: _parse_location(loc) for name, loc in actors.items()}
            staged = edits.stage_locations(project, session.level, moves,
                                           store=_SessionKeyedStore(_staging_store, session_id))
            # Final-review fix round, Finding 3: a re-stage can orphan the actor's PREVIOUS blob
            # (its content-addressed hash changes, the old one is no longer named by any manifest)
            # -- opportunistic eviction on the write path that could free one, per the spec.
            _staging_store.evict_unreferenced_blobs(live_hashes=_live_blob_hashes(),
                                                    max_bytes=_staging_blobs_max_bytes)
            return {"staged": staged}

    @app.post("/api/session/{session_id}/discard")
    def session_discard(session_id: str, request: Request, body: dict | None = None) -> dict:
        # `actors`: an optional subset of staged actor names to discard, leaving every other
        # staged actor's edit in place -- lets the Save conflict-resolution UI drop one conflicting
        # actor's stage without discarding unrelated staged work. Omitted/`None` -> the original
        # whole-session discard. `discard_staged`'s own `level_name` parameter is used ONLY as the
        # store key (it never touches the trunk), so `session_id` is passed straight through to the
        # real `_staging_store` -- no `_SessionKeyedStore` wrapper needed here (unlike stage/save).
        _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return JSONResponse(status_code=409, content={"error": "session superseded"})
            # Fix round 1 (Task 13, Finding 1): same re-check as `session_stage`/`session_load`/
            # `session_save` -- `discard_staged` also writes (or removes) `staged.json` through
            # `_staging_store`, so a DELETE racing this request's entry-to-lock window must not be
            # allowed to resurrect the session directory here either.
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_discard_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            actors = (body or {}).get("actors")
            edits.discard_staged(project, session_id, store=_staging_store, actors=actors)
            # Final-review fix round, Finding 3: discarding is exactly the write that frees a
            # blob's last reference -- evict opportunistically right here.
            _staging_store.evict_unreferenced_blobs(live_hashes=_live_blob_hashes(),
                                                    max_bytes=_staging_blobs_max_bytes)
            return {"status": "ok"}

    @app.post("/api/session/{session_id}/save")
    def session_save(session_id: str, body: dict, request: Request) -> dict:
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return JSONResponse(status_code=409, content={"error": "session superseded"})
            # Fix round 1 (Task 13, Finding 1): same re-check as `session_stage`/`session_load`/
            # `session_discard` -- `save_staged` writes the trunk itself, the highest-stakes write
            # of the four, so a DELETE racing this request's entry-to-lock window must not be
            # allowed through here either.
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_save_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            resolutions = body.get("resolutions") or {}
            result = edits.save_staged(project, session.level,
                                       store=_SessionKeyedStore(_staging_store, session_id),
                                       resolutions=resolutions)
            # Final-review fix round, Finding 3: Save clears every applied actor's stage --
            # exactly the write that frees a blob's last reference -- evict opportunistically here.
            _staging_store.evict_unreferenced_blobs(live_hashes=_live_blob_hashes(),
                                                    max_bytes=_staging_blobs_max_bytes)

        # Pin promotion, sequenced AFTER the trunk write above: under `ctx.trunk_lock` -- the
        # existing per-level write serialization (unchanged in purpose), NOT the per-session claim
        # lock, which is already released by the `with` block's exit above (the two locks are
        # never held simultaneously). `SessionPointerCorruptError` here is the NORMAL "this session
        # never ran a Rebuild" case, not corruption -- skip promotion and leave the level's
        # existing pin (whatever it currently holds, if anything) untouched.
        ctx = _get_or_create_level_context(session.level)
        with ctx.trunk_lock:
            try:
                geom_hash, light_hash = build_pin.load_session_pointer(_sessions_root, session_id)
            except build_pin.SessionPointerCorruptError:
                pass
            else:
                build_pin.write_level_pointer(project, session.level, geom_hash, light_hash)

        return {
            "applied": result.applied,
            "conflicts": _serialize_conflicts(result.conflicts),
        }

    @app.get("/api/session/{session_id}/staged")
    def session_staged(session_id: str) -> dict:
        _require_session(session_id)
        return {
            name: {
                "staged_location": _serialize_location(entry.staged_location),
                "baseline_location": _serialize_location(entry.baseline_location),
            }
            for name, entry in _staging_store.read_staged(session_id).items()
        }

    if fault_route:
        @app.get("/api/_boom")
        async def _boom():
            raise CommandError("Actor not found: Foo")

    # Plan Task 12: session CRUD. Unlike every other route in this file (which raises `CommandError`
    # for a clean "not found" 422 via the shared `error_to_status` exception handler), GET/DELETE's
    # "unknown id" case here returns a literal `404` via a direct `JSONResponse` -- the plan's own
    # brief specifies exactly that status for these two routes, a deliberate, narrower departure from
    # the 422-everywhere convention Task 11 established for `POST /api/session/{id}/rebuild`'s
    # analogous case. Flagged, not silently reconciled either way.
    @app.post("/api/level/{level_name}/sessions", status_code=201)
    def create_session_route(level_name: str) -> dict:
        # Creating a session establishes its own first claim -- nothing to supersede yet (spec's
        # claim-token note under "Session identity & lifecycle").
        _require_level(level_name)
        # Bug found post-merge: a fresh session used to always start at last_seen_generation=0,
        # so any level whose trunk had changed on disk even once since the server started (common,
        # not exotic) immediately showed "changes available" for a change this session never had a
        # chance to see. Seed it from the level's OWN current generation instead -- read as late as
        # possible, right before the write, to minimize (not that it needs to be zero: see
        # `create_session`'s own docstring for why any race here is safe-by-construction) the window
        # between this read and the persisted write.
        ctx = _get_or_create_level_context(level_name)
        rec = sessions.create_session(_sessions_root, level_name,
                                      last_seen_generation=ctx.generation[0])
        token = _claims.mint(rec.id)
        return {"id": rec.id, "level": rec.level, "created_at": rec.created_at,
                "claim_token": token}

    @app.get("/api/sessions")
    def list_sessions_route() -> dict:
        # A pure read: no claim token is required to call this, and none is minted either -- unlike
        # `GET /api/session/{id}` below, minting a token per listed session here would supersede
        # every open session's claim on every poll of the session-picker dropdown, which is not what
        # "listing" should do.
        return {
            "sessions": [
                {"id": r.id, "level": r.level, "created_at": r.created_at,
                 "last_active_at": r.last_active_at}
                for r in sessions.list_sessions(_sessions_root)
            ],
        }

    @app.get("/api/session/{session_id}")
    def get_session_route(session_id: str):
        # Mints a FRESH claim_token on every call, superseding whatever claim existed before -- this
        # is the spec's "resolving a session" operation, the same one a page load/reload performs
        # ("Reloading re-resolves the session fresh, mints a new claim ... supersedes whichever
        # window currently holds it"). Deliberately NOT idempotent in that sense: two GETs in quick
        # succession genuinely hand write ownership to whichever one landed last, by design -- the
        # mechanism that makes "whichever window last loaded always wins" true.
        rec = sessions.get_session(_sessions_root, session_id)
        if rec is None:
            return JSONResponse(status_code=404,
                                content={"error": f"session not found: {session_id!r}"})
        token = _claims.mint(session_id)
        return {"id": rec.id, "level": rec.level, "created_at": rec.created_at,
                "last_active_at": rec.last_active_at, "claim_token": token}

    @app.delete("/api/session/{session_id}", status_code=204)
    def delete_session_route(session_id: str, request: Request, force: bool = False):
        # Explicit close (spec, "API surface"): removes `sessions/<sid>/` entirely. A mutation, so
        # it needs a valid claim_token like any other write; destructive, so it also follows the
        # project's "never irretrievably clobber" convention -- refuses 409 on non-empty staged
        # edits unless `?force=true`.
        rec = sessions.get_session(_sessions_root, session_id)
        if rec is None:
            return JSONResponse(status_code=404,
                                content={"error": f"session not found: {session_id!r}"})

        token = request.headers.get("X-Claim-Token", "")
        if not _claims.check(session_id, token):
            return JSONResponse(status_code=409, content={"error": "session superseded"})

        if not force and _staging_store.read_staged(session_id):
            return JSONResponse(
                status_code=409,
                content={"error": "session has unsaved edits; pass ?force=true to close anyway"})

        # "closing every open WS connection for that session" (spec) is done here only PASSIVELY,
        # not by an active push: `delete_session_route` never reaches into `/ws` directly --
        # `LevelContext.connections` (the only WS connection set that exists in this app) stays
        # keyed per-LEVEL, not per-session, so this route has no way to find "just this session's"
        # connection among a level's other open ones without a new WS-to-session tracking structure,
        # which no task's brief has asked for and this route doesn't add on its own initiative.
        # Instead, `ws_endpoint`'s own poll loop (Task 15 fix round 1) re-checks
        # `sessions.get_session(...) is None` on every tick, BEFORE the claim check -- this closes
        # the gap `forget(session_id)` would otherwise leave (a deleted session's stale token
        # auto-re-accepting itself forever via `claims.check`'s first-claim semantics), at the cost
        # of up to `_WS_CLAIM_POLL_INTERVAL_S` of lag rather than an immediate close.
        #
        # Fix round 1, Finding 1: forget+delete run under the SAME per-session lock
        # `session_rebuild`'s write-time critical section uses, so an in-flight Rebuild's
        # claim-check-then-write can't interleave with this delete arbitrarily -- whichever side
        # gets the lock first completes cleanly, and `session_rebuild`'s own existence re-check
        # (added in the same fix) catches the case where this delete won the race.
        #
        # Fix round 2, Finding 1 (re-review of round 1): `delete_session` MUST run before `forget`,
        # not after. `forget()` pops this session_id's entry out of `_claims._session_locks` as a
        # side effect -- the moment it returns, the *registry* no longer knows about this lock, even
        # though the `with` block below is still holding the actual `Lock` object and hasn't exited.
        # `sessions.delete_session` does a real `shutil.rmtree`, which can release the GIL mid-call;
        # if `forget()` ran first, any other thread calling `_claims.lock_for(session_id)` during that
        # window gets handed a brand-new, independent `Lock` (not the one we're holding) and proceeds
        # unguarded for the rest of the rmtree -- exactly the race this lock exists to prevent. Doing
        # the delete first keeps the registered lock valid for the whole removal; only once the
        # directory is truly gone does `forget()` retire the registry entry.
        with _claims.lock_for(session_id):
            sessions.delete_session(_sessions_root, session_id)
            _claims.forget(session_id)
        return Response(status_code=204)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        # Task 15: `/ws` is now genuinely session-scoped, not bound to a single startup level.
        # The client must present `?session=<id>&claim=<token>` -- no back-compat no-params legacy
        # mode (CLAUDE.md). Both are validated up front: `sessions.get_session` confirms the session
        # exists, `_claims.check` confirms the presented token is (or becomes, per its own documented
        # first-claim semantics) the session's current claim. Every session that exists was minted a
        # token by `create_session_route`/`get_session_route` at creation time, so `_claims.check`'s
        # existence-agnostic three-state rule (unrecorded id -> auto-accept, recorded id -> exact
        # match) already gives the right refuse/accept behavior here with no extra "was this session
        # ever claimed" check needed -- the `sessions.get_session` call above is what supplies the
        # "does it exist" half.
        #
        # Two different refusal shapes (fix round 1, Important finding): an unknown/deleted session
        # or a request with no claim token at all is not something a retry can ever fix, so that case
        # calls `websocket.close()` directly, without ever calling `.accept()` -- confirmed against
        # Starlette 1.6's own `WebSocket.send`/`accept` source (not assumed): while `application_state`
        # is still CONNECTING, `send()` allows a "websocket.close" ASGI message (in addition to
        # "websocket.accept"), so this cleanly rejects the upgrade, and the client never sees an
        # accepted connection at all. A STALE claim on an EXISTING session is different -- the client
        # needs to actually learn that (see below), so that case does accept, briefly, to say so.
        session_id = websocket.query_params.get("session")
        claim_token = websocket.query_params.get("claim")
        session = sessions.get_session(_sessions_root, session_id) if session_id else None
        if session is None or not claim_token:
            await websocket.close(code=4001, reason="unknown session or missing claim token")
            return
        if not _claims.check(session_id, claim_token):
            # Fix round 1, Important finding: unlike the case above, the session genuinely exists --
            # this token is merely STALE (a newer claim was minted elsewhere, e.g. another window
            # opened the same session). The client needs to actually learn that, the same way the
            # mid-poll rejection below already tells it, so accept just long enough to push the same
            # "superseded" signal before closing -- a bare close here (as the old, undifferentiated
            # 4001 path did) is indistinguishable from a transient drop and would make a reconnecting
            # client retry this exact stale token forever.
            await websocket.accept()
            await websocket.send_json({"type": "superseded"})
            await websocket.close(code=4003, reason="session claimed by another connection")
            return

        # Joins the level's own `connections` set -- the pre-existing, UNRELATED trunk-watcher
        # broadcast mechanism (`_broadcast_changes_available`) this route already fed into, still
        # needed so a session-scoped connection keeps receiving "changes_available" pushes exactly
        # as before. `_get_or_create_level_context` is idempotent, so a session on the startup
        # level reuses `_startup_ctx` unchanged; a session on any other level lazily gets its own.
        ctx = _get_or_create_level_context(session.level)
        # Final-review fix round, Finding 5: `_get_or_create_level_context` builds a level's
        # `TrunkWatcher` but never STARTS one for a lazily-created (non-startup) level -- Task 9's
        # own docstring said a later async-context caller should do this, and none did. This route
        # is exactly that caller: `async def`, reached on every connect, and idempotent to check
        # (`TrunkWatcher.start()` itself is NOT idempotent -- calling it twice would leak the old
        # `_watch_task`). The startup level's watcher is already started by `_lifespan`, so
        # `ctx.watcher.started` is already True there and this is a no-op for it.
        if not ctx.watcher.started:
            ctx.watcher.start()
        await websocket.accept()
        ctx.connections.add(websocket)
        try:
            while True:
                # Poll, not push: `claims.mint` is called from plain sync routes (`create_session_route`/
                # `get_session_route`), which FastAPI/Starlette run in a worker THREAD, not on this
                # coroutine's event loop -- there is no cheap direct way for that thread to push into an
                # already-open WS living on a different thread's loop without a real cross-thread-to-loop
                # bridge, which doesn't exist anywhere in this codebase today. Re-checking the claim on
                # every receive-timeout tick stays entirely inside this already-correct async context, at
                # the cost of up to `_WS_CLAIM_POLL_INTERVAL_S` of lag before a superseded connection
                # learns about it.
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=_WS_CLAIM_POLL_INTERVAL_S)
                except asyncio.TimeoutError:
                    # Fix round 1, Critical finding: check existence BEFORE the claim check.
                    # `ClaimRegistry.check`'s own documented semantics auto-accept an *unrecorded*
                    # session id as a legitimate first claim -- exactly the state `forget()` (called
                    # by `delete_session_route`) leaves behind. Without this existence re-check, a
                    # deleted session's still-open WS would have its own stale token auto-accepted
                    # forever (re-recording it each tick) and never learn the session is gone -- the
                    # gap flagged in this route's own comment above. Both cases are reported to the
                    # client as the same `{"type": "superseded"}` message: from the client's point of
                    # view the practical action is identical either way ("this session is gone from
                    # under you, stop editing"), so there is no reason to teach it a second shape. The
                    # close code/reason differs only for a human reading server logs/network tab:
                    # 4004 = session no longer exists at all; 4003 = it exists but another connection
                    # now holds its claim.
                    if sessions.get_session(_sessions_root, session_id) is None:
                        await websocket.send_json({"type": "superseded"})
                        await websocket.close(code=4004, reason="session deleted")
                        return
                    if not _claims.check(session_id, claim_token):
                        await websocket.send_json({"type": "superseded"})
                        await websocket.close(code=4003, reason="session claimed by another connection")
                        return
                    # else: still current -- nothing arrived this tick, just poll again.
        except WebSocketDisconnect:
            pass
        finally:
            ctx.connections.discard(websocket)   # also drop on any other receive error

    frontend_dist = _frontend_dist_dir()
    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:
        # WARNING, not INFO: `uedcli serve`'s own uvicorn.run(..., log_level="info") only
        # configures uvicorn's OWN namespaced loggers, not this module's -- an unconfigured
        # `uedcli.serve.app` logger's effective level is Python's default WARNING, so an .info()
        # call here would be silently dropped (verified live: isEnabledFor(INFO) is False under
        # uvicorn's actual LOGGING_CONFIG). A plain dev checkout without `npm run build` hits this
        # every time, which is expected and not alarming -- but it must actually reach the user,
        # or a packaging drift (the standalone binary's web/dist copy landing somewhere this path
        # doesn't check) silently serves API-only with no signal at all, the opposite of the point.
        logger.warning("frontend_dist_not_found",
                        extra={"checked_path": str(Path(__file__).resolve().parents[2] / "web" / "dist")})

    return app
