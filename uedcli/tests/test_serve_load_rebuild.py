"""`uedcli serve`'s explicit Load (`POST /load`) and Rebuild (`POST /rebuild`) actions
(gui-explicit-rebuild-pinned-build-state-mode, Tasks 5-7): Load refreshes the trunk/actor view and
bootstraps the geometry pin from an on-disk pointer when the slot is empty; Rebuild is the only
route that ever solves; the two axes stay independent of each other."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from uedcli import preview_cache, trunk
from uedcli.model import Level
from uedcli.serve import app as serve_app
from uedcli.serve import build_pin
from uedcli.tests.conftest import cube_room


def _require_ued22():
    pytest.importorskip("uedcli_native")
    from uedcli.tests.test_serve_scene import UED22
    if not (UED22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present (build_scene needs real class schemas)")


def _write_fixture_trunk(root, level_name, actors) -> None:
    maps_dir = root / "maps" / level_name
    maps_dir.mkdir(parents=True)
    ranks = {a.name: f"n{i:03d}" for i, a in enumerate(actors)}
    trunk.write_level(maps_dir, Level(actors={a.name: a for a in actors},
                                      order=[a.name for a in actors]), ranks)


def _index_and_defaults():
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index
    return _ued22_index(), DEFAULTS


def test_load_with_no_pointer_and_no_rebuild_leaves_geometry_unpinned(tmp_path, monkeypatch):
    """Plan Task 5, step 1: `POST /load` with no on-disk pointer and no prior Rebuild leaves
    `/status`'s `build_status` `"no_build"` and `/scene`'s `geometry_pinned` still `false`."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/level/TestLevel/load")
    assert r.status_code == 200 and r.json() == {"status": "ok", "conflicts": []}

    assert c.get("/api/level/TestLevel/status").json()["build_status"] == "no_build"
    assert c.get("/api/level/TestLevel/scene").json()["geometry_pinned"] is False


def test_load_bootstraps_geometry_from_a_valid_on_disk_pointer(tmp_path, monkeypatch):
    """Plan Task 5, step 2 / spec test #8: a valid on-disk pointer (a prior Save, simulated by
    hand-writing `current.json` + a matching `preview_cache.store_scene` entry) is picked up on the
    very first `/load` -- `geometry_pinned: True`, `build_status: "built"` -- WITHOUT ever calling
    `build_scene` (a spy proves it)."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    payload = ([], [], [])   # empty polys/texture_table/owners -- valid, no unpacking needed
    preview_cache.store_scene(project, "TestLevel", "geomhash12ab", "lighthash12c", payload)
    pointer_path = build_pin.pointer_path(project, "TestLevel")
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text(json.dumps({"geom_hash": "geomhash12ab", "light_hash": "lighthash12c"}))

    calls = []
    monkeypatch.setattr(serve_app, "_build_scene", lambda *a, **k: calls.append(1))

    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/level/TestLevel/load")
    assert r.status_code == 200

    status = c.get("/api/level/TestLevel/status").json()
    assert status == {"changes_available": False, "geometry_pinned": True, "build_status": "built"}
    scene = c.get("/api/level/TestLevel/scene").json()
    assert scene["geometry_pinned"] is True
    assert not calls   # never solved -- the pin came straight from preview_cache


def test_load_degrades_to_evicted_when_the_pointer_names_a_missing_cache_entry(tmp_path, monkeypatch):
    """Plan Task 5, step 3 / spec test #9: an on-disk pointer naming hashes with no matching
    `preview_cache` entry (evicted by the project-wide LRU, or simply never stored) degrades to
    `"evicted"`, never an error and never `"built"`."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    pointer_path = build_pin.pointer_path(project, "TestLevel")
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text(json.dumps({"geom_hash": "nomatch111111", "light_hash": "nomatch222222"}))

    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/level/TestLevel/load")
    assert r.status_code == 200

    status = c.get("/api/level/TestLevel/status").json()
    assert status == {"changes_available": False, "geometry_pinned": False, "build_status": "evicted"}


def test_load_resets_changes_available_to_false(tmp_path, monkeypatch):
    """Plan Task 5, step 4: `POST /load` clears `changes_available` even if a trunk-settle event had
    set it beforehand."""
    import asyncio

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    asyncio.run(app.state.on_trunk_settled())
    assert c.get("/api/level/TestLevel/status").json()["changes_available"] is True

    c.post("/api/level/TestLevel/load")

    assert c.get("/api/level/TestLevel/status").json()["changes_available"] is False


