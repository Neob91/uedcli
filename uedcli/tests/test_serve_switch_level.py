"""`PUT /api/level` (quad-layout Part 7, Task 25): switches the level THIS SAME running app serves,
in-process -- no restart, no page-reload trick. Drives a REAL `TrunkWatcher` end to end (not
mocked): after a switch, a real filesystem change under the NEW level's dir pushes a WS
`changes_available` message naming the NEW level. This also pins the route's `async def`
requirement -- `TrunkWatcher.start()`/`stop()` need the request's own running event loop, which a
sync route (running in Starlette's threadpool) doesn't have; a regression to `sync def` here would
raise `RuntimeError` the moment the route called `new_watcher.start()`, failing loudly."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve.app import create_app


def _write_fixture_trunk(root, level_name) -> None:
    from uedcli import trunk as trunk_module
    from uedcli.model import Level
    from uedcli.tests.conftest import cube_room

    room = cube_room()
    maps_dir = root / "maps" / level_name
    maps_dir.mkdir(parents=True)
    trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]), {room.name: "m"})


def test_switch_level_updates_health_and_a_real_watcher_fires_for_the_new_level(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel")
    other_dir = root / "maps" / "Other"
    _write_fixture_trunk(root, "Other")
    project = SimpleNamespace(root=str(root), maps=None)

    app = create_app(project, "TestLevel")
    with TestClient(app) as client:                      # runs startup/shutdown -> starts the watcher
        r = client.put("/api/level", json={"level": "Other"})
        assert r.status_code == 200
        assert r.json() == {"level": "Other"}
        assert client.get("/api/health").json()["level"] == "Other"

        with client.websocket_connect("/ws") as ws:
            (other_dir / "seed.txt").write_text("y")      # a real trunk-dir change, NEW level
            msg = ws.receive_json(mode="text")
            assert msg == {"type": "changes_available", "level": "Other"}


def test_switch_level_stops_the_old_watcher_and_binds_a_new_one_to_the_new_dir(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel")
    _write_fixture_trunk(root, "Other")
    project = SimpleNamespace(root=str(root), maps=None)

    app = create_app(project, "TestLevel")
    with TestClient(app) as client:
        old_watcher = app.state.watcher[0]
        assert old_watcher._watch_task is not None         # running (lifespan startup started it)

        r = client.put("/api/level", json={"level": "Other"})
        assert r.status_code == 200

        assert old_watcher._watch_task is None              # PUT /api/level actually stopped it
        new_watcher = app.state.watcher[0]
        assert new_watcher is not old_watcher
        assert new_watcher.level_dir == root / "maps" / "Other"
        assert new_watcher._watch_task is not None          # the new one is running


def test_switch_level_rejects_a_nonexistent_level_and_leaves_the_served_level_unchanged(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel")
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app, raise_server_exceptions=False)

    r = c.put("/api/level", json={"level": "NoSuchLevel"})

    assert r.status_code == 422
    assert "not found" in r.json()["error"]
    assert c.get("/api/health").json()["level"] == "TestLevel"
