"""Offline tests for `preview_native` — the `--native` backend (spec §9). Everything runs
with no editor/container; tests that carve geometry need the `uedcli_native` extension
(skipped when absent, same as the CSG differential suite)."""
from __future__ import annotations

import hashlib
import math
import os
from decimal import Decimal
from pathlib import Path

import pytest

from uedcli import preview_native as pn
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level
from uedcli.preview_shots import Shot, parse_shot
from uedcli.rotation import world_vertices
from uedcli.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs

uedcli_native = pytest.importorskip("uedcli_native")

FIXTURES = Path(__file__).parent / "fixtures"


def _level(*actors: Actor) -> Level:
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    return lvl


def _room(name="Room", size=512.0, height=256.0, texture=None) -> Actor:
    return make_brush_actor(name, cube(size, size, height, texture=texture), csg="subtract")


def _set_prop(actor: Actor, key: str, value: str) -> None:
    # MainScale/PostScale are typed model fields (spec §10), no longer props — route them there so
    # the native scale-reject gate (which reads the typed field) sees them.
    if key in ("MainScale", "PostScale"):
        from uedcli.transform import parse_fscale
        setattr(actor, "main_scale" if key == "MainScale" else "post_scale", parse_fscale(value))
        return
    actor.props = [(k, v) for k, v in actor.props if k != key] + [(key, value)]


# --------------------------------------------------------------- scale/sheer rejections


def test_mainscale_rejected_named():
    room = _room()
    _set_prop(room, "MainScale", "(Scale=(X=2.000000),SheerAxis=SHEER_ZX)")
    with pytest.raises(pn.NativePreviewError, match="Room.*MainScale.*X=2"):
        pn.build_scene(_level(room), [], IDX)


def test_postscale_rejected_named():
    room = _room()
    _set_prop(room, "PostScale", "(Scale=(Z=0.500000),SheerAxis=SHEER_ZX)")
    with pytest.raises(pn.NativePreviewError, match="Room.*PostScale.*Z=0.5"):
        pn.build_scene(_level(room), [], IDX)


def test_sheerrate_rejected_named():
    room = _room()
    _set_prop(room, "MainScale", "(SheerRate=0.250000,SheerAxis=SHEER_ZX)")
    with pytest.raises(pn.NativePreviewError, match="Room.*MainScale.*SheerRate=0.25"):
        pn.build_scene(_level(room), [], IDX)


def test_identity_scale_props_accepted():
    room = _room()                       # make_brush_actor writes (SheerAxis=SHEER_ZX) both
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6               # a carved box renders its 6 interior faces


# --------------------------------------------------------------- zero-brush / BuildError


def test_zero_brush_trunk_is_named_error():
    lvl = _level(Actor(name="LevelInfo", cls="Engine.LevelInfo"))
    with pytest.raises(pn.NativePreviewError, match="no CSG brush actors"):
        pn.build_scene(lvl, [], IDX)


def test_build_error_surfaces_cleanly():
    bad = _room()
    bad.brush.polys = bad.brush.polys[:1]        # an open solid: CSG core rejects/degenerates
    lvl = _level(bad)
    try:
        pn.build_scene(lvl, [], IDX)                  # either a clean error or a degenerate build…
    except pn.NativePreviewError as e:
        assert "native CSG build failed" in str(e) or "nothing to render" in str(e)
    # …but NEVER a raw uedcli_native.BuildError / IndexError escaping (repo rule).


# --------------------------------------------------------------- join guards (§4.4)


def test_out_of_range_surf_owner_renders_grey_not_indexerror():
    room = _room()
    polys, table = pn.build_scene(_level(room), [], IDX)
    # Forge the guard input directly: node polys with hostile indices via _node_polys.
    from uedcli.native.umodel import BspNode, BspSurf, BspVert, Model
    m = Model()
    m.points = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0)]
    m.verts = [BspVert(i_vertex=0), BspVert(i_vertex=1), BspVert(i_vertex=2)]
    m.surfs = [BspSurf(i_actor=999, i_brush_poly=-1)]
    m.nodes = [BspNode(plane=(0, 0, 1, 0), i_vert_pool=0, i_surf=0, num_vertices=3)]
    got = pn._node_polys(m)
    assert got == [([m.points[0], m.points[1], m.points[2]], 999, -1)]
    # A hostile vert pool / point index never raises either — the node is skipped.
    m.nodes[0].i_vert_pool = 99
    assert pn._node_polys(m) == []
    m.nodes[0].i_vert_pool = 0
    m.verts[0].i_vertex = 12345
    assert pn._node_polys(m) == []


# --------------------------------------------------------------- checkerboard + warning


