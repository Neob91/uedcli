"""HTTP routes for GUI actor-edit staging (plan Task 3): thin adapters wrapping `serve/edits.py`'s
`stage_locations`/`discard_staged`/`save_staged` (Task 2) and `serve/snapshots.py`'s `StagingStore`
(Task 1). The Decimal/JSON boundary lives ONLY in these routes -- `edits.py`/`snapshots.py` never
see a `float`; every test here that inspects a location asserts it comes back as JSON floats.

Task 13 (persistent-GUI-editing-sessions plan): `/stage`, `/discard`, `/save`, `/staged`, `/load`
move from `/api/level/{level_name}/...` to `/api/session/{id}/...`; the four writes (`stage`,
`discard`, `save`, `load`) now require a valid `X-Claim-Token` header. Every test below is
re-pointed at the session-scoped paths -- the underlying stage/discard/save/load business logic
this file exercises is unchanged by the re-route, so nothing here was dropped, only re-addressed."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli import trunk
from uedcli.model import Level
from uedcli.serve import sessions
from uedcli.serve.app import create_app
from uedcli.tests.conftest import cube_room


def _write_fixture_trunk(tmp_path: Path, actors=None) -> tuple:
    """A tiny project (`<tmp>/proj/maps/TestLevel/`) holding one brush actor by default -- small
    enough to stage/save with no CSG solve (this route layer never touches geometry)."""
    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    if actors is None:
        actors = [cube_room("Brush1")]
    level = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    trunk.write_level(maps_dir, level, {a.name: f"m{i}" for i, a in enumerate(actors)})
    project = SimpleNamespace(root=str(root), maps=None)
    return project, "TestLevel"


def _client(tmp_path, actors=None) -> tuple[TestClient, str, str]:
    """Returns `(client, session_id, claim_token)` -- a session is created for the fixture level
    via `sessions.create_session` directly (this plan's own "tests set up state via lower-level
    module functions" rule), and its claim token minted, since every write route this file exercises
    (`stage`/`discard`/`save`/`load`) now requires one (Task 13)."""
    project, level_name = _write_fixture_trunk(tmp_path, actors)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    return c, sess.id, token


def test_stage_save_roundtrip_and_bad_actor_name_is_structured_error(tmp_path):
    c, sess_id, token = _client(tmp_path)
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess_id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers=h)
    assert r.status_code == 200 and r.json()["staged"] == ["Brush1"]

    r = c.get(f"/api/session/{sess_id}/staged")
    assert "Brush1" in r.json()

    r = c.post(f"/api/session/{sess_id}/save", json={}, headers=h)
    assert r.json()["applied"] == ["Brush1"] and r.json()["conflicts"] == []

    r = c.get(f"/api/session/{sess_id}/staged")
    assert r.json() == {}

    r = c.post(f"/api/session/{sess_id}/stage", json={"actors": {"NoSuchActor999": [0, 0, 0]}},
              headers=h)
    assert r.status_code // 100 == 4
    assert "NoSuchActor999" in r.json()["error"]


def test_stage_route_parses_decimal_strictly_and_staged_route_serializes_as_floats(tmp_path):
    """`0.1` as a binary float is `0.1000000000000000055511151231257827021181583404541015625` --
    routing it through `Decimal(str(v))` (never `Decimal(v)` directly) is what this test pins:
    a naive `Decimal(v)` would import that binary-float noise, and `read_staged` would echo it back
    verbatim in the response's `staged_location`/`baseline_location`."""
    c, sess_id, token = _client(tmp_path)

    r = c.post(f"/api/session/{sess_id}/stage", json={"actors": {"Brush1": [0.1, 0.2, 0.3]}},
              headers={"X-Claim-Token": token})
    assert r.status_code == 200

    r = c.get(f"/api/session/{sess_id}/staged")
    body = r.json()
    assert body["Brush1"]["staged_location"] == [0.1, 0.2, 0.3]
    assert body["Brush1"]["baseline_location"] == [0.0, 0.0, 0.0]


def test_discard_route_clears_staged_without_touching_trunk(tmp_path):
    c, sess_id, token = _client(tmp_path)
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess_id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers=h)
    assert r.status_code == 200

    r = c.post(f"/api/session/{sess_id}/discard", headers=h)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    r = c.get(f"/api/session/{sess_id}/staged")
    assert r.json() == {}


def test_discard_route_with_actors_subset_clears_only_those(tmp_path):
    c, sess_id, token = _client(tmp_path, actors=[cube_room("Brush1"), cube_room("Brush2")])
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess_id}/stage", json={
        "actors": {"Brush1": [10.0, 0.0, 0.0], "Brush2": [20.0, 0.0, 0.0]},
    }, headers=h)
    assert r.status_code == 200

    r = c.post(f"/api/session/{sess_id}/discard", json={"actors": ["Brush1"]}, headers=h)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    r = c.get(f"/api/session/{sess_id}/staged")
    assert r.json().keys() == {"Brush2"}


