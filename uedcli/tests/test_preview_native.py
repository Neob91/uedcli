"""Offline tests for `preview_native` — the `--native` backend (spec §9). Everything runs
with no editor/container; tests that carve geometry need the `uedcli_native` extension
(skipped when absent, same as the CSG differential suite)."""
from __future__ import annotations

import glob
import hashlib
import math
import os
from decimal import Decimal
from pathlib import Path

import pytest

from uedcli import preview_native as pn
from uedcli.builders import cube, make_brush_actor
from uedcli.classindex import ClassIndex
from uedcli.model import Actor, Level
from uedcli.preview_shots import Shot, parse_shot
from uedcli.rotation import world_vertices
from uedcli.tests.conftest import StubClassIndex, cube_room, set_prop

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs

uedcli_native = pytest.importorskip("uedcli_native")

FIXTURES = Path(__file__).parent / "fixtures"

# Real ClassIndex over the committed UED22 corpus, needed ONLY by the DT_Mesh actor tests below —
# `StubClassIndex`/`IDX` above has no `.resolver()`/`.package_paths()`, so a real mesh-actor build
# (class defaults, `Mesh` decode, skin resolve) needs the same offline corpus `test_class_preview.py`
# uses, not the stub.
UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
MESH_CLASS = "DeusEx.CrateUnbreakableLarge"          # DT_Mesh; SAME class test_class_preview.py uses


def _ued22_index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def _mesh_sf(index) -> list[str]:
    """A realistic `search_files` for the mesh tests. Skins resolve over the FULL composed path, not
    the `.u`-only `package_paths` — in production that path is a superset of `package_paths`, and the
    corpus skins (e.g. `DeusExDeco.CrateUnbreakableLargeTex1`) live in these corpus `.u` files."""
    return list(index.package_paths())


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
    assert got == [([m.points[0], m.points[1], m.points[2]], 999, -1, 0)]
    # A hostile vert pool / point index never raises either — the node is skipped.
    m.nodes[0].i_vert_pool = 99
    assert pn._node_polys(m) == []
    m.nodes[0].i_vert_pool = 0
    m.verts[0].i_vertex = 12345
    assert pn._node_polys(m) == []


def test_out_of_range_join_does_not_crash_add_poly(monkeypatch):
    """Regression, user-visible half: an out-of-range `i_brush_poly` (valid `i_actor`, no source
    poly) still renders flat grey, never a traceback. This exercises `add_poly`'s `surf_flags`
    branch (every `_node_polys`-driven call site passes one), which was never the buggy path.

    The ACTUAL bug fixed alongside this — `add_poly`'s no-`surf_flags` FALLBACK derivation
    (`(poly.flags or 0) if poly is not None else 0`) used to read `poly.flags` unconditionally,
    crashing with `AttributeError` whenever `poly` was `None` — has no live caller today (every
    `_node_polys` call site passes `surf_flags`; the only caller that doesn't, `_mover_world_polys`,
    always has a real `actor`+`poly`). The fix is kept as defensive-correct code for any future
    caller that omits `surf_flags` with `poly=None`, but is not exercised by any current test."""
    room = cube_room()
    real_node_polys = pn._node_polys

    def hostile(model):
        out = real_node_polys(model)
        verts, i_actor, _i_brush_poly, poly_flags = out[0]
        return [(verts, i_actor, 99999, poly_flags)] + out[1:]

    monkeypatch.setattr(pn, "_node_polys", hostile)
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert len(polys) == 6   # the hostile node still renders (flat grey), no crash


# --------------------------------------------------------------- backface cull, end to end (§?)

_BACKGROUND_RGB = bytes([56, 56, 60])   # render.rs::BACKGROUND — not exported, pinned here