def test_unresolvable_ref_checkerboards_and_warns_once(capsys):
    room = _room(texture="Missing.Tex")
    polys, table = pn.build_scene(_level(room), [], IDX)
    err = capsys.readouterr().err
    assert err.count("Missing.Tex") == 1         # ONE warning per distinct ref
    assert len(table) == 1                       # the shared checkerboard slot
    w, h, data = table[0]
    assert data[:3] == b"\xff\x00\xff"           # magenta/black checks
    assert all(p[5] == 0 for p in polys)


def test_bare_ref_is_unresolvable(capsys):
    room = _room(texture="barename")
    polys, table = pn.build_scene(_level(room), [], IDX)
    assert "barename" in capsys.readouterr().err
    assert len(table) == 1                       # checkerboard


def test_real_fixture_texture_resolves():
    room = _room(texture="LUM_InfoPortraits.ArthurCallaway")
    polys, table = pn.build_scene(_level(room), [str(FIXTURES / "LUM_InfoPortraits.utx")], IDX)
    assert len(table) == 1
    w, h, _ = table[0]
    assert (w, h) == (64, 64)


# --------------------------------------------------------------- UV frames (§5)


def _quad_poly(actor_name="B"):
    """The +X face poly of a unit-ish cube brush, with authored axes."""
    room = _room(actor_name, 64, 64)
    return room, room.brush.polys[0]


def test_uv_frame_authored_axes_identity_actor():
    actor, poly = _quad_poly()
    poly.origin = (1.0, 2.0, 3.0)
    poly.texture_u = (0.0, 1.0, 0.0)
    poly.texture_v = (0.0, 0.0, -1.0)
    poly.pan = (7, 9)
    base, tu, tv, pan = pn._world_uv_frame(actor, poly)
    assert base == (1.0, 2.0, 3.0)               # Location 0, no PrePivot, no rotation
    assert tu == (0.0, 1.0, 0.0) and tv == (0.0, 0.0, -1.0)
    assert pan == (7.0, 9.0)


def test_uv_frame_rotated_prepivoted_matches_hand_derived():
    actor, poly = _quad_poly()
    actor.location = (Decimal(100), Decimal(200), Decimal(50))
    _set_prop(actor, "Rotation", "(Yaw=16384)")   # 90°: x̂→ŷ, ŷ→−x̂ (GMath exact at 90°)
    _set_prop(actor, "PrePivot", "(X=10.000000,Y=20.000000,Z=30.000000)")
    poly.origin = (12.0, 24.0, 36.0)
    poly.texture_u = (1.0, 0.0, 0.0)
    poly.texture_v = (0.0, 0.0, 1.0)
    base, tu, tv, pan = pn._world_uv_frame(actor, poly)
    # base = Loc + R·(Origin − PrePivot); R(yaw 90°)·(2,4,6) = (−4,2,6)
    assert base == pytest.approx((96.0, 202.0, 56.0), abs=1e-3)
    assert tu == pytest.approx((0.0, 1.0, 0.0), abs=1e-5)    # x̂ rotates to ŷ
    assert tv == pytest.approx((0.0, 0.0, 1.0), abs=1e-5)    # ẑ unchanged by yaw
    assert pan == (0.0, 0.0)                                  # missing Pan → (0,0)


def test_uv_frame_missing_origin_and_axes_fall_back():
    actor, poly = _quad_poly()
    actor.location = (Decimal(5), Decimal(6), Decimal(7))
    poly.origin = None
    poly.texture_u = (0.0, 0.0, 0.0)             # zero axes → _tex_basis default
    poly.texture_v = None
    base, tu, tv, pan = pn._world_uv_frame(actor, poly)
    assert base == (5.0, 6.0, 7.0)               # local zero origin
    from uedcli.builders import _tex_basis
    n = tuple(float(c) for c in poly.normal)
    exp_u, exp_v = _tex_basis(n)
    assert tu == pytest.approx(exp_u) and tv == pytest.approx(exp_v)


# --------------------------------------------------------------- transform cross-checks


def test_rotated_brush_rust_transform_matches_world_vertices():
    """The §9 rotated-brush oracle: Rust's FPoly::Transform (rot3x3 through build_geometry)
    lands vertices where the GMath-verified Python `rotation.world_vertices` puts them."""
    room = _room("Rot", 256, 128)
    room.location = (Decimal(64), Decimal(-32), Decimal(16))
    _set_prop(room, "Rotation", "(Pitch=4096,Yaw=12288,Roll=2048)")
    _set_prop(room, "PrePivot", "(X=8.000000,Y=4.000000,Z=2.000000)")
    lvl = _level(room)
    polys, _ = pn.build_scene(lvl, [], IDX)
    got = {tuple(round(polys_c, 2) for polys_c in p[0][i:i + 3])
           for p in polys for i in range(0, len(p[0]), 3)}
    expect = {tuple(round(c, 2) for c in v) for v in world_vertices(room)}
    # A lone subtract keeps its faces whole (possibly split by BSP, but every node vertex
    # lies on the brush's transformed geometry) — corner set must be a superset match.
    assert expect <= got


