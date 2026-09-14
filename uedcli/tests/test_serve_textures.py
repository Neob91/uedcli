"""`uedcli serve`'s texture-atlas assembly (plan Task 3): packs a `build_scene` `texture_table`
into one RGBA image with an index-keyed manifest. The alpha test itself is a per-poly decision
(Task 6's material split) — this module just carries every entry's real per-texel mask as alpha."""
from __future__ import annotations

from uedcli.serve.textures import build_atlas


def _tex(w, h, rgb_byte, mask_bytes):
    return (w, h, bytes(rgb_byte) * (w * h), bytes(mask_bytes))


def test_manifest_has_one_rect_per_table_entry_keyed_by_index():
    table = [
        _tex(2, 2, (255, 0, 0), [1, 1, 1, 1]),
        _tex(4, 1, (0, 255, 0), [1, 0, 1, 0]),
        _tex(1, 1, (0, 0, 255), [0]),
    ]
    png_bytes, manifest, width, height = build_atlas(table)
    assert set(manifest) == {0, 1, 2}
    for idx, (w, h, _rgb, _mask) in enumerate(table):
        rect = manifest[idx]
        assert rect["w"] == w and rect["h"] == h
        assert 0 <= rect["x"] <= width - w
        assert 0 <= rect["y"] <= height - h
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"          # a real PNG


def test_rects_do_not_overlap():
    table = [_tex(3, 5, (1, 2, 3), [1] * 15) for _ in range(4)]
    _png, manifest, _w, _h = build_atlas(table)
    boxes = [(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]) for r in manifest.values()]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap_x = a[0] < b[2] and b[0] < a[2]
            overlap_y = a[1] < b[3] and b[1] < a[3]
            assert not (overlap_x and overlap_y), (a, b)


def test_alpha_channel_carries_the_per_texel_mask():
    from PIL import Image
    import io

    table = [_tex(2, 1, (200, 100, 50), [1, 0])]   # texel 0 opaque, texel 1 transparent
    png_bytes, manifest, _w, _h = build_atlas(table)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    rect = manifest[0]
    px0 = img.getpixel((rect["x"] + 0, rect["y"]))
    px1 = img.getpixel((rect["x"] + 1, rect["y"]))
    assert px0[:3] == (200, 100, 50) and px0[3] == 255
    assert px1[3] == 0                                     # masked texel -> alpha 0


def test_every_poly_tex_index_resolves_to_a_manifest_rect():
    """End-to-end shape check against a real `build_scene` payload: every non-negative `tex_index`
    a poly carries must key into the atlas manifest. Reuses the real fixture the scene test builds,
    so it exercises the actual `texture_table` `build_scene` produces, not a hand-rolled stand-in."""
    import pytest
    from pathlib import Path
    from types import SimpleNamespace

    from uedcli import trunk
    from uedcli.classdefaults import ClassDefaults
    from uedcli.model import Level
    from uedcli.preview_native import build_scene
    from uedcli.tests.conftest import StubClassIndex, cube_room

    uedcli_native = pytest.importorskip("uedcli_native")
    ued22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
    if not (ued22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present")

    def _resolver(name):
        p = ued22 / f"{name}.u"
        return str(p) if p.is_file() else None

    room = cube_room(texture="LUM_InfoPortraits.ArthurCallaway")
    level = Level(actors={room.name: room}, order=[room.name])
    fixtures = Path(__file__).parent / "fixtures"
    polys, texture_table = build_scene(level, [str(fixtures / "LUM_InfoPortraits.utx")],
                                       StubClassIndex(), defaults=ClassDefaults(_resolver))

    _png, manifest, _w, _h = build_atlas(texture_table)
    for verts, base, tu, tv, pan, tex_index, masked, flags, lightmap in polys:
        if tex_index >= 0:
            assert tex_index in manifest


def test_atlas_route_returns_200_with_a_json_safe_payload(tmp_path, monkeypatch):
    """HTTP-level round-trip for the real `/api/level/{level}/atlas` route (symmetric with the
    scene route's own regression test) -- `_scene_inputs` is monkeypatched offline so the test
    stays hermetic."""
    from pathlib import Path
    from types import SimpleNamespace

    import pytest
    from fastapi.testclient import TestClient

    from uedcli import trunk
    from uedcli.classdefaults import ClassDefaults
    from uedcli.model import Level
    from uedcli.serve import app as serve_app
    from uedcli.tests.conftest import StubClassIndex, cube_room

    pytest.importorskip("uedcli_native")
    ued22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
    if not (ued22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present")

    def _resolver(name):
        p = ued22 / f"{name}.u"
        return str(p) if p.is_file() else None

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    trunk.write_level(maps_dir, Level(actors={room.name: room}, order=[room.name]), {room.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    monkeypatch.setattr(serve_app, "_scene_inputs",
                        lambda project: ([], StubClassIndex(), ClassDefaults(_resolver)))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.get("/api/level/TestLevel/atlas")

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["png_base64"], str) and body["width"] >= 1 and body["height"] >= 1
