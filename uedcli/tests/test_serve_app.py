"""`uedcli serve`'s FastAPI app skeleton: the health route, the structured-error exception handler
(no Python exception reaches the user — CLAUDE.md), and the shared in-process trunk/geometry/payload
cache (`dev/docs/board/to-build/uedcli-serve-share-one-in-process-scene-cache/`) that makes `/scene`/
`/atlas` share one trunk-read + `resolve_actor_sprites` call per settled trunk state, with a
generation guard against a slow build publishing a stale result over a concurrent invalidation.

gui-explicit-rebuild-pinned-build-state-mode (Task 2) removed that sibling spec's auto-building
`_get_geometry()` entirely: `build_scene` is now called ONLY from `_build_and_publish_geometry`,
reached ONLY via `POST /rebuild` — `_read_geometry()` is a pure read `/scene`/`/atlas`/`/lightmap`
use instead, never solving as a side effect of being fetched. The payload slot (`_get_payload`,
covering `build_scene_payload`/`build_wireframe_payload`'s own per-actor class resolution) was
added after a live WanChai-scale perf bug — see `scene.py::build_scene_payload`'s docstring."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from uedcli.serve.app import create_app


def _project(tmp_path):
    return SimpleNamespace(root=str(tmp_path), maps=None)


def _require_ued22():
    """Every shared-cache test below exercises `resolve_actor_sprites`/`build_scene`'s real class
    resolution (`_is_hidden_ed`, `movers.is_mover`), so — like `test_serve_scene.py` — they need
    the committed UED22 corpus and the native extension; skip cleanly without either."""
    pytest.importorskip("uedcli_native")
    from uedcli.tests.test_serve_scene import UED22
    if not (UED22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present (build_scene needs real class schemas)")


def test_health_reports_the_served_level(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "level": "TestLevel"}


def test_fault_route_is_absent_by_default(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    assert c.get("/api/_boom").status_code == 404


def test_fault_route_renders_a_structured_error_not_a_traceback(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel", fault_route=True)
    # `raise_server_exceptions=False`: a bare-`Exception` handler DOES produce the real HTTP
    # response in production, but `TestClient` re-raises server exceptions for debugging by
    # default even when a handler caught them — this is what the flag turns off, per Starlette's
    # own documented caveat, not a change to how the app itself behaves.
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/_boom")
    assert r.status_code == 422
    assert r.json() == {"error": "Actor not found: Foo"}


def test_status_route_reports_no_build_on_a_freshly_created_app(tmp_path):
    """gui-explicit-rebuild plan Task 4 / spec test #1: a freshly created app (no on-disk pointer,
    no prior Rebuild) reports the wire-only state on `/status`."""
    from uedcli.tests.conftest import cube_room

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    r = c.get("/api/level/TestLevel/status")
    assert r.status_code == 200
    assert r.json() == {"changes_available": False, "geometry_pinned": False,
                        "build_status": "no_build"}


def test_status_route_reflects_a_successful_rebuild(tmp_path, monkeypatch):
    """gui-explicit-rebuild plan Task 4 / spec test #7 (the review-flagged "must actually test the
    gate re-opening, not just the locked state"): after `_build_and_publish_geometry` populates the
    slot, `/status` flips `geometry_pinned` False -> True and `build_status` "no_build" -> "built"."""
    _require_ued22()
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    before = c.get("/api/level/TestLevel/status").json()
    assert before == {"changes_available": False, "geometry_pinned": False,
                      "build_status": "no_build"}

    app.state.build_and_publish_geometry("TestLevel", [], _ued22_index(), DEFAULTS)

    after = c.get("/api/level/TestLevel/status").json()
    assert after == {"changes_available": False, "geometry_pinned": True, "build_status": "built"}


def test_status_route_reports_changes_available_after_a_settled_trunk_edit(tmp_path):
    from uedcli.tests.conftest import cube_room

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    asyncio.run(app.state.on_trunk_settled())

    assert c.get("/api/level/TestLevel/status").json()["changes_available"] is True


def test_broadcast_changes_available_survives_a_connection_change_mid_broadcast(tmp_path):
    """Regression (review finding): `_broadcast_changes_available` used to iterate the live
    `connections` set while `await`ing each send — a client connecting mid-broadcast (the
    multi-viewer scenario the spec explicitly allows) grows the set's size during iteration and
    raises `RuntimeError: Set changed size during iteration`, silently dropping the whole push for
    every connected client. (A discard+add pair that returns the set to its ORIGINAL size doesn't
    reliably trigger CPython's check — a net size CHANGE, as a real new connection causes, does.)"""
    app = create_app(_project(tmp_path), "TestLevel")

    class FakeWS:
        def __init__(self):
            self.sent = []
            self.on_send = None

        async def send_json(self, data):
            self.sent.append(data)
            if self.on_send:
                self.on_send()

    ws_a, ws_b = FakeWS(), FakeWS()
    app.state.connections.add(ws_a)

    def connect_mid_broadcast():
        # Simulate a second viewer's WebSocket connecting while ws_a's send is in flight.
        app.state.connections.add(ws_b)

    ws_a.on_send = connect_mid_broadcast

    asyncio.run(app.state.broadcast_changes_available())  # must not raise

    assert ws_a.sent == [{"type": "changes_available", "level": "TestLevel"}]
    assert app.state.connections == {ws_a, ws_b}


def _write_fixture_trunk(root, level_name, actors) -> None:
    from uedcli import trunk as trunk_module
    from uedcli.model import Level

    maps_dir = root / "maps" / level_name
    maps_dir.mkdir(parents=True)
    ranks = {a.name: f"n{i:03d}" for i, a in enumerate(actors)}
    trunk_module.write_level(maps_dir, Level(actors={a.name: a for a in actors},
                                             order=[a.name for a in actors]), ranks)


def test_get_trunk_second_call_is_a_cache_hit(tmp_path, monkeypatch):
    """Task 1: `_get_trunk` double-checked-locking — a second call with an unchanged trunk returns
    the SAME `_LoadedTrunk` object (`is`, not `==`) without re-reading the trunk from disk."""
    _require_ued22()
    from uedcli import trunk as trunk_module
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")

    calls = []
    real = trunk_module.read_level_with_bodies

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(trunk_module, "read_level_with_bodies", spy)

    first = app.state.get_trunk("TestLevel", [], DEFAULTS)
    second = app.state.get_trunk("TestLevel", [], DEFAULTS)
    assert first is second
    assert len(calls) == 1


def test_read_geometry_never_builds_regardless_of_slot_state(tmp_path, monkeypatch):
    """gui-explicit-rebuild plan Task 2: `_read_geometry()` is a pure read -- it must never call
    `build_scene`, whether the slot is empty (`None`, the common cold-open case) or already
    populated by a prior Rebuild (`app.state.build_and_publish_geometry`, the only other way to
    populate it)."""
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")

    calls = []
    real_build_scene = serve_app._build_scene

    def spy(*a, **k):
        calls.append(1)
        return real_build_scene(*a, **k)

    monkeypatch.setattr(serve_app, "_build_scene", spy)

    assert app.state.read_geometry() is None
    assert not calls                                          # empty slot: no build

    index = _ued22_index()
    app.state.build_and_publish_geometry("TestLevel", [], index, DEFAULTS)
    assert len(calls) == 1                                    # the Rebuild itself DID build

    calls.clear()
    assert app.state.read_geometry() is not None
    assert not calls                                          # populated slot: STILL no build


def test_build_and_publish_geometry_is_the_only_thing_that_calls_build_scene(tmp_path, monkeypatch):
    """gui-explicit-rebuild plan Task 2 (contrast case): `_build_and_publish_geometry()` DOES call
    `build_scene` and publishes its result into the slot `_read_geometry()` then sees."""
    _require_ued22()
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")

    assert app.state.read_geometry() is None

    index = _ued22_index()
    built = app.state.build_and_publish_geometry("TestLevel", [], index, DEFAULTS)

    assert {name for name, _i_brush_poly in built.owners} == {"Room"}
    assert app.state.read_geometry() is built


def test_scene_atlas_lightmap_cold_never_trigger_a_build(tmp_path, monkeypatch):
    """gui-explicit-rebuild plan Task 2, the review-mandated regression: a freshly created app (no
    on-disk pointer, `/rebuild` never called) serves all three routes with NO solved geometry and
    NEVER calls `build_scene` -- the exact gap a naively-wired `/scene` would have (still calling
    the sibling scene-cache spec's auto-building `_get_geometry()`)."""
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    calls = []
    real_build_scene = serve_app._build_scene

    def spy(*a, **k):
        calls.append(1)
        return real_build_scene(*a, **k)

    monkeypatch.setattr(serve_app, "_build_scene", spy)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.get("/api/level/TestLevel/scene")
    assert r.status_code == 200
    body = r.json()
    assert body["polys"] == []
    assert body["geometry_pinned"] is False
    assert {a["name"] for a in body["actors"]} == {"Room"}   # actors still populated from the trunk

    r = c.get("/api/level/TestLevel/atlas")
    assert r.status_code == 200

    r = c.get("/api/level/TestLevel/lightmap")
    assert r.status_code == 200
    body = r.json()
    assert body["manifest"] == {}

    assert not calls   # zero build_scene calls across all three routes


def test_scene_and_atlas_share_one_trunk_read_even_cold(tmp_path, monkeypatch):
    """`/scene` and `/atlas` both call `_get_trunk` -- an unchanged trunk means ONE real trunk-read
    shared between them, cold-open included (no geometry pin needed for this sharing to hold --
    `/lightmap` needs no trunk at all now, since it only ever reads `geometry.polys`)."""
    _require_ued22()
    from uedcli import trunk as trunk_module
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))

    trunk_calls = []
    real_trunk = trunk_module.read_level_with_bodies

    def trunk_spy(*a, **k):
        trunk_calls.append(1)
        return real_trunk(*a, **k)

    monkeypatch.setattr(trunk_module, "read_level_with_bodies", trunk_spy)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert c.get("/api/level/TestLevel/lightmap").status_code == 200

    assert len(trunk_calls) == 1


