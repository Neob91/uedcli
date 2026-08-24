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
from uedcli.tests.conftest import StubClassIndex, cube_room, set_prop

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs

uedcli_native = pytest.importorskip("uedcli_native")

FIXTURES = Path(__file__).parent / "fixtures"


def _level(*actors: Actor) -> Level:
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    return lvl


# --------------------------------------------------------------- scaled/mirrored/sheared render
# Scaled brushes now RENDER (their linear map `L` bakes into the CSG world transform) instead of
# exiting 2 — `preview_native._marshal_brush` is a thin wrapper over the shared `_build_brush_input`.


def test_mainscale_brush_renders_scaled():
    """A non-identity MainScale renders its 6 carved faces (was exit-2). The verts land where the
    scaled `world_vertices` puts them — geometry cross-checked in `test_scaled_brush_preview_*`."""
    room = cube_room()
    set_prop(room, "MainScale", "(Scale=(X=2.000000),SheerAxis=SHEER_ZX)")
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6


def test_postscale_brush_renders_scaled():
    room = cube_room()
    set_prop(room, "PostScale", "(Scale=(Z=0.500000),SheerAxis=SHEER_ZX)")
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6


def test_sheerrate_brush_renders():
    """A pure-sheer scale (det=1) now renders too — the double `L` carries the sheer off-diagonal."""
    room = cube_room()
    set_prop(room, "MainScale", "(SheerRate=0.250000,SheerAxis=SHEER_ZX)")
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6


def test_degenerate_scale_exits_2_naming_the_brush():
    """A zero/degenerate scale axis makes `L` singular — the covariant map would ZeroDivisionError, so
    the marshaller refuses with a named `NativePreviewError` (exit 2), never a traceback."""
    room = cube_room()
    set_prop(room, "PostScale", "(Scale=(X=0.000000),SheerAxis=SHEER_ZX)")
    with pytest.raises(pn.NativePreviewError, match="Room.*non-invertible"):
        pn.build_scene(_level(room), [], IDX)


def test_identity_scale_props_accepted():
    room = cube_room()                   # make_brush_actor writes (SheerAxis=SHEER_ZX) both
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6               # a carved box renders its 6 interior faces


# --------------------------------------------------------------- zero-brush / BuildError


def test_zero_brush_trunk_is_named_error():
    lvl = _level(Actor(name="LevelInfo", cls="Engine.LevelInfo"))
    with pytest.raises(pn.NativePreviewError, match="no CSG brush actors"):
        pn.build_scene(lvl, [], IDX)


def test_build_error_surfaces_cleanly():
    bad = cube_room()
    bad.brush.polys = bad.brush.polys[:1]        # an open solid: CSG core rejects/degenerates
    lvl = _level(bad)
    try:
        pn.build_scene(lvl, [], IDX)                  # either a clean error or a degenerate build…
    except pn.NativePreviewError as e:
        assert "native CSG build failed" in str(e) or "nothing to render" in str(e)
    # …but NEVER a raw uedcli_native.BuildError / IndexError escaping (repo rule).


# --------------------------------------------------------------- join guards (§4.4)


def test_out_of_range_surf_owner_renders_grey_not_indexerror():
    room = cube_room()
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
    """A whole-frame render DEGRADES: one texture it cannot read must not stop the preview.

    The warning carries the decoder's named case, so a reader can tell a wrong ref from a
    layout we cannot decode yet without re-running anything — and it is printed ONCE per
    distinct ref, not once per face.
    """
    room = cube_room(texture="Missing.Tex")
    polys, table = pn.build_scene(_level(room), [], IDX)
    err = capsys.readouterr().err
    assert err.count("Missing.Tex") == 1         # ONE warning per distinct ref
    assert "unknown-package" in err              # the decoder's case, not a generic "missing"
    assert len(table) == 1                       # the shared checkerboard slot
    w, h, data = table[0]
    assert data[:3] == b"\xff\x00\xff"           # magenta/black checks
    assert all(p[5] == 0 for p in polys)


def test_bare_ref_is_unresolvable(capsys):
    """A bare ref is refused by name — `unqualified-ref`, not "not found" — because the fix is
    to qualify it, not to go looking for the texture."""
    room = cube_room(texture="barename")
    polys, table = pn.build_scene(_level(room), [], IDX)
    err = capsys.readouterr().err
    assert "barename" in err and "unqualified-ref" in err
    assert len(table) == 1                       # checkerboard


def test_real_fixture_texture_resolves():
    room = cube_room(texture="LUM_InfoPortraits.ArthurCallaway")
    polys, table = pn.build_scene(_level(room), [str(FIXTURES / "LUM_InfoPortraits.utx")], IDX)
    assert len(table) == 1
    w, h, _ = table[0]
    assert (w, h) == (64, 64)


