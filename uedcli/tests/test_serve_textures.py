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
    png_bytes, manifest, width, height = build_atlas(table, [None, None, None])
    assert set(manifest) == {0, 1, 2}
    for idx, (w, h, _rgb, _mask) in enumerate(table):
        rect = manifest[idx]
        assert rect.w == w and rect.h == h
        assert 0 <= rect.x <= width - w
        assert 0 <= rect.y <= height - h
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"          # a real PNG


def test_rects_do_not_overlap():
    table = [_tex(3, 5, (1, 2, 3), [1] * 15) for _ in range(4)]
    _png, manifest, _w, _h = build_atlas(table, [None] * len(table))
    boxes = [(r.x, r.y, r.x + r.w, r.y + r.h) for r in manifest.values()]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap_x = a[0] < b[2] and b[0] < a[2]
            overlap_y = a[1] < b[3] and b[1] < a[3]
            assert not (overlap_x and overlap_y), (a, b)


def test_alpha_channel_carries_the_per_texel_mask():
    from PIL import Image
    import io

    table = [_tex(2, 1, (200, 100, 50), [1, 0])]   # texel 0 opaque, texel 1 transparent
    png_bytes, manifest, _w, _h = build_atlas(table, [None])
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    rect = manifest[0]
    px0 = img.getpixel((rect.x + 0, rect.y))
    px1 = img.getpixel((rect.x + 1, rect.y))
    assert px0[:3] == (200, 100, 50) and px0[3] == 255
    assert px1[3] == 0                                     # masked texel -> alpha 0


def test_manifest_rect_carries_the_real_group_name():
    """`build_atlas`'s `groups` param becomes each rect's `name` -- `None` for an index `groups`
    doesn't cover (mirrors `_TextureTable.group_for`'s own out-of-range disposition)."""
    table = [_tex(2, 2, (1, 2, 3), [1, 1, 1, 1]), _tex(1, 1, (4, 5, 6), [1])]
    _png, manifest, _w, _h = build_atlas(table, ["CoreTexMetal.Metal.Area51Wall_A"])
    assert manifest[0].name == "CoreTexMetal.Metal.Area51Wall_A"
    assert manifest[1].name is None


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
    groups: list = []
    polys, texture_table, _owners, _geom_hash, _light_hash = build_scene(
        level, [str(fixtures / "LUM_InfoPortraits.utx")],
        StubClassIndex(), defaults=ClassDefaults(_resolver), groups_out=groups)
    assert len(groups) == len(texture_table)   # groups_out stays parallel to texture_table

    _png, manifest, _w, _h = build_atlas(texture_table, groups)
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

    from uedcli.serve import sessions

    monkeypatch.setattr(serve_app, "_scene_inputs",
                        lambda project: ([], StubClassIndex(), ClassDefaults(_resolver)))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")

    r = c.get(f"/api/session/{sess.id}/atlas")   # Task 13: /atlas is session-scoped now

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["png_base64"], str) and body["width"] >= 1 and body["height"] >= 1


def test_atlas_route_manifest_name_carries_the_real_group_identity(tmp_path, monkeypatch):
    """The `/atlas` route's manifest entries carry a real `Package.Group.Name` via `name` for a
    texture that resolves through `_TextureTable.index_for` -- a Mover's own texture (Load-owned,
    `resolve_mover_scene_polys`), so this needs no native CSG rebuild to reach the route, just a real
    fixture with a genuinely grouped texture (`CoreTexWater.utx`'s `dirtywater`, `Group=water`).

    A real `ClassIndex` (not `StubClassIndex`) -- `_build_actors`'s own `_class_ctx_for` needs a
    real `.resolver()`, which `StubClassIndex` doesn't have (a pre-existing gap, unrelated to this
    change -- confirmed still failing identically on master with `StubClassIndex` here)."""
    import glob
    import os
    from pathlib import Path
    from types import SimpleNamespace

    import pytest
    from fastapi.testclient import TestClient

    from uedcli import trunk
    from uedcli.builders import cube, make_brush_actor
    from uedcli.classdefaults import ClassDefaults
    from uedcli.classindex import ClassIndex
    from uedcli.model import Level
    from uedcli.serve import app as serve_app
    from uedcli.serve import sessions
    from uedcli.tests.conftest import cube_room

    pytest.importorskip("uedcli_native")
    ued22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
    if not (ued22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present")

    def _resolver(name):
        p = ued22 / f"{name}.u"
        return str(p) if p.is_file() else None

    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(ued22 / "*.u"))]
    index = ClassIndex.from_files(files)

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    room = cube_room()
    mover = make_brush_actor("Door", cube(64, 8, 96, texture="CoreTexWater.dirtywater"),
                             mover_class="Engine.Mover")
    level = Level(actors={room.name: room, mover.name: mover}, order=[room.name, mover.name])
    trunk.write_level(maps_dir, level, {room.name: "m", mover.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)

    fixture = str(Path(__file__).parent / "fixtures" / "CoreTexWater.utx")
    monkeypatch.setattr(serve_app, "_scene_inputs",
                        lambda project: ([fixture], index, ClassDefaults(_resolver)))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")

    r = c.get(f"/api/session/{sess.id}/atlas")

    assert r.status_code == 200
    manifest = r.json()["manifest"]
    names = {rect["name"] for rect in manifest.values()}
    assert "CoreTexWater.water.dirtywater" in names