def test_on_trunk_settled_leaves_both_slots_untouched_bumps_generation_sets_changes_available(
        tmp_path, monkeypatch):
    """Task 3 (gui-explicit-rebuild spec §0/§2): the watcher's settle callback no longer clears
    EITHER cache slot -- Load owns `_trunk_ref`, Rebuild owns `_geometry_ref`, and a mere trunk
    change on disk must not silently discard an already-pinned Rebuild. It still bumps
    `_generation[0]` by exactly 1 (repurposed to guard a Rebuild's publish, not an automatic
    rebuild), sets `_changes_available[0]`, and still broadcasts -- now a `"changes_available"`
    message, never the old silent `"reload"`."""
    _require_ued22()
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")

    trunk_state = app.state.get_trunk("TestLevel", [], DEFAULTS)
    geometry = app.state.build_and_publish_geometry("TestLevel", [], _ued22_index(), DEFAULTS)
    assert app.state.changes_available[0] is False

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, data):
            self.sent.append(data)

    ws = FakeWS()
    app.state.connections.add(ws)
    gen_before = app.state.generation[0]

    asyncio.run(app.state.on_trunk_settled())

    assert ws.sent == [{"type": "changes_available", "level": "TestLevel"}]
    assert app.state.changes_available[0] is True
    assert app.state.generation[0] == gen_before + 1
    assert app.state.get_trunk("TestLevel", [], DEFAULTS) is trunk_state    # untouched -- same object, no re-read
    assert app.state.read_geometry() is geometry               # untouched -- same object, no rebuild


