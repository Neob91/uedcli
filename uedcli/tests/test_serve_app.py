"""`uedcli serve`'s FastAPI app skeleton: the health route, the structured-error exception handler
(no Python exception reaches the user — CLAUDE.md), and the shared in-process trunk/geometry cache
(`dev/docs/board/to-build/uedcli-serve-share-one-in-process-scene-cache/`) that makes `/scene`,
`/atlas`, `/lightmap` do one trunk-read + one `build_scene`/`resolve_actor_sprites` call each per
settled trunk state, with a generation guard against a slow build publishing a stale result over a
concurrent invalidation."""
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


def test_broadcast_reload_survives_a_connection_change_mid_broadcast(tmp_path):
    """Regression (review finding): `_broadcast_reload` used to iterate the live `connections` set
    while `await`ing each send — a client connecting mid-broadcast (the multi-viewer scenario the
    spec explicitly allows) grows the set's size during iteration and raises `RuntimeError: Set
    changed size during iteration`, silently dropping the whole reload push for every connected
    client. (A discard+add pair that returns the set to its ORIGINAL size doesn't reliably trigger
    CPython's check — a net size CHANGE, as a real new connection causes, does.)"""
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

    asyncio.run(app.state.broadcast_reload())  # must not raise

    assert ws_a.sent == [{"type": "reload", "level": "TestLevel"}]
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

    first = app.state.get_trunk([], DEFAULTS)
    second = app.state.get_trunk([], DEFAULTS)
    assert first is second
    assert len(calls) == 1


def test_get_geometry_second_call_is_a_cache_hit(tmp_path, monkeypatch):
    """Task 1: same double-checked-locking behavior for `_get_geometry` (spying on the native CSG
    solve, mirroring `test_serve_scene.py`'s retired `build_scene_payload`-level cache-hit test)."""
    _require_ued22()
    import uedcli_native

    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")

    calls = []
    real = uedcli_native.build_geometry_bspcsg

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(uedcli_native, "build_geometry_bspcsg", spy)

    index = _ued22_index()
    first = app.state.get_geometry([], index, DEFAULTS)
    second = app.state.get_geometry([], index, DEFAULTS)
    assert first is second
    assert len(calls) == 1


def test_on_trunk_settled_clears_both_slots_and_still_broadcasts(tmp_path, monkeypatch):
    """Task 2: the watcher's settle callback (`_on_trunk_settled`, wired in place of the raw
    `_broadcast_reload` as `TrunkWatcher`'s `on_change`) clears both cache slots so the next
    request rebuilds, AND still pushes the WS reload — same visible behavior as before this cache
    existed, just via one extra callback."""
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

    app.state.get_trunk([], DEFAULTS)
    assert len(calls) == 1

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, data):
            self.sent.append(data)

    ws = FakeWS()
    app.state.connections.add(ws)

    asyncio.run(app.state.on_trunk_settled())

    assert ws.sent == [{"type": "reload", "level": "TestLevel"}]   # broadcast still fires

    app.state.get_trunk([], DEFAULTS)
    assert len(calls) == 2                                        # cleared -> re-reads the trunk


def test_generation_guard_discards_a_build_invalidated_mid_flight(tmp_path, monkeypatch):
    """Task 2 (review-mandated): a slow `_get_geometry()` build in flight for the PRE-edit trunk
    must discard its result and rebuild against the POST-edit state when an invalidation lands
    mid-build, never publish the stale result. `_build_scene` is gated with a `threading.Event` so
    the block is deterministic, not timing-dependent — the concurrency test below can't exercise
    this (its fixture solves near-instantly, so the invalidation never actually lands DURING a
    build)."""
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

    def gated_build_scene(*a, **kw):
        build_entered.set()
        release_build.wait(timeout=5)
        return real_build_scene(*a, **kw)

    monkeypatch.setattr(serve_app, "_build_scene", gated_build_scene)

    result: dict = {}

    def call_get_geometry():
        search_files, index, defaults = serve_app._scene_inputs(project)
        result["geometry"] = app.state.get_geometry(search_files, index, defaults)

    t = threading.Thread(target=call_get_geometry)
    t.start()
    assert build_entered.wait(timeout=5)          # the slow build is now genuinely in flight

    room2 = cube_room(name="Room2")                # the "real edit" landing mid-build
    # `deleted={"Room"}`: two overlapping CSG_Subtract rooms at the SAME location merge their
    # coincident faces under CSG (confirmed by direct probe) -- deleting the old one keeps the
    # post-edit trunk unambiguous, so `owners` cleanly distinguishes "rebuilt from fresh state" from
    # "published the stale pre-edit result" (the exact race this test exists to catch).
    trunk_module.write_level(maps_dir, Level(actors={room2.name: room2}, order=[room2.name]),
                             {room2.name: "m"}, deleted={"Room"})
    asyncio.run(app.state.on_trunk_settled())       # bumps generation, clears both refs

    release_build.set()                             # let the stale (pre-edit) build finish
    t.join(timeout=10)

    assert set(result["geometry"].owners) == {"Room2"}   # never the discarded "Room" result


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