def test_backface_cull_end_to_end_through_the_full_pipeline():
    """The real regression this change fixes, through the WHOLE chain (`_node_polys` -> `add_poly`
    -> the Rust `light_in_front` cull): a lone additive box's geometric +X face (`polys[0]`) renders
    when viewed from the side its post-CSG normal actually points to, and renders BACKGROUND — not
    its own texture seen from the wrong side — from the opposite side. The CSG core's own winding
    for a lone add brush is measured, not assumed: `newell(polys[0])` gives -X (the face's front is
    the world-origin side, x<64, not the outward x>64 side a raw authored brush would have) — a
    real, if slightly surprising, fact about this specific CSG-solved case; this test locks it down
    with an assertion rather than silently relying on it."""
    import uedcli_native
    from uedcli.texframe import newell
    box = make_brush_actor("Box", cube(128.0, 128.0, 128.0), csg="add")
    polys, table = pn.build_scene(_level(box), [], IDX)
    assert len(polys) == 6
    verts_flat = polys[0][0]
    verts = [tuple(verts_flat[j:j + 3]) for j in range(0, len(verts_flat), 3)]
    assert all(v[0] == 64.0 for v in verts)          # polys[0] IS the geometric +X face
    assert newell(verts)[0] < 0                      # ...and its front faces -X (measured, not assumed)

    # Isolate this ONE face: with all 6 present, a ray through the culled near face legitimately
    # keeps going and hits the (correctly front-facing) OPPOSITE wall — a real result, not a
    # confound this test is about, but it would make an untextured grey "background" check
    # meaningless here (same default-grey shade either way).
    one_face = [polys[0]]

    def centre_px(eye_x: float, yaw: float) -> bytes:
        fwd, right, up = pn.camera_basis(0.0, yaw)
        buf = uedcli_native.render_frame(one_face, table, ((eye_x, 5.0, 5.0), fwd, right, up, 30.0),
                                         (64, 64))
        o = (32 * 64 + 32) * 3
        return bytes(buf[o:o + 3])

    assert centre_px(-500.0, 0.0) != _BACKGROUND_RGB    # -X side, looking +X: the front
    assert centre_px(200.0, 180.0) == _BACKGROUND_RGB   # +X side, looking -X: the back, now culled


# --------------------------------------------------------------- unresolvable texture → error


def test_unresolvable_ref_raises_named_error():
    """A whole-frame render REFUSES outright: no checkerboard, no partial image (spec §4.5
    revision, owner ruling) — one unreadable texture fails the whole `--native` shot.

    The error carries the decoder's named case, so a reader can tell a wrong ref from a
    layout we cannot decode yet without re-running anything.
    """
    room = cube_room(texture="Missing.Tex")
    with pytest.raises(pn.NativePreviewError, match=r"Missing\.Tex") as excinfo:
        pn.build_scene(_level(room), [], IDX)
    assert "unknown-package" in str(excinfo.value)   # the decoder's case, not a generic "missing"


def test_bare_ref_is_unresolvable():
    """A bare ref is refused by name — `unqualified-ref`, not "not found" — because the fix is
    to qualify it, not to go looking for the texture. Raises, same as any other unresolvable ref."""
    room = cube_room(texture="barename")
    with pytest.raises(pn.NativePreviewError, match=r"barename") as excinfo:
        pn.build_scene(_level(room), [], IDX)
    assert "unqualified-ref" in str(excinfo.value)


def test_undecodable_present_ref_raises_too():
    """The decode layer (a texture the ref DID resolve to, but whose data won't decode) raises
    exactly like the ref layer above — `index_for` doesn't distinguish the two `TextureError`
    layers, it raises on any of them."""
    class _Resolver:
        def resolve(self, ref):
            return pn.TextureError(ref, "corrupt-body", "mip 0 truncated")

    table = pn._TextureTable(_Resolver())
    with pytest.raises(pn.NativePreviewError, match=r"Real\.Tex") as excinfo:
        table.index_for("Real.Tex")
    assert "corrupt-body" in str(excinfo.value)


def test_real_fixture_texture_resolves():
    room = cube_room(texture="LUM_InfoPortraits.ArthurCallaway")
    polys, table = pn.build_scene(_level(room), [str(FIXTURES / "LUM_InfoPortraits.utx")], IDX)
    assert len(table) == 1
    w, h, _, mask = table[0]
    assert (w, h) == (64, 64)
    assert len(mask) == w * h                    # per-texel mask plumbed alongside RGB