def test_generation_guard_retries_a_build_invalidated_mid_flight(tmp_path, monkeypatch):
    """Task 2's generation guard, updated for Task 3's landed behavior: a slow
    `_build_and_publish_geometry` build in flight must DISCARD its result and retry (re-derive,
    not just re-publish the same computed value) when `_generation[0]` moves mid-build, rather than
    publish blind. `_build_scene` is gated with a `threading.Event` so the block is deterministic.

    Deviation from the plan's original illustrative test (flagged, not silently dropped): the plan's
    Open Question 6 explicitly scopes OUT a Load-triggered generation bump, and Task 3 makes the
    watcher's own bump leave `_trunk_ref` untouched -- so, at this point in the plan (Task 5's
    explicit Load doesn't exist yet either), NOTHING can make a mid-flight retry actually observe a
    different trunk view: `_get_trunk()` just returns the same cached `_LoadedTrunk` object on
    retry. This test therefore asserts what the mechanism actually still guarantees here -- the
    build genuinely RETRIES (calls `_build_scene` again, not just returns the in-flight result) --
    rather than a "sees the post-edit data" outcome the current call graph cannot produce yet."""
    _require_ued22()
    from uedcli import trunk as trunk_module
    from uedcli.model import Level
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room(name="Room")
    trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]),
                             {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")

    real_build_scene = serve_app._build_scene
    build_entered = threading.Event()
    release_build = threading.Event()
    build_calls: list[int] = []

    def gated_build_scene(*a, **kw):
        build_calls.append(1)
        build_entered.set()
        release_build.wait(timeout=5)
        return real_build_scene(*a, **kw)

    monkeypatch.setattr(serve_app, "_build_scene", gated_build_scene)

    result: dict = {}

    def call_build_and_publish():
        search_files, index, defaults = serve_app._scene_inputs(project)
        result["geometry"] = app.state.build_and_publish_geometry("TestLevel", search_files, index, defaults)

    t = threading.Thread(target=call_build_and_publish)
    t.start()
    assert build_entered.wait(timeout=5)          # the slow build is now genuinely in flight

    asyncio.run(app.state.on_trunk_settled())       # bumps generation (no longer clears any slot)

    release_build.set()                             # let the in-flight build finish
    t.join(timeout=10)

    assert len(build_calls) == 2                    # discarded the first result and retried once
    assert {name for name, _i_brush_poly in result["geometry"].owners} == {"Room"}
    assert app.state.read_geometry() is result["geometry"]


def test_require_level_rejects_a_second_valid_but_different_level_name(tmp_path, monkeypatch):
    """Task 5: `_require_level` must reject a level name that is a real, existing directory under
    `maps/` but isn't the ONE level `create_app` fixed for this app's lifetime — otherwise the
    shared trunk/geometry cache (keyed on nothing but that fixed level) would silently serve the
    WRONG level's cached data instead of a clean 'not found'."""
    from uedcli import trunk as trunk_module
    from uedcli.tests.conftest import cube_room

    root = tmp_path / "proj"
    for name in ("TestLevel", "OtherLevel"):
        _write_fixture_trunk(root, name, [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    calls = []
    real = trunk_module.read_level_with_bodies

    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(trunk_module, "read_level_with_bodies", spy)
    app = create_app(project, "TestLevel")
    c = TestClient(app, raise_server_exceptions=False)

    r = c.get("/api/level/OtherLevel/scene")

    assert r.status_code == 422
    assert "not found" in r.json()["error"]
    assert not calls    # never touched OtherLevel's trunk -- rejected before any cache lookup


def test_scene_and_atlas_share_one_trunk_read_and_sprite_resolve(tmp_path, monkeypatch):
    """`/scene` and `/atlas` against an unchanged trunk share ONE trunk-read + ONE
    `resolve_actor_sprites` call (the redundant-work bug the shared trunk cache exists to fix) --
    `build_scene`/the native CSG solve is NOT part of this any more (gui-explicit-rebuild plan
    Task 2: cold routes never call it at all)."""
    _require_ued22()
    from uedcli import trunk as trunk_module
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))

    trunk_calls, sprite_calls = [], []
    real_trunk, real_sprites = trunk_module.read_level_with_bodies, serve_app.resolve_actor_sprites

    def trunk_spy(*a, **k):
        trunk_calls.append(1)
        return real_trunk(*a, **k)

    def sprite_spy(*a, **k):
        sprite_calls.append(1)
        return real_sprites(*a, **k)

    monkeypatch.setattr(trunk_module, "read_level_with_bodies", trunk_spy)
    monkeypatch.setattr(serve_app, "resolve_actor_sprites", sprite_spy)

    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/atlas").status_code == 200

    assert len(trunk_calls) == 1
    assert len(sprite_calls) == 1

    # gui-explicit-rebuild plan Task 3: a trunk edit + the watcher settling no longer invalidates
    # the trunk slot -- Load (Task 5) is the only thing that refreshes it. `/scene` right after
    # still serves the SAME (pre-edit) trunk read, no re-read.
    from uedcli.model import Level

    room2 = cube_room(name="Room2")
    trunk_module.write_level(root / "maps" / "TestLevel",
                             Level(actors={room2.name: room2}, order=[room2.name]),
                             {room2.name: "m"}, deleted={"Room"})
    asyncio.run(app.state.on_trunk_settled())

    r = c.get("/api/level/TestLevel/scene")
    assert r.status_code == 200
    assert {a["name"] for a in r.json()["actors"]} == {"Room"}   # still the pre-edit trunk

    assert len(trunk_calls) == 1
    assert len(sprite_calls) == 1
    assert app.state.changes_available[0] is True                # ...but the banner signal fired


def test_scene_route_reuses_payload_across_requests_despite_fresh_scene_inputs(tmp_path, monkeypatch):
    """Regression for the live WanChai perf bug (see `scene.py::build_scene_payload`'s docstring): in
    production, `_scene_inputs()` builds a BRAND NEW `ClassDefaults`/`ClassIndex` on every call --
    unlike every other test in this file, which monkeypatches `_scene_inputs` to one FIXED pair
    (masking exactly this bug, since a fixed `ClassDefaults`'s memo survives between calls on its
    own). Sharing only `_get_trunk`/`_get_geometry` and not `build_scene_payload`'s own output would
    still redo every actor's class resolution from scratch on a second `/scene` GET; `_get_payload`
    must make the second GET a genuine cache hit regardless of `_scene_inputs` handing it fresh
    `defaults`/`index` each time."""
    _require_ued22()
    from uedcli.classdefaults import ClassDefaults
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import _defaults_resolver, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs",
                        lambda p: ([], _ued22_index(), ClassDefaults(_defaults_resolver)))

    resolve_calls = []
    real_resolve = ClassDefaults._resolve

    def spy(self, fqcn):
        resolve_calls.append(fqcn)
        return real_resolve(self, fqcn)

    monkeypatch.setattr(ClassDefaults, "_resolve", spy)

    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    first_count = len(resolve_calls)
    assert first_count > 0                        # the cold build really did resolve some classes

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert len(resolve_calls) == first_count       # warm repeat: zero NEW class resolutions


