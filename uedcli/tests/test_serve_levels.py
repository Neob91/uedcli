"""`GET /api/levels` (quad-layout Part 7, Task 24): reuses level_sources.list_levels, flags the
currently-served level `active`."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve.app import create_app
from uedcli.serve.levels import levels_payload


def _write_fixture_trunk(root, level_name) -> None:
    from uedcli import trunk as trunk_module
    from uedcli.model import Level
    from uedcli.tests.conftest import cube_room

    room = cube_room()
    maps_dir = root / "maps" / level_name
    maps_dir.mkdir(parents=True)
    trunk_module.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]), {room.name: "m"})


def test_levels_payload_flags_the_current_level(tmp_path):
    for name in ("Alpha", "Beta", "Gamma"):
        _write_fixture_trunk(tmp_path, name)

    payload = levels_payload(tmp_path / "maps", "Beta")

    assert payload["current"] == "Beta"
    assert payload["levels"] == [
        {"name": "Alpha", "active": False},
        {"name": "Beta", "active": True},
        {"name": "Gamma", "active": False},
    ]


def test_levels_route_returns_every_project_level(tmp_path):
    root = tmp_path / "proj"
    for name in ("TestLevel", "OtherLevel"):
        _write_fixture_trunk(root, name)
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.get("/api/levels")

    assert r.status_code == 200
    body = r.json()
    assert body["current"] == "TestLevel"
    names_active = {entry["name"]: entry["active"] for entry in body["levels"]}
    assert names_active == {"TestLevel": True, "OtherLevel": False}