def test_scene_atlas_lightmap_share_one_trunk_read_and_build_each(tmp_path, monkeypatch):
    """Task 4 (spec Testing bullet 1): three requests against an unchanged trunk share ONE
    trunk-read, ONE `build_scene`/native-CSG-solve, and ONE `resolve_actor_sprites` call, across
    all three routes — the redundant-work bug this whole cache exists to fix."""
    _require_ued22()
    import uedcli_native

    from uedcli import trunk as trunk_module
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))

    trunk_calls, geom_calls, sprite_calls = [], [], []
    real_trunk, real_geom, real_sprites = (trunk_module.read_level_with_bodies,
                                           uedcli_native.build_geometry_bspcsg,
                                           serve_app.resolve_actor_sprites)

    def trunk_spy(*a, **k):
        trunk_calls.append(1)
        return real_trunk(*a, **k)

    def geom_spy(*a, **k):
        geom_calls.append(1)
        return real_geom(*a, **k)

    def sprite_spy(*a, **k):
        sprite_calls.append(1)
        return real_sprites(*a, **k)

    monkeypatch.setattr(trunk_module, "read_level_with_bodies", trunk_spy)
    monkeypatch.setattr(uedcli_native, "build_geometry_bspcsg", geom_spy)
    monkeypatch.setattr(serve_app, "resolve_actor_sprites", sprite_spy)

    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert c.get("/api/level/TestLevel/lightmap").status_code == 200

    assert len(trunk_calls) == 1
    assert len(geom_calls) == 1
    assert len(sprite_calls) == 1

    # Task 4 step 5 / spec Testing bullet 2: a real trunk edit + the watcher settling invalidates
    # BOTH slots, and the next request rebuilds fully (fresh trunk-read, fresh solve, fresh sprite
    # resolve) and reflects the edit. `deleted={"Room"}` -- `write_actor_tree`'s trunk write is a
    # DELTA (architecture.md "The core write pattern"): an on-disk actor dir neither rewritten nor
    # named in `deleted` is left alone, so a bare re-`write_level` with only "Room2" would otherwise
    # leave "Room"'s dir in place and this become a two-actor level, not a replacement.
    from uedcli.model import Level

    room2 = cube_room(name="Room2")
    trunk_module.write_level(root / "maps" / "TestLevel",
                             Level(actors={room2.name: room2}, order=[room2.name]),
                             {room2.name: "m"}, deleted={"Room"})
    asyncio.run(app.state.on_trunk_settled())

    r = c.get("/api/level/TestLevel/scene")
    assert r.status_code == 200
    assert {a["name"] for a in r.json()["actors"]} == {"Room2"}

    assert len(trunk_calls) == 2
    assert len(geom_calls) == 2
    assert len(sprite_calls) == 2


def test_concurrent_requests_never_see_a_torn_trunk_or_geometry_slot(tmp_path, monkeypatch):
    """Task 6: fires 7 concurrent `/scene` GETs racing an 8th thread's trunk edit + invalidation.
    No torn read WITHIN a slot: every response's actor set is internally self-consistent — from
    ONE trunk generation, never a mix of pre- and post-edit data. Does NOT assert the two cache
    slots agree with each other across responses (spec: incidental to this spec's scope)."""
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
    c.get("/api/level/TestLevel/scene")           # warm both slots once, deterministically

    barrier = threading.Barrier(8)
    results: list[dict] = []
    errors: list[Exception] = []

    def worker(i: int):
        try:
            barrier.wait()
            if i == 0:
                # The mutation + invalidation happen HERE, right after the barrier releases all 8
                # threads together -- guarantees this races the other 7 threads' GETs, not a
                # vacuous "invalidate before anyone reads" sequence.
                room2 = cube_room(name="Room2")
                # `deleted={"Room"}`: see the generation-guard test above -- an actual replacement,
                # not a two-actor trunk (`write_actor_tree`'s delta-write leaves an unmentioned dir
                # alone unless it's named in `deleted`).
                trunk_module.write_level(maps_dir, Level(actors={room2.name: room2},
                                                         order=[room2.name]), {room2.name: "m"},
                                         deleted={"Room"})
                asyncio.run(app.state.on_trunk_settled())
            else:
                r = c.get("/api/level/TestLevel/scene")
                results.append(r.json())
        except Exception as e:                              # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    for body in results:
        actor_names = {a["name"] for a in body["actors"]}
        assert actor_names in ({"Room"}, {"Room2"})   # whichever generation, never a MIX