def test_scene_route_geometry_pinned_flag_matches_the_payload_it_actually_returned(
        tmp_path, monkeypatch):
    """Review finding on the payload-cache fix: `scene()` used to read `_read_geometry()` a SECOND
    time, independently of `_get_payload`'s own internal read, purely to compute `geometry_pinned`.
    Under `_payload_lock` contention (this function's own slow path, ~28-37s on a real level), a
    concurrent `POST /rebuild` landing between those two reads could make the route report
    `geometry_pinned: true` for a response whose `polys` were actually built by
    `build_wireframe_payload` (empty) BEFORE the rebuild ever happened -- an internally inconsistent
    response. `_get_payload` now returns `(payload, geometry_pinned)` from the SAME `geometry` value
    it used to pick/cache the payload, so this can no longer disagree. `build_wireframe_payload` is
    gated with a `threading.Event` to make the race deterministic."""
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    real_build_wireframe = serve_app.build_wireframe_payload
    build_entered = threading.Event()
    release_build = threading.Event()

    def gated_build_wireframe(*a, **kw):
        build_entered.set()
        release_build.wait(timeout=5)
        return real_build_wireframe(*a, **kw)

    monkeypatch.setattr(serve_app, "build_wireframe_payload", gated_build_wireframe)

    response: dict = {}

    def call_scene():
        response["body"] = c.get("/api/level/TestLevel/scene").json()

    t = threading.Thread(target=call_scene)
    t.start()
    assert build_entered.wait(timeout=5)   # the wireframe build is now genuinely in flight

    # A concurrent Rebuild completes WHILE the above call is blocked on _payload_lock -- exactly
    # the window the review flagged.
    search_files, index, defaults = serve_app._scene_inputs(project)
    app.state.build_and_publish_geometry("TestLevel", search_files, index, defaults)
    assert app.state.read_geometry() is not None   # geometry really is pinned now

    release_build.set()
    t.join(timeout=10)

    body = response["body"]
    # The in-flight call captured a wireframe payload (empty polys) BEFORE the rebuild landed --
    # geometry_pinned must say so too, not report the geometry state as of AFTER this call returned.
    assert body["polys"] == []
    assert body["geometry_pinned"] is False