def test_pf_masked_flag_plumbed_to_poly_tuple():
    """A face's PF_Masked bit reaches the render-poly tuple's `masked` field; a plain face is
    False. This is what tells the rasterizer to alpha-test the texture's mask for that face."""
    polys, _ = pn.build_scene(_level(cube_room()), [], IDX)
    assert polys and all(p[6] is False for p in polys)

    masked = cube_room()
    set_prop(masked, "PolyFlags", str(pn.PF_MASKED))
    polys, _ = pn.build_scene(_level(masked), [], IDX)
    assert polys and all(p[6] is True for p in polys)
    # The raw merged flags (8th element) carry PF_MASKED too — the same value the backface cull's
    # PF_TwoSided|PF_Portal exemption reads.
    assert polys and all(p[7] & pn.PF_MASKED for p in polys)


def test_bmasked_texture_masks_without_the_surface_flag():
    """`_TextureTable.is_bmasked` reports the texture's own `bMasked`, so `add_poly` masks a face
    whose TEXTURE is bMasked even with no `PF_Masked` surface flag — the engine ORs a texture's
    PolyFlags onto every surface it's applied to (`unrealed/quirks.md`). The no-texture (-1) slot is
    False."""
    from types import SimpleNamespace
    def _tex(b_masked):
        return SimpleNamespace(width=2, height=1, rgb=b"\xff\x00\x00\xff\x00\x00",
                               mask=b"\x01\x00", b_masked=b_masked)

    class _Resolver:
        def resolve(self, ref):
            return _tex(ref == "Masked.Tex")

    t = pn._TextureTable(_Resolver())
    assert t.is_bmasked(t.index_for("Masked.Tex")) is True
    assert t.is_bmasked(t.index_for("Plain.Tex")) is False
    assert t.is_bmasked(-1) is False


def test_bmasked_texture_masks_through_build_scene(monkeypatch):
    """END-TO-END: a face whose TEXTURE is bMasked masks (`p[6]` True) via `build_scene` even with no
    `PF_Masked` surface flag — this pins the deciding `or textures.is_bmasked(...)` in `add_poly`
    (dropping it makes every poly False, failing here)."""
    from types import SimpleNamespace

    class _Resolver:
        def __init__(self, *a, **k):
            pass

        def resolve(self, ref):
            return SimpleNamespace(width=2, height=1, rgb=b"\xff\x00\x00\xff\x00\x00",
                                   mask=b"\x01\x00", b_masked=True)

    monkeypatch.setattr(pn, "TextureResolver", _Resolver)
    room = cube_room(texture="Masked.Tex")               # bMasked texture, NO PolyFlags set
    polys, _ = pn.build_scene(_level(room), [], IDX)
    assert polys and all(p[6] is True for p in polys)


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
    puts it. The CSG core keys winding off ring order for its own carve, so the marshaller's
    pre-reverse is what keeps the carved solid right-side-out here — independent of whether the
    RENDERER also reads winding (it now does, via the backface cull, but that is a separate
    concern from this geometric correctness check)."""
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


# --------------------------------------------------------------- DT_Mesh actors (real corpus)


def test_build_scene_includes_a_dt_mesh_actor():
    """A DT_Mesh actor (`MESH_CLASS`, resolved through the real UED22 corpus — `StubClassIndex` can't
    resolve class defaults/mesh/skins) adds its frame-0 triangles on top of the world-CSG baseline.
    Room has no texture set, so its 6 baseline polys carry no ambiguity against the new textured mesh
    triangles; the room is rebuilt fresh for each call since `build_scene` is not asserted pure over
    its brush input."""
    index = _ued22_index()
    baseline_polys, baseline_textures = pn.build_scene(_level(cube_room()), [], index)
    assert baseline_polys and not baseline_textures      # untextured room: polys exist, no textures

    crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    polys, textures = pn.build_scene(_level(cube_room(), crate), _mesh_sf(index), index)

    assert polys[:len(baseline_polys)] == baseline_polys  # baseline untouched, mesh triangles appended
    new_polys = polys[len(baseline_polys):]
    assert new_polys                                       # the crate actually contributed triangles
    for verts_flat, *_ in new_polys:
        assert len(verts_flat) == 9    # exactly 3 verts * 3 floats -- one mesh triangle per RenderPoly
    assert textures                                         # the crate's skin decoded into the table


def _mesh_default(prop: str, index) -> str:
    """One class default of `MESH_CLASS`, read off the real corpus (its `Mesh` ref, for instance
    overrides that need a REAL mesh on a class that has none of its own)."""
    from uedcli import uprops
    return uprops.resolve_class_defaults(MESH_CLASS, resolver=index.resolver())[(prop, 0)]


def _mesh_poly_count(actor, index) -> int:
    """How many polys `actor` adds on top of the bare-room baseline."""
    baseline, _ = pn.build_scene(_level(cube_room()), [], index)
    polys, _ = pn.build_scene(_level(cube_room(), actor), _mesh_sf(index), index)
    return len(polys) - len(baseline)


def test_drawtype_instance_override_decides_what_renders():
    """`DrawType` resolves instance-override-else-class-default, like `Mesh` right beside it and like
    `cli/rendering.py::_resolve_point_render` — reading only the class default rendered a DT_None
    instance of a mesh class and skipped a DT_Mesh instance of a non-mesh class."""
    index = _ued22_index()
    off = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)),
                props=[("DrawType", "DT_None")])
    assert _mesh_poly_count(off, index) == 0

    on = Actor(name="Laser", cls="DeusEx.LaserEmitter",          # DT_None class, no Mesh default
               location=(Decimal(0), Decimal(0), Decimal(0)),
               props=[("DrawType", "DT_Mesh"), ("Mesh", _mesh_default("mesh", index))])
    assert _mesh_poly_count(on, index) > 0


def test_bhidden_mesh_actor_does_not_render():
    """`level photo` shows what the PLAYER sees, so a `bHidden` actor contributes nothing. (The
    editor flag `bHiddenEd` is `actor diagram`'s, and stays untouched here.)"""
    index = _ued22_index()
    hidden = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)),
                   props=[("bHidden", "True")])
    assert _mesh_poly_count(hidden, index) == 0
    shown = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    assert _mesh_poly_count(shown, index) > 0