def test_mover_world_polys_match_world_vertices():
    mover = make_brush_actor("Door", cube(64, 8, 96), location=(10.0, 20.0, 30.0),
                             mover_class="Engine.Mover")
    _set_prop(mover, "Rotation", "(Yaw=8192)")
    _set_prop(mover, "PrePivot", "(X=32.000000)")
    lvl = _level(_room(), mover)
    got = pn._mover_world_polys(lvl, IDX)
    assert got and all(a.name == "Door" for _, a, _ in got)
    flat = {tuple(round(c, 3) for c in v) for verts, _, _ in got for v in verts}
    expect = {tuple(round(c, 3) for c in v) for v in world_vertices(mover)}
    assert flat == expect


def test_movers_are_out_of_world_csg_but_rendered():
    mover = make_brush_actor("Door", cube(64, 8, 96), mover_class="Engine.Mover")
    lvl = _level(_room(), mover)
    brushes, join = pn._brush_inputs(lvl, IDX)
    assert [n for n, _ in join] == ["Room"]      # mover NOT in the CSG input
    polys, _ = pn.build_scene(lvl, [], IDX)
    assert len(polys) == 6 + 6                   # room faces + mover extra_polys


# --------------------------------------------------------------- invisible faces


def test_pf_invisible_faces_dropped():
    room = _room()
    room.brush.polys[0].flags = pn.PF_INVISIBLE
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 5


# --------------------------------------------------------------- aim points


def test_aim_point_brush_is_aabb_centre():
    room = _room()
    room.location = (Decimal(100), Decimal(0), Decimal(0))
    lvl = _level(room)
    assert pn.actor_aim_point(lvl, "room") == pytest.approx((100.0, 0.0, 0.0))


def test_aim_point_point_actor_is_location():
    a = Actor(name="L1", cls="Engine.Light", location=(Decimal(1), Decimal(2), Decimal(3)))
    assert pn.actor_aim_point(_level(a), "l1") == (1.0, 2.0, 3.0)


def test_aim_point_unknown_actor_named_error():
    with pytest.raises(pn.NativePreviewError, match="actor not found: Ghost"):
        pn.actor_aim_point(_level(_room()), "Ghost")


# --------------------------------------------------------------- render_shots E2E


def test_render_shots_writes_pngs(tmp_path):
    lvl = _level(_room())
    shots = [parse_shot("at:0,0,0;rot:0,0"), parse_shot("at:0,0,0;rot:0,90;name:east")]
    n = pn.render_shots(level=lvl, shots=shots, out_dir=tmp_path / "out", size=(160, 120),
                        index=IDX)
    assert n == 2
    assert (tmp_path / "out" / "shot-01.png").is_file()
    assert (tmp_path / "out" / "east.png").is_file()