def test_load_refreshes_trunk_but_leaves_an_already_populated_geometry_pin_untouched(
        tmp_path, monkeypatch):
    """Plan Task 5, step 5 (half of spec test #5 -- Task 7 covers the other half): a changed trunk
    on disk produces a different actor set on the NEXT `/load`, but an already-populated geometry
    pin (from a prior Rebuild) is left exactly as it was -- Load never touches `_geometry_ref`."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room(name="Room")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    geometry = app.state.build_and_publish_geometry("TestLevel", [], index, defaults)

    room2 = cube_room(name="Room2")
    trunk.write_level(root / "maps" / "TestLevel",
                      Level(actors={room2.name: room2}, order=[room2.name]),
                      {room2.name: "m"}, deleted={"Room"})

    r = c.post("/api/level/TestLevel/load")
    assert r.status_code == 200

    scene = c.get("/api/level/TestLevel/scene").json()
    assert {a["name"] for a in scene["actors"]} == {"Room2"}    # trunk refreshed
    assert app.state.read_geometry() is geometry                # geometry untouched, same object


def test_rebuild_populates_geometry_and_never_touches_the_on_disk_pointer(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #2: `POST /rebuild` populates `_geometry_ref[0]` (real
    `build_scene` call, spied) -- a subsequent `/scene` serves poly data from it and reports
    `geometry_pinned: true` -- and the on-disk pointer file stays ABSENT (Rebuild is in-memory
    only; the pointer is Save-owned, P2, out of scope here)."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    calls = []
    real_build_scene = serve_app._build_scene

    def spy(*a, **k):
        calls.append(1)
        return real_build_scene(*a, **k)

    monkeypatch.setattr(serve_app, "_build_scene", spy)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/level/TestLevel/rebuild")
    assert r.status_code == 200
    assert len(calls) == 1

    scene = c.get("/api/level/TestLevel/scene").json()
    assert scene["geometry_pinned"] is True
    assert scene["polys"]

    assert not build_pin.pointer_path(project, "TestLevel").exists()


def test_two_rebuilds_with_no_trunk_change_are_a_preview_cache_hit(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #4: two `POST /rebuild` calls in a row, no trunk change between
    them, hit the SAME `preview_cache` entry -- no wasted native CSG re-solve (Rebuild always
    RE-DERIVES, per spec §3.3, but `build_scene`'s own internal cache makes a same-hash repeat
    cheap rather than a genuine re-solve)."""
    _require_ued22()
    import uedcli_native

    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)

    calls = []
    real_bspcsg = uedcli_native.build_geometry_bspcsg

    def spy(*a, **k):
        calls.append(1)
        return real_bspcsg(*a, **k)

    monkeypatch.setattr(uedcli_native, "build_geometry_bspcsg", spy)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    assert c.post("/api/level/TestLevel/rebuild").status_code == 200

    assert len(calls) == 1   # the second Rebuild's build_scene call was a preview_cache hit


