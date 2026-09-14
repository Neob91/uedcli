"""`uedcli serve`'s scene endpoint assembly (plan Task 2): trunk → `ScenePayload`, reusing
`preview_native.build_scene` + `preview_cache` for the solve and joining actor metadata fresh.
Mirrors `test_preview_native.py`'s fixture pattern: a `StubClassIndex`, a `ClassDefaults` over the
git-tracked `uned/UED22/*.u`, skipped when that corpus is absent."""
from __future__ import annotations

import glob
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import trunk
from uedcli.classdefaults import ClassDefaults
from uedcli.classindex import ClassIndex
from uedcli.model import Actor, Level
from uedcli.tests.conftest import StubClassIndex, cube_room

IDX = StubClassIndex()

uedcli_native = pytest.importorskip("uedcli_native")

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

pytestmark = pytest.mark.skipif(
    not (UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (build_scene's lighting needs real class schemas)")


def _defaults_resolver(name: str) -> str | None:
    p = UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


DEFAULTS = ClassDefaults(_defaults_resolver)


def _ued22_index() -> ClassIndex:
    """A real `ClassIndex` over the committed UED22 corpus — needed (unlike the offline
    `StubClassIndex`) whenever the level has a non-brush actor (e.g. a light), since `build_scene`
    resolves its class defaults via `index.resolver()`, which `StubClassIndex` doesn't implement."""
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def _write_fixture_trunk(tmp_path) -> tuple:
    """A tiny project (`<tmp>/proj/maps/TestLevel/`) holding one subtract room brush — the
    small/already-cached fixture the plan calls for (NOT UNATCO: a cold solve is ~24s)."""
    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    level = Level(actors={room.name: room}, order=[room.name])
    trunk.write_level(maps_dir, level, {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)
    return project, "TestLevel"


def test_build_scene_payload_has_polys_and_actors(tmp_path):
    from uedcli.serve.scene import build_scene_payload

    project, level_name = _write_fixture_trunk(tmp_path)
    payload = build_scene_payload(project, level_name, IDX, DEFAULTS, [])

    assert payload.polys
    for poly in payload.polys:
        assert poly.tex_index == -1 or poly.tex_index >= 0    # -1: untextured (flat grey), else in range

    names = {a.name for a in payload.actors}
    assert names == {"Room"}
    room_actor = next(a for a in payload.actors if a.name == "Room")
    assert room_actor.cls == "Engine.Brush" or "Brush" in room_actor.cls
    assert room_actor.bbox_lo != room_actor.bbox_hi           # a real, non-degenerate box
    assert room_actor.order_value == "m"
    assert isinstance(room_actor.props, list)                 # the inspector's raw T3D property set
    assert all(len(p) == 2 for p in room_actor.props)


def test_build_scene_payload_second_call_is_a_cache_hit(tmp_path, monkeypatch):
    from uedcli.serve.scene import build_scene_payload

    project, level_name = _write_fixture_trunk(tmp_path)

    calls = []
    real = uedcli_native.build_geometry_bspcsg

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(uedcli_native, "build_geometry_bspcsg", spy)

    build_scene_payload(project, level_name, IDX, DEFAULTS, [])
    assert len(calls) == 1
    build_scene_payload(project, level_name, IDX, DEFAULTS, [])
    assert len(calls) == 1                                    # second call: preview_cache hit, no re-solve


def test_scene_route_returns_200_with_a_json_safe_payload(tmp_path, monkeypatch):
    """HTTP-level round-trip for the real `/api/level/{level}/scene` route — `build_scene_payload`
    alone (the test above) never round-trips through the actual HTTP/JSON layer, so a shape that
    the JSON encoder can't handle would slip past it. Includes a real light actor so at least one
    poly carries a non-None `lightmap` (a bare brush level never does — `gather_lights` finds
    nothing to bake): `bake_radiance`'s RGB buffer is a plain `list[float]`, already JSON-safe, but
    that is exactly the kind of assumption this test exists to keep honest against the real route
    rather than take on faith. `_scene_inputs` is monkeypatched to an offline (real `ClassIndex`,
    `ClassDefaults`) trio so the test stays hermetic (no real per-user games config needed)."""
    from fastapi.testclient import TestClient

    from uedcli.serve import app as serve_app

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    light = Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    level = Level(actors={room.name: room, light.name: light}, order=[room.name, light.name])
    trunk.write_level(maps_dir, level, {room.name: "m", light.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda project: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.get("/api/level/TestLevel/scene")

    assert r.status_code == 200
    body = r.json()
    assert body["polys"] and body["actors"]
    lightmaps = [p["lightmap"] for p in body["polys"]]
    assert any(lm is not None for lm in lightmaps)   # the light actually produced baked radiance
    for lm in lightmaps:
        if lm is not None:
            assert isinstance(lm[-1], list) and all(isinstance(v, float) for v in lm[-1])
