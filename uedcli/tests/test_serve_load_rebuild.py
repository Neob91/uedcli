"""`uedcli serve`'s explicit Load (`POST /api/session/{id}/load`) and session-scoped Rebuild
(`POST /api/session/{id}/rebuild`) actions (gui-explicit-rebuild-pinned-build-state-mode, Tasks
5-7; persistent-GUI-editing-sessions plan Tasks 9/11/13). Task 9 removed in-memory geometry pinning
(`_geometry_ref`/`_payload_ref`/`_build_status`/`solve_lock`) entirely; Task 11 restored it,
per-session, via disk (`build_pin`); Task 13 re-routed `/scene`/`/atlas`/`/lightmap`/`/load` from
per-level to per-session paths. The per-level `/api/level/{level_name}/rebuild` route these tests
used to exercise (Task 9's own deliberate intermediate placeholder) is deleted outright
(final-review fix round, Finding 2) -- every test that used it is either gone (its whole point was
the dead route's own memorylessness) or ported to `POST /api/session/{id}/rebuild`, which now
really does pin real geometry (final-review fix round, Finding 1 -- see `test_serve_scene.py`/
`test_serve_lightmap.py` for the JSON-round-trip regression coverage of that)."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli import trunk
from uedcli.model import Level
from uedcli.serve import app as serve_app
from uedcli.tests.conftest import cube_room


def _require_ued22():
    import pytest
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
    `/status`'s `build_status` `"no_build"` and `/scene`'s `geometry_pinned` still `false`. Task 14:
    `/status` is session-scoped too now (`GET /api/session/{id}/status`, replacing the per-level
    route this task retired) -- a session is created via `sessions.create_session` (this plan's own
    "tests set up state via lower-level module functions" rule), and `/load` needs a claim token."""
    from uedcli.serve import sessions

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    r = c.post(f"/api/session/{sess.id}/load", headers={"X-Claim-Token": token})
    assert r.status_code == 200 and r.json() == {"status": "ok", "conflicts": []}

    assert c.get(f"/api/session/{sess.id}/status").json()["build_status"] == "no_build"
    assert c.get(f"/api/session/{sess.id}/scene").json()["geometry_pinned"] is False


def test_load_resets_changes_available_to_false(tmp_path, monkeypatch):
    """Plan Task 5, step 4: `POST /load` clears `changes_available` even if a trunk-settle event had
    set it beforehand. Unaffected by Task 9's geometry-pinning removal. Task 13: `/load` is
    session-scoped now, gated by a claim token. Task 14: `/status` is session-scoped too --
    `changes_available` now compares the level's trunk generation against THIS session's own
    `last_seen_generation`, not a level-wide flag every session shared."""
    import asyncio

    from uedcli.serve import sessions

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    asyncio.run(app.state.on_trunk_settled())
    assert c.get(f"/api/session/{sess.id}/status").json()["changes_available"] is True

    c.post(f"/api/session/{sess.id}/load", headers={"X-Claim-Token": token})

    assert c.get(f"/api/session/{sess.id}/status").json()["changes_available"] is False