def test_concurrent_first_scene_requests_never_see_a_torn_trunk_build(tmp_path, monkeypatch):
    """8 concurrent, un-warmed `/scene` GETs race `_get_trunk`'s double-checked lock for the very
    first (automatic-initial-Load) build. Every response must come from the SAME single trunk
    build, never a torn read mixing partial state from two racing builders.

    (gui-explicit-rebuild plan Task 3 note: the sibling scene-cache spec's ORIGINAL version of this
    test raced an 8th thread's trunk edit + `on_trunk_settled()` invalidation against the other 7
    GETs -- that race no longer exists post-Task-3, since settling a trunk change no longer clears
    `_trunk_ref` at all (only an explicit Load does, Task 5). This test keeps the concurrency
    coverage that's still real: many simultaneous first-callers of `_get_trunk`'s slow path.)"""
    _require_ued22()
    from uedcli import trunk as trunk_module
    from uedcli.model import Level
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room(name="Room")
    trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]),
                             {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    barrier = threading.Barrier(8)
    results: list[dict] = []
    errors: list[Exception] = []

    def worker():
        try:
            barrier.wait()
            r = c.get("/api/level/TestLevel/scene")
            results.append(r.json())
        except Exception as e:                              # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 8
    for body in results:
        assert {a["name"] for a in body["actors"]} == {"Room"}   # every response, self-consistent


def test_switch_level_resets_all_three_cache_slots(tmp_path, monkeypatch):
    """quad-layout Part 7, Task 25 (adapted to current reality): the shared-cache spec's
    `_trunk_ref`/`_geometry_ref`/`_payload_ref` all cache data scoped to whichever level is
    currently served -- none of that is valid once `PUT /api/level` switches to a different one.
    Populate all three for the OLD level, switch, and confirm every slot is empty again (and
    `/status` reports the fresh "no_build" state, not a stale "built")."""
    _require_ued22()
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    _write_fixture_trunk(root, "Other", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    # Populate all three slots for "TestLevel".
    index = _ued22_index()
    app.state.get_trunk("TestLevel", [], DEFAULTS)
    app.state.build_and_publish_geometry("TestLevel", [], index, DEFAULTS)
    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert app.state.read_geometry() is not None
    gen_before = app.state.generation[0]

    r = c.put("/api/level", json={"level": "Other"})
    assert r.status_code == 200

    assert app.state.read_geometry() is None                    # _geometry_ref reset
    assert app.state.generation[0] == gen_before + 1             # bumped, guards any in-flight build
    status = c.get("/api/level/Other/status").json()
    assert status == {"changes_available": False, "geometry_pinned": False, "build_status": "no_build"}

    # A fresh trunk-read for "Other" happens lazily on the next real request (the SAME "automatic
    # initial Load" path a first-ever request takes) -- not a stale "TestLevel" trunk.
    body = c.get("/api/level/Other/scene").json()
    assert {a["name"] for a in body["actors"]} == {"Room"}
