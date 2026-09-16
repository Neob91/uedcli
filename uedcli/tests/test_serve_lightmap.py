"""`uedcli serve`'s lightmap-atlas assembly: packs `build_scene`'s per-poly baked lumel grids into
one RGB image, keyed by poly index, scaled by one global `intensity` so overbright (>1.0) survives
an 8-bit atlas. Mirrors `test_serve_textures.py`'s style."""
from __future__ import annotations

import io

from uedcli.serve.lightmap import build_lightmap_atlas


def _poly(lightmap):
    """A minimal `build_scene`-shaped poly tuple: only the last field (the lightmap) is read by the
    atlas builder, so the other eight are placeholders."""
    return (None, None, None, None, None, -1, False, 0, lightmap)


def _lm(u_size, v_size, rgb):
    return ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), u_size, v_size, rgb)


def _read(png_bytes):
    from PIL import Image

    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def test_manifest_keyed_by_poly_index_with_interior_rect_inside_the_gutter():
    polys = [_poly(None), _poly(_lm(2, 1, [1.0] * 6)), _poly(None), _poly(_lm(1, 3, [1.0] * 9))]
    _png, manifest, _w, _h, _intensity = build_lightmap_atlas(polys)
    assert set(manifest) == {1, 3}                       # only lit polys, keyed by poly index
    assert manifest[1]["w"] == 2 and manifest[1]["h"] == 1
    assert manifest[3]["w"] == 1 and manifest[3]["h"] == 3
    for rect in manifest.values():
        assert rect["x"] >= 1 and rect["y"] >= 1          # inside the 1-lumel gutter


def test_empty_level_returns_valid_1x1_png_intensity_1():
    png, manifest, w, h, intensity = build_lightmap_atlas([_poly(None), _poly(None)])
    assert manifest == {} and (w, h) == (1, 1) and intensity == 1.0
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_intensity_is_the_global_max_and_encoding_recovers_the_value():
    # Two lumels: multiplier 0.5 and overbright 2.0. intensity = max(1, 2.0) = 2.0.
    png, manifest, _w, _h, intensity = build_lightmap_atlas(
        [_poly(_lm(2, 1, [0.5, 0.5, 0.5, 2.0, 2.0, 2.0]))])
    assert intensity == 2.0
    img = _read(png)
    rect = manifest[0]
    lo = img.getpixel((rect["x"], rect["y"]))            # lumel 0 -> 0.5
    hi = img.getpixel((rect["x"] + 1, rect["y"]))        # lumel 1 -> 2.0 (overbright preserved)
    assert abs(lo[0] / 255 * intensity - 0.5) < 0.01
    assert abs(hi[0] / 255 * intensity - 2.0) < 0.01     # would be crushed to 1.0 without intensity


def test_gutter_replicates_edge_lumels_for_clamp():
    # A 2x1 patch: left lumel 0.2, right 0.9. The gutter column left of the interior must equal the
    # left edge lumel (edge-replicate, so a nearest sample just past the edge clamps, not bleeds).
    png, manifest, _w, _h, intensity = build_lightmap_atlas(
        [_poly(_lm(2, 1, [0.2, 0.2, 0.2, 0.9, 0.9, 0.9]))])
    img = _read(png)
    rect = manifest[0]
    left_edge = img.getpixel((rect["x"], rect["y"]))
    left_gutter = img.getpixel((rect["x"] - 1, rect["y"]))
    assert left_gutter == left_edge


def test_polys_sharing_a_lightmap_object_share_one_rect():
    shared = _lm(2, 2, [1.0] * 12)
    _png, manifest, _w, _h, _i = build_lightmap_atlas([_poly(shared), _poly(shared), _poly(None)])
    assert manifest[0] == manifest[1]                    # deduped: one packed patch, two poly keys
    assert 2 not in manifest


def test_lightmap_route_returns_200_with_a_json_safe_payload(tmp_path, monkeypatch):
    """HTTP round-trip for the real `/api/level/{level}/lightmap` route against a light-bearing
    fixture (a room + a centred `Engine.Light`), symmetric with the scene/atlas route tests. Every
    poly whose scene payload carries a lightmap frame must have a manifest rect keyed by its index.

    `/lightmap` no longer auto-solves (gui-explicit-rebuild plan, Task 2) — a Rebuild is simulated
    directly via `app.state.build_and_publish_geometry` before hitting the route."""
    from decimal import Decimal
    from pathlib import Path
    from types import SimpleNamespace

    import glob
    import os

    import pytest
    from fastapi.testclient import TestClient

    from uedcli import trunk
    from uedcli.classdefaults import ClassDefaults
    from uedcli.classindex import ClassIndex
    from uedcli.model import Actor, Level
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import cube_room

    pytest.importorskip("uedcli_native")
    ued22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
    if not (ued22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present")

    def _resolver(name):
        p = ued22 / f"{name}.u"
        return str(p) if p.is_file() else None

    defaults = ClassDefaults(_resolver)
    index = ClassIndex.from_files(
        [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(ued22 / "*.u"))])

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    light = Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    level = Level(actors={room.name: room, light.name: light}, order=[room.name, light.name])
    trunk.write_level(maps_dir, level, {room.name: "m", light.name: "n"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs", lambda project: ([], index, defaults))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    app.state.build_and_publish_geometry("TestLevel", [], index, defaults)

    r = c.get("/api/level/TestLevel/lightmap")
    assert r.status_code == 200
    body = r.json()
    assert body["intensity"] >= 1.0
    assert body["manifest"]                                     # the light produced lit polys
    assert body["png_base64"]

    scene = c.get("/api/level/TestLevel/scene").json()
    for i, poly in enumerate(scene["polys"]):
        if poly["lightmap"] is not None:
            assert str(i) in body["manifest"]                   # every lit poly has a packed rect