def test_staged_route_is_empty_when_nothing_staged(tmp_path):
    c, sess_id, _token = _client(tmp_path)
    r = c.get(f"/api/session/{sess_id}/staged")
    assert r.status_code == 200
    assert r.json() == {}


def test_save_route_reports_a_conflict_with_json_float_locations(tmp_path):
    """Stages a move, then applies a conflicting external edit straight through the model-side
    write path (bypassing staging), so `save` must report a conflict (not apply it) -- and the
    conflict's two locations must come back as JSON floats, never a raw `Decimal`."""
    from decimal import Decimal

    from uedcli.cli.level_sources import TrunkLevelSource
    from uedcli import config as config_module

    project, level_name = _write_fixture_trunk(tmp_path)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess.id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers=h)
    assert r.status_code == 200

    trunk_dir = Path(config_module.project_maps_dir(project)) / level_name
    src = TrunkLevelSource(trunk_dir)
    level = src.load()
    level.actors["Brush1"].location = (Decimal("999"), Decimal("0"), Decimal("0"))
    src.save(verb="test-external-edit", args={}, level=level, touched=["Brush1"])

    r = c.post(f"/api/session/{sess.id}/save", json={}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == []
    assert body["conflicts"] == [{
        "name": "Brush1",
        "staged_location": [10.0, 0.0, 0.0],
        "trunk_location": [999.0, 0.0, 0.0],
    }]

    r = c.post(f"/api/session/{sess.id}/save",
               json={"resolutions": {"Brush1": "staged"}}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == ["Brush1"]
    assert body["conflicts"] == []


def test_load_route_reports_conflict_but_still_refreshes_and_accept_load_clears_stage(
        tmp_path, monkeypatch):
    """Symmetric with `save`'s conflict check, in the reverse direction: Load must never block or
    fail on a conflict -- it only reports one. The route's response gains a `conflicts` field,
    additive to the pre-existing `{"status": "ok"}` shape.

    `_scene_inputs` is stubbed to `([], None, None)` -- same as `test_serve_load_rebuild.py`'s own
    pattern for a route test with no real games config, except here an empty `search_files` alone
    is enough (`resolve_actor_sprites`/`resolve_mesh_scene_polys`/`resolve_mover_scene_polys` all
    degrade to empty results without touching `index`/`defaults` at all), since this test's fixture
    project (a bare `SimpleNamespace`) has no `.paths` for the real `_scene_inputs` to read."""
    from decimal import Decimal

    from uedcli.cli.level_sources import TrunkLevelSource
    from uedcli import config as config_module
    from uedcli.serve import app as serve_app

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], None, None))

    project, level_name = _write_fixture_trunk(tmp_path)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess.id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers=h)
    assert r.status_code == 200

    trunk_dir = Path(config_module.project_maps_dir(project)) / level_name
    src = TrunkLevelSource(trunk_dir)
    level = src.load()
    level.actors["Brush1"].location = (Decimal("999"), Decimal("0"), Decimal("0"))
    src.save(verb="test-external-edit", args={}, level=level, touched=["Brush1"])

    r = c.post(f"/api/session/{sess.id}/load", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["conflicts"] == [{
        "name": "Brush1",
        "staged_location": [10.0, 0.0, 0.0],
        "trunk_location": [999.0, 0.0, 0.0],
    }]

    r = c.get(f"/api/session/{sess.id}/staged")
    assert "Brush1" in r.json()   # untouched -- kept staged, the default "keep staged" behavior

    r = c.post(f"/api/session/{sess.id}/load",
               json={"resolutions": {"Brush1": "accept-load"}}, headers=h)
    assert r.status_code == 200
    assert r.json()["conflicts"] == []

    r = c.get(f"/api/session/{sess.id}/staged")
    assert r.json() == {}   # accept-load cleared the stage


def test_load_route_completes_and_clears_stage_when_a_staged_actor_was_deleted_externally(
        tmp_path, monkeypatch):
    """The HTTP-level contract for the deleted-actor edge case: `POST /load` must return 200 with a
    COMPLETED refresh (never a 4xx/5xx, never skip the trunk swap), even though the staged actor no
    longer exists in the trunk at all. A deleted actor is not a reportable conflict (no real
    `trunk_location` to show) -- its stale staged entry is silently dropped instead."""
    from decimal import Decimal

    from uedcli.cli.level_sources import TrunkLevelSource
    from uedcli import config as config_module
    from uedcli.serve import app as serve_app

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], None, None))

    project, level_name = _write_fixture_trunk(tmp_path)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    h = {"X-Claim-Token": token}

    r = c.post(f"/api/session/{sess.id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers=h)
    assert r.status_code == 200

    trunk_dir = Path(config_module.project_maps_dir(project)) / level_name
    src = TrunkLevelSource(trunk_dir)
    level = src.load()
    del level.actors["Brush1"]
    level.order.remove("Brush1")
    src.save(verb="test-external-edit", args={}, level=level, touched=[])

    r = c.post(f"/api/session/{sess.id}/load", headers=h)
    assert r.status_code == 200                # never blocks/fails, not a 4xx/5xx
    body = r.json()
    assert body["status"] == "ok"
    assert body["conflicts"] == []              # deleted actor isn't a reportable conflict

    r = c.get(f"/api/session/{sess.id}/staged")
    assert r.json() == {}                       # the stale staged entry is gone

    # the refresh genuinely completed rather than bailing early (the actual pre-fix bug: a raised
    # CommandError short-circuited BEFORE `_scene_inputs_ref[0]`/`_trunk_ref[0]` ever got written,
    # which surfaced as a 422, not this 200) -- `/status` staying servable with a clean, non-error
    # response is only reachable once that write sequence has run. Task 14: `/status` is
    # session-scoped now.
    r = c.get(f"/api/session/{sess.id}/status")
    assert r.status_code == 200
    assert r.json()["changes_available"] is False


def test_stage_dropped_when_session_deleted_between_claim_check_and_write(tmp_path, monkeypatch):
    """Fix round 1 (Task 13, Finding 1) -- the reviewer's concrete repro. A DELETE that completes
    in the narrow window between this request's claim-token check passing and its own write
    (simulated here, mirroring `test_rebuild_dropped_when_session_deleted_mid_solve`'s shape in
    `test_serve_app.py`, by making the patched `ClaimRegistry.check` perform the real
    `sessions.delete_session` + `_claims.forget` as a side effect right after it returns True) must
    not resurrect `sessions/<sid>/` with an orphaned `staged.json` -- `stage_locations` ->
    `atomic_write_json` does an unconditional `mkdir(parents=True, exist_ok=True)`, which is exactly
    what would otherwise recreate the just-deleted directory."""
    project, level_name = _write_fixture_trunk(tmp_path)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    session_dir = Path(app.state.sessions_root) / sess.id
    assert session_dir.exists()

    real_check = app.state.claims.check

    def check_then_delete(sid, tok):
        result = real_check(sid, tok)
        if sid == sess.id:
            sessions.delete_session(app.state.sessions_root, sid)
            app.state.claims.forget(sid)
        return result

    monkeypatch.setattr(app.state.claims, "check", check_then_delete)

    r = c.post(f"/api/session/{sess.id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers={"X-Claim-Token": token})

    assert r.status_code == 409
    assert "error" in r.json()
    assert not session_dir.exists()   # not resurrected


def test_discard_dropped_when_session_deleted_between_claim_check_and_write(tmp_path, monkeypatch):
    """Same fix, same repro shape, for `discard` -- the least-analyzed of the four per the review
    (the reviewer confirmed `save`/`load` are only INCIDENTALLY safe today for unrelated reasons,
    and didn't specifically analyze `discard` at all). `discard_staged` -> `StagingStore.clear_actor`
    also goes through `atomic_write_json`'s unconditional `mkdir`, so it is exactly as exposed as
    `stage` was."""
    project, level_name = _write_fixture_trunk(tmp_path)
    app = create_app(project, level_name)
    c = TestClient(app, raise_server_exceptions=False)
    sess = sessions.create_session(app.state.sessions_root, level_name)
    token = app.state.claims.mint(sess.id)
    session_dir = Path(app.state.sessions_root) / sess.id

    # Stage something first, then delete the session (matching the real flow), leaving a
    # `staged.json` on disk that a resurrected `discard` would otherwise clear/rewrite.
    r = c.post(f"/api/session/{sess.id}/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}},
              headers={"X-Claim-Token": token})
    assert r.status_code == 200
    assert session_dir.exists()

    real_check = app.state.claims.check

    def check_then_delete(sid, tok):
        result = real_check(sid, tok)
        if sid == sess.id:
            sessions.delete_session(app.state.sessions_root, sid)
            app.state.claims.forget(sid)
        return result

    monkeypatch.setattr(app.state.claims, "check", check_then_delete)

    r = c.post(f"/api/session/{sess.id}/discard", headers={"X-Claim-Token": token})

    assert r.status_code == 409
    assert "error" in r.json()
    assert not session_dir.exists()   # not resurrected


def test_old_per_level_edit_routes_are_gone(tmp_path):
    """Task 13: the eight old `/api/level/{level_name}/...` routes this file used to drive
    (`stage`/`discard`/`save`/`staged`/`load` among them) are deleted outright -- no back-compat
    shim."""
    c, sess_id, token = _client(tmp_path)
    h = {"X-Claim-Token": token}

    assert c.post("/api/level/TestLevel/stage", json={"actors": {}}, headers=h).status_code == 404
    assert c.post("/api/level/TestLevel/discard", headers=h).status_code == 404
    assert c.post("/api/level/TestLevel/save", json={}, headers=h).status_code == 404
    assert c.get("/api/level/TestLevel/staged").status_code == 404
    assert c.post("/api/level/TestLevel/load", headers=h).status_code == 404