def test_mesh_material_with_no_texture_renders_flat_grey(monkeypatch):
    """A material with NOTHING assigned is not a failure: the triangle still renders, in the flat
    default grey (`tex_index -1`) an untextured BSP face already gets. Only a texture that IS
    assigned and won't decode is an error, and `resolve_skins` raises that one by name."""
    from uedcli import meshrender
    index = _ued22_index()
    monkeypatch.setattr(meshrender, "resolve_skins", lambda *a, **k: {})   # no material textured
    baseline, _ = pn.build_scene(_level(cube_room()), [], index)
    crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    polys, textures = pn.build_scene(_level(cube_room(), crate), [], index)
    new_polys = polys[len(baseline):]
    assert new_polys                                     # the crate still contributed triangles
    assert all(p[5] == -1 for p in new_polys)            # ...all flat grey
    assert not textures                                  # nothing registered in the table


def test_mesh_skin_dedup_keys_on_class_and_mesh_ref():
    """`resolve_skins` is CLASS-dependent (a class's `MultiSkins`/`Skin` defaults override the
    mesh's own textures), so the skin cache key must carry the class AND the mesh asset ref. Two
    classes sharing one mesh with different skins used to collide on `(mesh.name, material)` and
    the second silently rendered the first's skin."""
    t = pn._TextureTable(resolver=None)                  # index_for_decoded never touches it
    px = b"\xff\x00\x00"
    mask = b"\x01"
    a = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask)
    assert t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask) == a
    # a DIFFERENT class over the SAME mesh gets its own slot (the C1 bug)
    assert t.index_for_decoded("DeusEx.CrateB", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask) != a
    # a same-NAMED mesh from another package is a different asset
    assert t.index_for_decoded("DeusEx.CrateA", ("OtherPkg", "Crate"), 0, 1, 1, px, False, mask) != a
    assert t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 1, 1, 1, px, False, mask) != a