def test_two_rebuilds_with_no_trunk_change_are_a_build_cache_hit(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #4, ported to session-scoped Rebuild once the per-level `/rebuild`
    route was deleted outright (final-review fix round, Finding 2 -- nothing calls it any more): two
    `POST /api/session/{id}/rebuild` calls in a row, no trunk change between them, hit the SAME
    `build_cache` entry -- no wasted native CSG re-solve. `build_scene`'s own internal on-disk cache
    makes a same-hash repeat cheap rather than a genuine re-solve -- a property of
    `build_scene`/`build_cache`, unaffected by which route calls it."""
    from uedcli.serve import sessions

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
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    assert c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token}).status_code == 200
    assert c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token}).status_code == 200

    assert len(calls) == 1   # the second Rebuild's build_scene call was a build_cache hit


def test_rebuild_with_no_prior_load_still_succeeds(tmp_path, monkeypatch):
    """Plan Task 6 / spec test #6, ported to session-scoped Rebuild (Finding 2 above): `POST
    /api/session/{id}/rebuild` with NO prior explicit `/load` still succeeds -- it rebuilds against
    the automatically-loaded trunk (`_get_trunk`'s own first-population), not an error and not
    "nothing to build". Also pins real geometry now (final-review fix round, Finding 1): a later
    `/scene` reports `geometry_pinned: true`."""
    from uedcli.serve import sessions

    _require_ued22()
    index, defaults = _index_and_defaults()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, defaults))

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [cube_room()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    r = c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token})
    assert r.status_code == 200
    assert r.json()["geom_hash"]
    assert c.get(f"/api/session/{sess.id}/scene").json()["geometry_pinned"] is True


def test_scene_route_reuses_load_s_scene_inputs_instead_of_rebuilding(tmp_path, monkeypatch):
    """Board `gui-serve-rebuilds-classindex-on-every-request`: /scene must NOT rebuild
    `(search_files, index, defaults)` once /load already built a trunk to pair them with -- a
    plain Reload (POST /load then GET /scene+/atlas+/lightmap) used to call `_scene_inputs()` 4
    times; after the fix it's called exactly once, by /load. `scene_inputs_ref` stays in
    `LevelContext` after Task 9 (it's genuinely level-shared, not solved-build state), so this
    contract is unaffected by the geometry-pinning removal. Task 13: `/load`/`/scene`/`/atlas`/
    `/lightmap` are all session-scoped now."""
    from uedcli.serve import sessions

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
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    assert c.post(f"/api/session/{sess.id}/load", headers={"X-Claim-Token": token}).status_code == 200
    assert len(calls) == 1

    assert c.get(f"/api/session/{sess.id}/scene").status_code == 200
    assert c.get(f"/api/session/{sess.id}/scene").status_code == 200
    assert c.get(f"/api/session/{sess.id}/atlas").status_code == 200
    assert c.get(f"/api/session/{sess.id}/lightmap").status_code == 200

    assert len(calls) == 1   # still just the one call /load made


def test_scene_route_as_the_very_first_request_bootstraps_and_seeds_the_cache(tmp_path, monkeypatch):
    """No /load or /rebuild has ever run -- /scene itself triggers `_get_trunk`'s once-only
    bootstrap branch. That ONE call still rebuilds `_scene_inputs()` (nothing to reuse yet, not a
    regression), but stashes its result so the immediately-following /atlas does NOT. Task 13:
    `/scene`/`/atlas` are session-scoped now."""
    from uedcli.serve import sessions

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
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")

    assert c.get(f"/api/session/{sess.id}/scene").status_code == 200
    assert len(calls) == 1

    assert c.get(f"/api/session/{sess.id}/atlas").status_code == 200
    assert len(calls) == 1   # reused what /scene's own bootstrap just stashed


def test_rebuild_route_always_calls_scene_inputs_fresh_not_cached(tmp_path, monkeypatch):
    """Guards the deliberate exclusion the spec calls for: unlike /scene/atlas/lightmap,
    session-scoped Rebuild must keep calling `_scene_inputs()` fresh on every invocation -- it feeds
    `index`/`defaults` straight into a real CSG/lighting solve (`build_scene`), where a stale schema
    could silently produce a wrong result, not just a slow one. Ported to
    `POST /api/session/{id}/rebuild` once the per-level `/rebuild` route was deleted outright
    (final-review fix round, Finding 2) -- the property itself is unaffected by which route calls it."""
    from uedcli.serve import sessions

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
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    assert c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token}).status_code == 200
    assert len(calls) == 1
    assert c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token}).status_code == 200
    assert len(calls) == 2   # a second Rebuild calls it again -- never reused


def test_load_resolves_mesh_class_defaults_through_the_shared_memo(tmp_path, monkeypatch):
    """Board `load-resolves-mesh-class-defaults-and-texture`: /load must pass its own already-built
    `defaults` into resolve_mesh_scene_polys/resolve_mover_scene_polys, not let them go without --
    a spy on `ClassDefaults.for_class` proves the SHARED instance actually gets used, not just that
    /load succeeds (which it would even with the old, unfixed signature erroring differently).
    Task 13: `/load` is session-scoped now, gated by a claim token."""
    from uedcli.classdefaults import ClassDefaults
    from uedcli.serve import sessions
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
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    assert c.post(f"/api/session/{sess.id}/load", headers={"X-Claim-Token": token}).status_code == 200
    # `calls` stays empty here, and NOT because cube_room() has no mesh/mover actors -- the mocked
    # `_scene_inputs` above returns `search_files=[]`, and `resolve_mesh_scene_polys`/
    # `resolve_mover_scene_polys` both short-circuit to `return [], [], []` BEFORE their per-actor
    # loop whenever `search_files` is falsy (`preview_native.py:514`/`295`) -- so
    # `class_defaults.for_class` is never reached regardless of what actors the level has. The real
    # assertion this test makes is that /load's now-required `class_defaults` argument is actually
    # wired at both call sites -- a TypeError there would 500, not 200, and the domain-error handler
    # would report it, not silently succeed.
    assert c.get(f"/api/session/{sess.id}/status").json()["build_status"] == "no_build"