# --------------------------------------------------------------- transform cross-checks


def test_rotated_brush_rust_transform_matches_world_vertices():
    """The §9 rotated-brush oracle: Rust's FPoly::Transform (rot3x3 through build_geometry)
    lands vertices where the GMath-verified Python `rotation.world_vertices` puts them."""
    room = cube_room("Rot", 256, 128)
    room.location = (Decimal(64), Decimal(-32), Decimal(16))
    set_prop(room, "Rotation", "(Pitch=4096,Yaw=12288,Roll=2048)")
    set_prop(room, "PrePivot", "(X=8.000000,Y=4.000000,Z=2.000000)")
    lvl = _level(room)
    polys, _ = pn.build_scene(lvl, [], IDX)
    got = {tuple(round(polys_c, 2) for polys_c in p[0][i:i + 3])
           for p in polys for i in range(0, len(p[0]), 3)}
    expect = {tuple(round(c, 2) for c in v) for v in world_vertices(room)}
    # A lone subtract keeps its faces whole (possibly split by BSP, but every node vertex
    # lies on the brush's transformed geometry) — corner set must be a superset match.
    assert expect <= got


def _preview_corner_set(lvl):
    polys, _ = pn.build_scene(lvl, [], IDX)
    return {tuple(round(c, 2) for c in p[0][i:i + 3])
            for p in polys for i in range(0, len(p[0]), 3)}


def test_scaled_brush_preview_geometry_matches_world_vertices():
    """The unify parity (spec §8): a SCALED brush's preview node-poly WORLD geometry lands exactly
    where `world_vertices` puts it — the shared `L` bake feeds the CSG world transform, so preview
    renders the scaled solid (was exit-2). Geometry, not pixels."""
    room = cube_room("Scaled", 256, 128)
    room.location = (Decimal(64), Decimal(-32), Decimal(16))
    set_prop(room, "PostScale",
             "(Scale=(X=1.500000,Y=2.000000,Z=0.500000),SheerAxis=SHEER_ZX)")
    expect = {tuple(round(c, 2) for c in v) for v in world_vertices(room)}
    assert expect <= _preview_corner_set(_level(room))


def test_mirrored_world_csg_brush_preview_geometry_matches_world_vertices():
    """A MIRRORED world-CSG brush (`det L < 0`, ring-reverse path) renders where `world_vertices`
    puts it. The Rust core keys winding off ring order (unlike the winding-agnostic renderer), so the
    marshaller's pre-reverse is what keeps the carved solid right-side-out here."""
    room = cube_room("Mir", 256, 128)
    room.location = (Decimal(64), Decimal(-32), Decimal(16))
    set_prop(room, "PostScale", "(Scale=(X=-1.500000),SheerAxis=SHEER_ZX)")
    expect = {tuple(round(c, 2) for c in v) for v in world_vertices(room)}
    assert expect <= _preview_corner_set(_level(room))


def test_mover_world_polys_match_world_vertices():
    mover = make_brush_actor("Door", cube(64, 8, 96), location=(10.0, 20.0, 30.0),
                             mover_class="Engine.Mover")
    set_prop(mover, "Rotation", "(Yaw=8192)")
    set_prop(mover, "PrePivot", "(X=32.000000)")
    lvl = _level(cube_room(), mover)
    got = pn._mover_world_polys(lvl, IDX)
    assert got and all(a.name == "Door" for _, a, _ in got)
    flat = {tuple(round(c, 3) for c in v) for verts, _, _ in got for v in verts}
    expect = {tuple(round(c, 3) for c in v) for v in world_vertices(mover)}
    assert flat == expect


def test_movers_are_out_of_world_csg_but_rendered():
    mover = make_brush_actor("Door", cube(64, 8, 96), mover_class="Engine.Mover")
    lvl = _level(cube_room(), mover)
    brushes, join = pn._brush_inputs(lvl, IDX)
    assert [n for n, _ in join] == ["Room"]      # mover NOT in the CSG input
    polys, _ = pn.build_scene(lvl, [], IDX)
    assert len(polys) == 6 + 6                   # room faces + mover extra_polys


# --------------------------------------------------------------- invisible faces


def test_pf_invisible_faces_dropped():
    room = cube_room()
    room.brush.polys[0].flags = pn.PF_INVISIBLE
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 5


# --------------------------------------------------------------- aim points


def test_aim_point_brush_is_aabb_centre():
    room = cube_room()
    room.location = (Decimal(100), Decimal(0), Decimal(0))
    lvl = _level(room)
    assert pn.actor_aim_point(lvl, "room") == pytest.approx((100.0, 0.0, 0.0))