def test_bmasked_mesh_skin_masks_without_the_triangle_flag(monkeypatch):
    """A `bMasked` mesh SKIN masks its triangles even with no `PF_Masked` triangle flag — the same
    rule a bMasked surface texture already gets (`unrealed/quirks.md`: the engine ORs a texture's
    PolyFlags onto every surface it is applied to). `resolve_skins` carries the flag out of the
    decode; `index_for_decoded` records it; `is_bmasked` reports it."""
    t = pn._TextureTable(resolver=None)
    px = b"\xff\x00\x00"
    mask = b"\x01"
    plain = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask)
    masked = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Grate"), 0, 1, 1, px, True, mask)
    assert t.is_bmasked(plain) is False and t.is_bmasked(masked) is True

    # END TO END: the flag reaches the render-poly tuple's `masked` field through build_scene.
    from uedcli import meshrender
    index = _ued22_index()
    monkeypatch.setattr(meshrender, "resolve_skins",   # the crate mesh has one material, index 0
                        lambda *a, **k: {0: (1, 1, px, True, mask)})
    baseline, _ = pn.build_scene(_level(cube_room()), [], index)
    crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    polys, _ = pn.build_scene(_level(cube_room(), crate), [], index)
    new_polys = polys[len(baseline):]
    assert new_polys and all(p[6] is True for p in new_polys)
    assert all(not (p[7] & pn.PF_MASKED) for p in new_polys)   # ...with NO triangle flag set


def test_mesh_skin_carries_the_real_per_texel_mask_not_synthesized_opaque(monkeypatch):
    """`index_for_decoded` used to synthesize an ALL-OPAQUE mask (`b"\\x01" * (w*h)`) regardless of
    the skin's real alpha data, so the rasterizer's `masked && mask[texel] == 0` test never cut
    anything — a bMasked mesh skin (e.g. `Plant`, `SecurityCamera`'s lens) rendered as a solid
    opaque block instead of being alpha-tested. The table entry must carry the texture's OWN
    decoded mask (with at least one transparent texel) verbatim, matching what `index_for` already
    does for world/mover textures (`got.mask`)."""
    t = pn._TextureTable(resolver=None)
    px = b"\xff\x00\x00\xff\x00\x00"
    real_mask = b"\x01\x00"                               # texel 1 is transparent -- NOT all-opaque
    idx = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 2, 1, px, True, real_mask)
    w, h, rgb, mask = t.table[idx]
    assert mask == real_mask
    assert mask != b"\x01" * (w * h)                      # the old synthesized-opaque bug

    # END TO END: resolve_skins' decoded mask reaches the texture table through build_scene.
    from uedcli import meshrender
    index = _ued22_index()
    px1 = b"\xff\x00\x00"
    real_mask2 = b"\x00"                                   # one texel, fully transparent
    monkeypatch.setattr(meshrender, "resolve_skins",       # the crate mesh has one material, index 0
                        lambda *a, **k: {0: (1, 1, px1, True, real_mask2)})
    _polys, table = pn.build_scene(
        _level(cube_room(), Actor(name="Crate", cls=MESH_CLASS,
                                   location=(Decimal(0), Decimal(0), Decimal(0)))),
        [], index)
    assert table and table[-1][3] == real_mask2


def test_index_for_decoded_actor_override_gets_its_own_slot():
    """`actor_override` extends the dedup key (board `per-actor-skins-override-in-native-mesh-render`):
    the SAME class/mesh/material with the SAME (empty) override still dedupes exactly as before
    (this fix must not touch the common no-override case), but a DIFFERENT override fingerprint
    gets its own slot — the reopened C1-shaped bug this pins."""
    t = pn._TextureTable(resolver=None)
    px = b"\xff\x00\x00"
    mask = b"\x01"
    a = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask)
    # no override on either call (the default) -> same slot, same as before this fix
    assert t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask) == a
    # an actor that overrides its own skin must NOT collide with one that doesn't
    override = (("multiskins", 0), "Texture'Other.Pkg.Skin'")
    b = t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask,
                            actor_override=(override,))
    assert b != a
    # the SAME override fingerprint still dedupes (two actors overriding to the identical skin)
    assert t.index_for_decoded("DeusEx.CrateA", ("DeusExDeco", "Crate"), 0, 1, 1, px, False, mask,
                               actor_override=(override,)) == b