def test_render_shots_unwritable_out_dir(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    if os.access(ro, os.W_OK):                   # running as root: cannot make unwritable
        pytest.skip("cannot create an unwritable dir here")
    try:
        with pytest.raises(pn.NativePreviewError, match="out-dir"):
            pn.render_shots(level=_level(_room()), shots=[parse_shot("at:0,0,0;rot:0,0")], index=IDX,
                            out_dir=ro / "sub", size=(32, 32))
    finally:
        ro.chmod(0o755)


def test_render_shots_all_or_nothing_actor_resolution(tmp_path):
    lvl = _level(_room())
    shots = [parse_shot("at:0,0,0;rot:0,0"), parse_shot("at:0,0,0;look:@Nope")]
    with pytest.raises(pn.NativePreviewError, match="actor not found: Nope"):
        pn.render_shots(level=lvl, shots=shots, out_dir=tmp_path, size=(32, 32), index=IDX)
    assert not list(tmp_path.glob("*.png"))      # nothing written


# --------------------------------------------------------------- pixel probe (§9)


def test_pixel_probe_marker_quad_lands_at_oracle_pixel():
    """Place a small marker at a known world point, render, and assert the ORACLE-projected
    pixel is hit (guards the projection + the Python-side camera basis end to end)."""
    room = _room("Room", 1024, 512)
    lvl = _level(room)
    polys, table = pn.build_scene(lvl, [], IDX)
    # marker quad: 8uu square centred at (200, 60, -40), facing the camera at origin
    cx, cy, cz = 200.0, 60.0, -40.0
    quad = ([cx, cy - 4, cz - 4, cx, cy + 4, cz - 4, cx, cy + 4, cz + 4, cx, cy - 4, cz + 4],
            [cx, cy, cz], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [0.0, 0.0], 0)
    red = (1, 1, bytes([255, 0, 0]))
    import uedcli_native
    W, H, FOV = 320, 240, 90.0
    fwd, right, up = pn.camera_basis(0.0, 0.0)
    rgb = uedcli_native.render_frame(polys + [quad], list(table) + [red],
                                     ((0.0, 0.0, 0.0), fwd, right, up, FOV), (W, H))
    # oracle: focal = (W/2)/tan(45°) = 160; sx = 160 + 60*160/200 = 208; sy = 120 + 40*160/200 = 152
    o = (152 * W + 208) * 3
    assert rgb[o] > 100 and rgb[o + 1] < 60 and rgb[o + 2] < 60   # red marker, shaded


# --------------------------------------------------------------- golden image (§9)

GOLDEN = FIXTURES / "native_preview_golden.png"

# csg-golden case c (add_in_subtract): subtract room + added pillar — real multi-brush
# provenance (case a is a lone subtract; the M0 carved-box path has no brushes at all).
_CASE_C_ROOM = dict(size=512.0, height=256.0)
_CASE_C_PILLAR = dict(size=128.0, height=256.0)


def _case_c_level() -> Level:
    room = make_brush_actor("Room", cube(512, 512, 256, texture="Golden.Asym"),
                            csg="subtract")
    pillar = make_brush_actor("Pillar", cube(128, 128, 256, texture="Golden.Asym"),
                              location=(96.0, -64.0, 0.0), csg="add")
    return _level(room, pillar)


def _synthetic_scene(tmp_path=None):
    """Case-c level with a synthetic asymmetric 4-texel texture injected straight into the
    table (no package file needed): the resolver misses, then the table is patched."""
    lvl = _case_c_level()
    polys, table = pn.build_scene(lvl, [], IDX)
    asym = (2, 2, bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]))
    table = [asym if i == 0 else t for i, t in enumerate(table)]
    return polys, table


def test_golden_image_byte_exact(capsys):
    """Two exact-trig poses (0°/90°) at 320×240, byte-exact pixel buffers on the dev
    platform (Linux/x86_64 — spike 40). On mismatch prints the differing-byte count.
    Bless/regenerate: UEDCLI_BLESS_GOLDEN=1 bin/test -k golden. Blessed 2026-07-16 AFTER
    the anchor verdict (U/V/Pan pinned against the live editor + game references —
    dev/docs/spikes/2026-07-16-native-preview-anchor/).
    RE-BLESSED 2026-07-20 after the GMath trig-table fix (§92 §41): `camera_basis` now reads the
    editor-EXACT float32 GMath table, so the 90°-yaw pose uses cos(90°) = −8.742278e-08 (the game's
    own value) instead of double 0. The 0° frame stays BYTE-IDENTICAL; the 90° frame's face-side flips
    are what the GAME renders (the game builds its camera from the same table), so the golden tracks it.
    Cross-reviewed defensible; the anchor U/V/Pan pins are unaffected (texture math, not camera trig)."""
    capsys.readouterr()                          # swallow the checkerboard warning
    import uedcli_native
    polys, table = _synthetic_scene()
    frames = []
    for pitch, yaw in ((0.0, 0.0), (0.0, 90.0)):
        fwd, right, up = pn.camera_basis(pitch, yaw)
        frames.append(uedcli_native.render_frame(
            polys, table, ((-100.0, 0.0, 0.0), fwd, right, up, 90.0), (320, 240)))
    buf = b"".join(frames)
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        from PIL import Image
        Image.frombytes("RGB", (320, 480), buf).save(GOLDEN)
        pytest.skip(f"golden blessed → {GOLDEN}")
    if not GOLDEN.is_file():
        pytest.fail("golden fixture missing — run UEDCLI_BLESS_GOLDEN=1 bin/test -k golden "
                    "(bless ONLY after the anchor verdict, spec §9)")
    from PIL import Image
    want = Image.open(GOLDEN).convert("RGB").tobytes()
    if buf != want:
        diff = sum(1 for a, b in zip(buf, want) if a != b) + abs(len(buf) - len(want))
        pytest.fail(f"native-preview golden mismatch: {diff} differing bytes "
                    f"(re-bless with UEDCLI_BLESS_GOLDEN=1 only after re-verifying the "
                    f"anchor — spec §9)")