def test_aim_point_point_actor_is_location():
    a = Actor(name="L1", cls="Engine.Light", location=(Decimal(1), Decimal(2), Decimal(3)))
    assert pn.actor_aim_point(_level(a), "l1") == (1.0, 2.0, 3.0)


def test_aim_point_unknown_actor_named_error():
    with pytest.raises(pn.NativePreviewError, match="actor not found: Ghost"):
        pn.actor_aim_point(_level(cube_room()), "Ghost")


# --------------------------------------------------------------- render_shots E2E


def test_render_shots_writes_pngs(tmp_path):
    lvl = _level(cube_room())
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
            pn.render_shots(level=_level(cube_room()), index=IDX, out_dir=ro / "sub",
                            shots=[parse_shot("at:0,0,0;rot:0,0")], size=(32, 32))
    finally:
        ro.chmod(0o755)


def test_render_shots_all_or_nothing_actor_resolution(tmp_path):
    lvl = _level(cube_room())
    shots = [parse_shot("at:0,0,0;rot:0,0"), parse_shot("at:0,0,0;look:@Nope")]
    with pytest.raises(pn.NativePreviewError, match="actor not found: Nope"):
        pn.render_shots(level=lvl, shots=shots, out_dir=tmp_path, size=(32, 32), index=IDX)
    assert not list(tmp_path.glob("*.png"))      # nothing written


# --------------------------------------------------------------- pixel probe (§9)


def test_pixel_probe_marker_quad_lands_at_oracle_pixel():
    """Place a small marker at a known world point, render, and assert the ORACLE-projected
    pixel is hit (guards the projection + the Python-side camera basis end to end)."""
    room = cube_room("Room", 1024, 512)
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


# --------------------------------------------------------- solve_world_surfaces (parity engine)


def _solve(actors, monkeypatch=None):
    return pn.solve_world_surfaces(actors, IDX)


def test_solve_carves_room_shows_interior_add_and_hides_buried_add():
    """The parity engine: a subtracted room keeps its interior walls, an add INSIDE it survives
    where it borders empty, and an add BURIED in solid space (outside the subtraction) leaves no
    surface at all — the containment result a per-brush cull cannot produce."""
    room = make_brush_actor("Room", cube(1024, 1024, 1024), location=(0, 0, 0), csg="subtract")
    inner = make_brush_actor("Inner", cube(256, 256, 256), location=(0, 0, 0), csg="add")
    buried = make_brush_actor("Buried", cube(128, 128, 128), location=(4000, 0, 0), csg="add")
    solved = _solve([room, inner, buried])
    by_actor: dict = {}
    for s in solved.world_surfaces:
        key = s.actor.name if s.actor is not None else None
        by_actor[key] = by_actor.get(key, 0) + 1
    assert by_actor == {"Room": 6, "Inner": 6}         # Buried absent — no surviving surface
    assert solved.mover_polys == []


def test_solve_routes_through_bspcsg_core(monkeypatch):
    """The solve MUST call `build_geometry_bspcsg`, never the default `build_geometry` — the default
    mis-renders overlapping subtracts (the exact geometry parity exists to show). Guards the core
    choice against a silent revert."""
    import uedcli_native
    calls: list = []
    real = uedcli_native.build_geometry_bspcsg
    monkeypatch.setattr(uedcli_native, "build_geometry_bspcsg",
                        lambda b: calls.append("bspcsg") or real(b))
    monkeypatch.setattr(uedcli_native, "build_geometry",
                        lambda b: pytest.fail("default core must not be called"))
    room = make_brush_actor("Room", cube(1024, 1024, 1024), csg="subtract")
    _solve([room])
    assert calls == ["bspcsg"]


def test_solve_world_verts_are_already_world_space():
    """A solved fragment's verts are world-space (offset by Location): a room built at a non-origin
    Location has fragments around that Location, with NO second local→world transform owed."""
    room = make_brush_actor("Room", cube(512, 512, 512), location=(1000, 2000, 3000),
                            csg="subtract")
    solved = _solve([room])
    xs = [float(p[0]) for s in solved.world_surfaces for p in s.world_verts]
    assert xs and min(xs) >= 700 and max(xs) <= 1300   # 1000 ± 256, never near the local origin


def test_solve_movers_excluded_from_csg_and_returned_separately():
    """A mover is not carved into the world (it never subtracts/adds), so the room solves as if the
    mover were absent; the mover comes back as a world-transformed overlay poly set."""
    room = make_brush_actor("Room", cube(1024, 1024, 1024), csg="subtract")
    door = make_brush_actor("Door", cube(128, 16, 256), location=(0, 512, 0),
                            mover_class="Engine.Mover")
    solved = _solve([room, door])
    assert {s.actor.name for s in solved.world_surfaces if s.actor} == {"Room"}
    assert {a.name for _v, a, _p in solved.mover_polys} == {"Door"}