def test_two_instances_of_one_mesh_class_share_one_texture_slot():
    """The dedup the class key must NOT break: two placed actors of the SAME class and mesh still
    register one texture-table entry per material, not one per actor."""
    index = _ued22_index()
    one = Actor(name="Crate1", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    two = Actor(name="Crate2", cls=MESH_CLASS, location=(Decimal(200), Decimal(0), Decimal(0)))
    _p1, t1 = pn.build_scene(_level(cube_room(), one), _mesh_sf(index), index)
    _p2, t2 = pn.build_scene(_level(cube_room(), one, two), _mesh_sf(index), index)
    assert t1 and len(t2) == len(t1)


def test_actor_own_skin_override_renders_over_the_mesh_default_not_the_class():
    """A placed actor's own `MultiSkins(N)=` beats what it would otherwise render with — the actual
    fix (board `per-actor-skins-override-in-native-mesh-render`). `MESH_CLASS` has no class-level
    `MultiSkins`/`Skin` default at all (verified: every slot is `None` in the real corpus), so its
    material 0 comes from the MESH's own texture (`DeusExDeco.Skins.CrateUnbreakableLargeTex1`,
    tier 3) today — the actor override (tier 1) must win over that."""
    index = _ued22_index()
    sf = [str(FIXTURES / "LUM_InfoPortraits.utx"), *_mesh_sf(index)]
    plain = Actor(name="Crate1", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    overridden = Actor(name="Crate2", cls=MESH_CLASS, location=(Decimal(200), Decimal(0), Decimal(0)),
                       props=[("MultiSkins(0)", "Texture'LUM_InfoPortraits.ArthurCallaway'")])
    _p1, t1 = pn.build_scene(_level(cube_room(), plain), sf, index)
    _p2, t2 = pn.build_scene(_level(cube_room(), overridden), sf, index)
    assert (t1[0][0], t1[0][1]) != (64, 64)            # the mesh's own crate texture, NOT 64x64
    assert (t2[0][0], t2[0][1]) == (64, 64)            # LUM_InfoPortraits.ArthurCallaway's real size


def test_two_actors_one_overriding_get_distinct_skins_not_a_cache_collision():
    """The cache-collision regression the fix's Bug 2 closes: two placed actors of the SAME class
    and mesh, only one overriding its own skin, must NOT share a texture-table slot — sharing one
    would silently render the non-overriding actor with the OTHER actor's overridden skin (the same
    failure `_TextureTable.index_for_decoded`'s own docstring already names for the class-blind
    case, reopened one layer up by making skins actor-dependent)."""
    index = _ued22_index()
    sf = [str(FIXTURES / "LUM_InfoPortraits.utx"), *_mesh_sf(index)]
    plain = Actor(name="Crate1", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    overridden = Actor(name="Crate2", cls=MESH_CLASS, location=(Decimal(200), Decimal(0), Decimal(0)),
                       props=[("MultiSkins(0)", "Texture'LUM_InfoPortraits.ArthurCallaway'")])
    polys, table = pn.build_scene(_level(cube_room(), plain, overridden), sf, index)
    sizes = {(w, h) for (w, h, *_rest) in table}
    assert (64, 64) in sizes                                    # the override's texture is present
    assert len(sizes) >= 2                                      # AND distinct from the mesh default
    # every triangle's tex_index must point at a table entry of the RIGHT size for its owning actor —
    # not silently reused from the other actor's slot.
    tex_sizes = {p[5]: (table[p[5]][0], table[p[5]][1]) for p in polys if p[5] != -1}
    assert (64, 64) in tex_sizes.values()
    assert any(sz != (64, 64) for sz in tex_sizes.values())


def test_mesh_skins_resolve_over_full_search_files_not_u_only(monkeypatch):
    """Regression: a mesh skin can live in a `.utx` (`Effects.BioCell_SFX`), never on the `.u`-only
    `index.package_paths()`. `build_scene` must hand `resolve_skins` the FULL `search_files` — passing
    `package_paths` raised "no package named 'Effects' on the composed search path" for any deco whose
    skin is a `.utx` texture."""
    from uedcli import meshrender
    index = _ued22_index()
    seen: dict = {}

    def spy(mesh, pkg, defaults, search_files, *, class_fqcn, class_index=None):
        seen["sf"] = search_files
        return {}

    monkeypatch.setattr(meshrender, "resolve_skins", spy)
    sf = ["/nonexistent/Effects.utx", *index.package_paths()]      # a `.utx` NOT on the `.u` set
    crate = Actor(name="Crate", cls=MESH_CLASS, location=(Decimal(0), Decimal(0), Decimal(0)))
    pn.build_scene(_level(cube_room(), crate), sf, index)
    assert seen["sf"] == sf                                        # full path forwarded verbatim
    assert seen["sf"] != list(index.package_paths())              # NOT the `.u`-only set


def test_build_scene_unresolvable_mesh_ref_raises_naming_the_actor():
    """The actor's own `Mesh=` override points at a package not on the search path — a REALISTIC
    "mesh not on the search path" scenario writes a syntactically well-formed ref
    (`LodMesh'Pkg.Name'`), which `parse_mesh_ref` parses fine; the failure surfaces one level down,
    inside `meshfacts.decode_mesh` (package not found), converted to `NativePreviewError` by
    `_mesh_actor_polys`'s `except meshfacts.MeshFactError` branch — NOT the `ref is None` branch (a
    bare unquoted string like "NoSuchPackage.Bogus" fails to parse at all and is not how a real T3D
    Mesh override reads)."""
    index = _ued22_index()
    crate = Actor(name="Crate", cls=MESH_CLASS,
                  location=(Decimal(0), Decimal(0), Decimal(0)),
                  props=[("Mesh", "LodMesh'NoSuchPackage.Bogus'")])
    lvl = _level(cube_room(), crate)
    with pytest.raises(pn.NativePreviewError, match=r"NoSuchPackage\.Bogus"):
        pn.build_scene(lvl, [], index)


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
    # marker quad: 8uu square centred at (200, 60, -40), wound to face the camera at origin
    # (yaw=0 -> forward=+X; the ring must wind so its Newell normal points back toward -X).
    cx, cy, cz = 200.0, 60.0, -40.0
    quad = ([cx, cy - 4, cz + 4, cx, cy + 4, cz + 4, cx, cy + 4, cz - 4, cx, cy - 4, cz - 4],
            [cx, cy, cz], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [0.0, 0.0], 0, False, 0)
    red = (1, 1, bytes([255, 0, 0]), bytes([1]))
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


def _synthetic_scene(monkeypatch, tmp_path=None):
    """Case-c level with a synthetic asymmetric 4-texel texture injected straight into the
    table (no package file needed): an unresolvable ref now raises instead of degrading, so the
    resolver is patched to hand back a 1x1 placeholder, then the table is patched with the real
    asymmetric pixels."""
    from types import SimpleNamespace
    monkeypatch.setattr(pn.TextureResolver, "resolve",
                        lambda self, ref: SimpleNamespace(width=1, height=1, rgb=b"\x00\x00\x00",
                                                          mask=b"\x01", b_masked=False))
    lvl = _case_c_level()
    polys, table = pn.build_scene(lvl, [], IDX)
    asym = (2, 2, bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]), bytes([1, 1, 1, 1]))
    table = [asym if i == 0 else t for i, t in enumerate(table)]
    return polys, table


def test_golden_image_byte_exact(monkeypatch):
    """Two exact-trig poses (0°/90°) at 320×240, byte-exact pixel buffers on the dev
    platform (Linux/x86_64 — spike 40). On mismatch prints the differing-byte count.
    Bless/regenerate: UEDCLI_BLESS_GOLDEN=1 bin/test -k golden. Blessed 2026-07-16 AFTER
    the anchor verdict (U/V/Pan pinned against the live editor + game references —
    dev/docs/spikes/2026-07-16-native-preview-anchor/).
    RE-BLESSED 2026-07-20 after the GMath trig-table fix (§92 §41): `camera_basis` now reads the
    editor-EXACT float32 GMath table, so the 90°-yaw pose uses cos(90°) = −8.742278e-08 (the game's
    own value) instead of double 0. The 0° frame stays BYTE-IDENTICAL; the 90° frame's face-side flips
    are what the GAME renders (the game builds its camera from the same table), so the golden tracks it.
    Cross-reviewed defensible; the anchor U/V/Pan pins are unaffected (texture math, not camera trig).
    RE-BLESSED 2026-08-24 after `build_scene` switched to the faithful `build_geometry_bspcsg` core
    (board `native-preview-drops-large-geometry-on-full`). The core change alters case c's fragment
    tessellation (coarse 18 nodes/12 surfs → bspcsg 16/10), so the pixel buffer moves; the case-c
    surf SET still matches the editor golden (`test_csg_native_differential`), and the anchor U/V/Pan
    + camera-trig pins are unaffected (only the CSG core feeding fragments changed)."""
    import uedcli_native
    polys, table = _synthetic_scene(monkeypatch)
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