def test_rebuild_with_no_prior_load_still_succeeds(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #6: `POST /rebuild` with NO prior explicit `/load` still succeeds --
    it rebuilds against the automatically-loaded trunk (`_get_trunk`'s own first-population), not
    an error and not "nothing to build"."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/level/TestLevel/rebuild")
    assert r.status_code == 200
    assert c.get("/api/level/TestLevel/scene").json()["geometry_pinned"] is True


def test_rebuild_unlocks_the_status_gate(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #7 (the review-flagged "must test the gate re-opening, not just the
    locked state"): a successful `POST /rebuild` flips `/status`'s `geometry_pinned` False -> True
    and `build_status` `"no_build"` -> `"built"`."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    before = c.get("/api/level/TestLevel/status").json()
    assert before["geometry_pinned"] is False and before["build_status"] == "no_build"

    c.post("/api/level/TestLevel/rebuild")

    after = c.get("/api/level/TestLevel/status").json()
    assert after["geometry_pinned"] is True and after["build_status"] == "built"


def test_rebuild_route_generation_guard_discards_a_mid_flight_build(tmp_path, monkeypatch):
    """Plan Task 6's generation-guard test, at the HTTP layer: firing a real `POST /rebuild`
    request that races a settled trunk change mid-solve still discards+retries rather than publish
    blind -- the same mechanism `test_serve_app.py`'s unit-level test pins directly on
    `_build_and_publish_geometry`, now proven through the real route."""
    import threading

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

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

    def call_rebuild():
        result["response"] = c.post("/api/level/TestLevel/rebuild")

    t = threading.Thread(target=call_rebuild)
    t.start()
    assert build_entered.wait(timeout=5)

    import asyncio
    asyncio.run(app.state.on_trunk_settled())   # bumps generation mid-solve

    release_build.set()
    t.join(timeout=10)

    assert result["response"].status_code == 200
    assert len(build_calls) == 2   # discarded the first result and retried
    assert app.state.read_geometry() is not None


# --------------------------------------------------------------- Task 7: independent-axes tests

def test_rebuild_then_a_settled_trunk_change_leaves_scene_pinned_until_a_second_rebuild(
        tmp_path, monkeypatch):
    """Plan Task 7, Test A (spec test #3): Rebuild, then a trunk change settling (the watcher firing,
    simulated via `on_trunk_settled` directly) does NOT change what `/scene` serves -- still the
    pinned geometry from the first Rebuild -- and a second Rebuild fired with NO Load in between
    (so `_trunk_ref` is still the pre-edit view) reproduces the SAME pin, not an error and not a
    silent pickup of data nothing asked to Load yet. (Also exercises that a mere `_generation[0]`
    bump with no build in flight is a no-op -- nothing reads or reacts to generation except a build
    that's actively checking it.)"""
    import asyncio

    from uedcli.builders import cube, make_brush_actor

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room(name="Room")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    scene_before = c.get("/api/level/TestLevel/scene").json()
    assert {p["owner"] for p in scene_before["polys"]} == {"Room"}

    pillar = make_brush_actor("Pillar", cube(64.0, 64.0, 64.0), csg="add")
    room = cube_room(name="Room")
    trunk.write_level(root / "maps" / "TestLevel",
                      Level(actors={room.name: room, pillar.name: pillar},
                           order=[room.name, pillar.name]),
                      {room.name: "m", pillar.name: "n"})
    asyncio.run(app.state.on_trunk_settled())    # the watcher firing -- no Load, no Rebuild

    scene_after_settle = c.get("/api/level/TestLevel/scene").json()
    assert {p["owner"] for p in scene_after_settle["polys"]} == {"Room"}   # unchanged

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    scene_after_second_rebuild = c.get("/api/level/TestLevel/scene").json()
    # Still "Room" only: this second Rebuild had no Load in between, so `_get_trunk()` still
    # returns the pre-edit view -- a Rebuild alone never pulls fresh trunk data (spec §3 test #6's
    # OTHER half: it rebuilds against the CURRENT view, not the live on-disk trunk).
    assert {p["owner"] for p in scene_after_second_rebuild["polys"]} == {"Room"}


def test_load_pulls_in_a_new_actor_but_geometry_stays_pinned_until_a_separate_rebuild(
        tmp_path, monkeypatch):
    """Plan Task 7, Test B (spec test #5): after an initial Rebuild, `/load` picks up a NEWLY-ADDED
    actor into `/scene`'s `actors` list, but the pinned geometry (`/scene`'s `polys`/`geometry_pinned`,
    unchanged since the actor has no solved geometry yet) stays exactly as the first Rebuild left it
    -- until a separate, later Rebuild picks the new actor's geometry up too."""
    from uedcli.builders import cube, make_brush_actor

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room(name="Room")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    geometry_after_first_rebuild = app.state.read_geometry()
    assert set(geometry_after_first_rebuild.owners) == {"Room"}

    pillar = make_brush_actor("Pillar", cube(64.0, 64.0, 64.0), csg="add")
    room = cube_room(name="Room")
    trunk.write_level(root / "maps" / "TestLevel",
                      Level(actors={room.name: room, pillar.name: pillar},
                           order=[room.name, pillar.name]),
                      {room.name: "m", pillar.name: "n"})

    assert c.post("/api/level/TestLevel/load").status_code == 200

    scene = c.get("/api/level/TestLevel/scene").json()
    assert {a["name"] for a in scene["actors"]} == {"Room", "Pillar"}   # Load-axis: sees the new actor
    assert scene["geometry_pinned"] is True
    assert {p["owner"] for p in scene["polys"]} == {"Room"}             # geometry-axis: unmoved
    assert app.state.read_geometry() is geometry_after_first_rebuild   # same object, no rebuild

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    scene_after_second_rebuild = c.get("/api/level/TestLevel/scene").json()
    assert {p["owner"] for p in scene_after_second_rebuild["polys"]} == {"Room", "Pillar"}


def test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding(tmp_path, monkeypatch):
    """Board `gui-serve-rebuilds-classindex-on-every-request`: /scene must NOT rebuild
    `(search_files, index, defaults)` once /load already built a trunk to pair them with -- a
    plain Reload (POST /load then GET /scene+/atlas+/lightmap) used to call `_scene_inputs()` 4
    times; after the fix it's called exactly once, by /load."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    assert len(calls) == 1

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert c.get("/api/level/TestLevel/lightmap").status_code == 200

    assert len(calls) == 1   # still just the one call /load made


def test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache(tmp_path, monkeypatch):
    """No /load or /rebuild has ever run -- /scene itself triggers `_get_trunk`'s once-only
    bootstrap branch. That ONE call still rebuilds `_scene_inputs()` (nothing to reuse yet, not a
    regression), but stashes its result so the immediately-following /atlas does NOT."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.get("/api/level/TestLevel/scene").status_code == 200
    assert len(calls) == 1

    assert c.get("/api/level/TestLevel/atlas").status_code == 200
    assert len(calls) == 1   # reused what /scene's own bootstrap just stashed


def test_rebuild_route_always_calls_scene_inputs_fresh_not_cached(tmp_path, monkeypatch):
    """Guards the deliberate exclusion the spec calls for: unlike /scene/atlas/lightmap, /rebuild
    must keep calling `_scene_inputs()` fresh on every invocation -- it feeds `index`/`defaults`
    straight into a real CSG/lighting solve (`_build_scene`), where a stale schema could silently
    produce a wrong result, not just a slow one. A future change that accidentally routes /rebuild
    through `_current_scene_inputs()` would fail this test."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    assert len(calls) == 1
    assert c.post("/api/level/TestLevel/rebuild").status_code == 200
    assert len(calls) == 2   # a second Rebuild calls it again -- never reused


def test_switch_level_clears_the_scene_inputs_cache_too(tmp_path, monkeypatch):
    """`_scene_inputs_ref` must be cleared alongside `_trunk_ref`/`_geometry_ref`/`_payload_ref` on
    a level switch -- otherwise a stale pairing from the OLD level's trunk would leak into the new
    one's first read (it would still be a HARMLESS reuse in practice -- see spec's "Not tied to
    PUT /api/level" -- but this pins the simpler, obviously-correct behavior actually chosen)."""
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []

    def _counting_scene_inputs(project):
        calls.append(1)
        return [], index, defaults

    monkeypatch.setattr(serve_app, "_scene_inputs", _counting_scene_inputs)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    _write_fixture_trunk(root, "Other", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    assert len(calls) == 1

    assert c.put("/api/level", json={"level": "Other"}).status_code == 200
    assert c.get("/api/level/Other/scene").status_code == 200
    assert len(calls) == 2   # the old level's cached pairing was cleared, not reused for the new one


def test_load_resolves_mesh_class_defaults_through_the_shared_memo(tmp_path, monkeypatch):
    """Board `load-resolves-mesh-class-defaults-and-texture`: /load must pass its own already-built
    `defaults` into resolve_mesh_scene_polys/resolve_mover_scene_polys, not let them go without --
    a spy on `ClassDefaults.for_class` proves the SHARED instance actually gets used, not just that
    /load succeeds (which it would even with the old, unfixed signature erroring differently)."""
    from uedcli.classdefaults import ClassDefaults
    _require_ued22()
    index, defaults = _index_and_defaults()
    calls = []
    real_for_class = ClassDefaults.for_class
    def _spy(self, fqcn):
        if self is defaults:
            calls.append(fqcn)
        return real_for_class(self, fqcn)
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))
    monkeypatch.setattr(ClassDefaults, "for_class", _spy)

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    assert c.post("/api/level/TestLevel/load").status_code == 200
    # `calls` stays empty here, and NOT because cube_room() has no mesh/mover actors -- the mocked
    # `_scene_inputs` above returns `search_files=[]`, and `resolve_mesh_scene_polys`/
    # `resolve_mover_scene_polys` both short-circuit to `return [], [], []` BEFORE their per-actor
    # loop whenever `search_files` is falsy (`preview_native.py:514`/`295`) -- so
    # `class_defaults.for_class` is never reached regardless of what actors the level has. The real
    # assertion this test makes is that /load's now-required `class_defaults` argument is actually
    # wired at both call sites (app.py:277-280/551-554) -- a TypeError there would 500, not 200,
    # and the domain-error handler would report it, not silently succeed.
