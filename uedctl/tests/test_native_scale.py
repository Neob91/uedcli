"""Native-materialize brush-SCALE regression (spike `2026-07-15-native-materialize` §87 §9).

`materialize._build_brush_input` used to silently DROP every brush's `MainScale`/`PostScale`, so a
scaled brush built at UNIT size.  On real DX levels a scaled-up SUBTRACT then carved a tiny hole
instead of the full room, leaving the room interior SOLID — native over-solidified the editor's open
void (HK `[A]` 74.5 %, UNATCO 15.3 %; `shatter_probe.py`).  The fix bakes the full linear map
`L = PostScale·R·MainScale` into the world transform handed to the Rust core, gated on non-identity
scale (so unscaled brushes — the ENTIRE castle — stay byte-identical).

The real-level probes (HK/UNATCO/Catacombs `[A]` collapse) run out of gitignored `_scratch/` trunks
and cannot be committed; the castle differential provably HIDES this whole bug class because the
castle has ZERO scaled brushes.  So this module pins the fix with a self-contained SYNTHETIC
differential: a scaled-up subtract must carve the SAME world room as the equivalent explicit-size
subtract.  If scale is ever dropped again, the scaled build carves only the unit hole and the
interior probe points read SOLID where the explicit build reads OPEN -> these asserts go red.
"""
import pytest

from uedctl import model as trunk_model
from uedctl.builders import cube, make_brush_actor
from uedctl.native import materialize
from uedctl.transform import FScale

from uedctl.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


def _one_brush_level(name, brush, *, location=(0.0, 0.0, 0.0), post_scale=None, main_scale=None):
    """A single-subtract-brush trunk `Level`, optionally with a non-identity MainScale/PostScale."""
    lvl = trunk_model.Level()
    a = make_brush_actor(name, brush, location=location, csg="subtract")
    if post_scale is not None:
        a.post_scale = post_scale
    if main_scale is not None:
        a.main_scale = main_scale
    lvl.actors[name] = a
    lvl.order.append(name)
    return lvl


# Points DEEP inside the intended 512x512x256 world room (|x|,|y|<256, |z|<128) but OUTSIDE the
# 64x64x32 unit brush (|x|,|y|>32, |z|>16) — so each reads OPEN iff scale was applied, SOLID iff
# scale was dropped.  (A point inside the unit hole, e.g. the origin, reads OPEN either way and would
# catch nothing, so all probes are deliberately outside it.)
_INTERIOR = [(200.0, 200.0, 100.0), (-200.0, -200.0, -100.0),
             (200.0, -200.0, 100.0), (-200.0, 200.0, -100.0)]
# Points OUTSIDE the 512x512x256 room on every side — SOLID in a correct build (the subtract
# stops at ±256/±128); if scale over-applied these would wrongly read OPEN.
_EXTERIOR = [(400.0, 0.0, 0.0), (-400.0, 0.0, 0.0), (0.0, 400.0, 0.0),
             (0.0, -400.0, 0.0), (0.0, 0.0, 300.0), (0.0, 0.0, -300.0)]


def test_postscale_subtract_carves_full_room_like_explicit():
    """A `cube(64,64,32)` subtract with PostScale (8,8,8) carves the same 512x512x256 world room as
    an explicit `cube(512,512,256)` subtract: identical solidity at every interior + exterior probe,
    and the same surf count.  Scale-drop regression catcher (the whole §87 §9 bug class)."""
    pytest.importorskip("uedctl_native")
    scaled = _one_brush_level("Room", cube(64, 64, 32),
                              post_scale=FScale(scale=(8, 8, 8)))
    explicit = _one_brush_level("Room", cube(512, 512, 256))
    m_scaled, *_ = materialize._build_level_model(scaled, index=IDX, bake_light=False)
    m_explicit, *_ = materialize._build_level_model(explicit, index=IDX, bake_light=False)

    for p in _INTERIOR:
        zs = materialize._model_point_zone(m_scaled, p)
        ze = materialize._model_point_zone(m_explicit, p)
        assert zs > 0, (f"interior {p} reads SOLID in the scaled build (zone {zs}) — brush scale "
                        "was DROPPED (§87 §9); the scaled-up subtract carved only the unit hole")
        assert ze > 0, f"explicit build interior {p} unexpectedly SOLID (zone {ze})"

    for p in _EXTERIOR:
        assert materialize._model_point_zone(m_scaled, p) == 0, \
            f"exterior {p} reads OPEN in the scaled build — scale over-carved"
        assert materialize._model_point_zone(m_explicit, p) == 0, \
            f"exterior {p} reads OPEN in the explicit build"

    assert len(m_scaled.surfs) == len(m_explicit.surfs), (
        f"scaled build has {len(m_scaled.surfs)} surfs vs explicit {len(m_explicit.surfs)} — a "
        "correctly-scaled box carves the identical 6-face room")


def test_mainscale_matches_postscale_for_axis_aligned_box():
    """MainScale (LOCAL/pre-rotation) and PostScale (WORLD/post-rotation) coincide for an
    axis-aligned box with no rotation — both must carve the full room (pins that `actor_linear`'s
    MainScale leg is honoured too, not only PostScale)."""
    pytest.importorskip("uedctl_native")
    main = _one_brush_level("Room", cube(64, 64, 32), main_scale=FScale(scale=(8, 8, 8)))
    m_main, *_ = materialize._build_level_model(main, index=IDX, bake_light=False)
    for p in _INTERIOR:
        assert materialize._model_point_zone(m_main, p) > 0, \
            f"interior {p} SOLID under MainScale — the MainScale leg of actor_linear was dropped"
    for p in _EXTERIOR:
        assert materialize._model_point_zone(m_main, p) == 0, f"exterior {p} OPEN under MainScale"


def test_mirror_scale_subtract_carves_room_not_inside_out():
    """A MIRRORED subtract (`PostScale (-8,8,8)`, `det(L) < 0`) must carve the room the RIGHT way
    round, not build inside-out.  The mirror inverts winding orientation; the Rust core assumes
    Orientation +1 and never re-flips, so `_build_brush_input` must PRE-reverse the ring (as
    `transform.bake` does on `det3(L) < 0`).  Without that reversal `calc_normal` yields inward
    normals and the interior reads SOLID.  Regression for the mirror-scale case (HK has ~30 such
    brushes) flagged by the cold-review gate."""
    pytest.importorskip("uedctl_native")
    from uedctl.transform import det3
    from uedctl import rotation as ROT
    lvl = _one_brush_level("Room", cube(64, 64, 32), post_scale=FScale(scale=(-8, 8, 8)))
    assert det3(ROT.actor_linear(lvl.actors["Room"])) < 0, "fixture must be a true mirror (det<0)"
    m, *_ = materialize._build_level_model(lvl, index=IDX, bake_light=False)
    # A mirror of a symmetric centred cube keeps the same 512x512x256 extents, so the SAME probes
    # apply: interior OPEN (carved right-side-out), exterior SOLID.
    for p in _INTERIOR:
        assert materialize._model_point_zone(m, p) > 0, (
            f"interior {p} SOLID under a MIRROR subtract — winding not reversed for det(L)<0, so the "
            "subtract built inside-out")
    for p in _EXTERIOR:
        assert materialize._model_point_zone(m, p) == 0, f"exterior {p} OPEN under a mirror subtract"


def test_unscaled_brush_is_untouched_by_the_scale_path():
    """The gate: an identity-scale brush must take the exact prior (rotation-only) builder path, so
    its BrushTuple is unchanged — this is what keeps the castle byte-identical.  Assert the tuple a
    plain subtract produces carries authored normals/origins (non-empty) and identity `scale`."""
    lvl = _one_brush_level("Room", cube(512, 512, 256))
    verts, sizes, normals, oper, _pf, _loc, R, _pp, scale, *_rest = \
        materialize._build_brush_input("Room", lvl.actors["Room"])
    assert normals, "unscaled brush lost its authored per-poly normals (should keep the prior path)"
    assert tuple(scale) == (1.0, 1.0, 1.0), "unscaled brush must pass identity scale"
    assert R == materialize._IDENTITY_ROT, "unscaled, unrotated brush must pass identity rotation"


# ── §92 §34: texture axes are COVECTORS — covariant `(L⁻¹)ᵀ`, not forward-`L` ──────────────────
# The Rust core transforms a poly's TextureU/TextureV by the SAME forward map `L` it applies to
# verts, but texture axes must transform by the inverse-transpose `(L⁻¹)ᵀ`.  Under scale, forward-`L`
# SQUARED the scale into the axis magnitude and over-produced 146 UNATCO Vectors (native 745 vs
# golden 599).  `_build_brush_input` now PRE-CANCELS with `P = (LᵀL)⁻¹` so the core's forward-`L`
# comes out covariant.  These pin the fix (silently coupled to Rust applying forward-`L`).

def _one_add_brush_level(name, brush, *, post_scale=None, main_scale=None):
    """A single-ADD-brush trunk `Level` (add so the build emits the brush's 6 faces as surfs)."""
    lvl = trunk_model.Level()
    a = make_brush_actor(name, brush, csg="add")
    if post_scale is not None:
        a.post_scale = post_scale
    if main_scale is not None:
        a.main_scale = main_scale
    lvl.actors[name] = a
    lvl.order.append(name)
    return lvl


def _texu_magnitudes(model):
    import math
    return {round(math.sqrt(sum(c * c for c in model.vectors[su.v_texture_u])), 4)
            for su in model.surfs if su.v_texture_u >= 0}


def test_scaled_brush_texture_axis_is_covariant():
    """A `cube` face carries a UNIT in-plane TextureU (`builders._tex_basis`).  Under a uniform
    PostScale s=2 the emitted world texture axis must SHRINK by 1/s (covariant `(L⁻¹)ᵀ`), so every
    surf's vTextureU has magnitude 1/2 — and NONE has magnitude 2 (the pre-fix forward-L value that
    squared the scale into the axis).  §92 §34 end-to-end regression through the Rust core."""
    pytest.importorskip("uedctl_native")
    s = 2.0
    lvl = _one_add_brush_level("Box", cube(64, 64, 32), post_scale=FScale(scale=(2, 2, 2)))
    m, *_ = materialize._build_level_model(lvl, index=IDX, bake_light=False)
    mags = _texu_magnitudes(m)
    assert mags, "no textured surfs emitted"
    assert all(abs(mag - 1.0 / s) < 1e-3 for mag in mags), (
        f"scaled-brush texture-U magnitudes {sorted(mags)} are not covariant 1/s={1.0/s}; the "
        "forward-L bug gives s=2 (squared scale into the axis) — §92 §34 regression")
    assert all(abs(mag - s) > 1e-2 for mag in mags), (
        f"a texture-U magnitude equals the forward-L value s={s} in {sorted(mags)} — the covariant "
        "pre-cancel was not applied")


def test_tex_cov_pre_cancel_reproduces_inverse_transpose():
    """The algebraic identity behind the fix: with `P = (LᵀL)⁻¹`, applying the forward map `L` to
    `P·v` reproduces the covariant `(L⁻¹)ᵀ·v` for ANY invertible L (here scale + rotation).  This is
    what makes the Rust core's unconditional forward-`L` on texture axes come out covariant."""
    from uedctl import rotation as ROT
    a = make_brush_actor("X", cube(8, 8, 8))
    a.main_scale = FScale(scale=(2, 1, 4))
    a.post_scale = FScale(scale=(1, 3, 1))
    a.props.append(("Rotation", "(Yaw=8192)"))
    L = ROT.actor_linear(a)
    Linv = ROT.inverse(L)
    P = ROT.matmul(Linv, ROT.transpose(Linv))          # (LᵀL)⁻¹ — the pre-cancel matrix
    NT = ROT.transpose(Linv)                            # (L⁻¹)ᵀ — the editor's covariant map
    for v in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.3, -0.7, 0.2)]:
        got = ROT.matvec(L, ROT.matvec(P, v))          # core's forward-L on the pre-cancelled axis
        want = ROT.matvec(NT, v)                        # editor's covariant axis
        assert all(abs(float(got[i]) - float(want[i])) < 1e-6 for i in range(3)), (v, got, want)


def test_unscaled_brush_texture_axes_pass_through_unchanged():
    """The gate on the covariant pre-cancel: an UNSCALED brush (`tex_cov` stays None) must emit its
    authored TextureU byte-unchanged — this is what keeps the castle (0 scaled brushes) byte-identical
    after §92 §34.  The emitted `tex_u_flat` must equal the actor's authored per-poly TextureU."""
    lvl = _one_add_brush_level("Box", cube(64, 64, 32))
    tup = materialize._build_brush_input("Box", lvl.actors["Box"])
    tex_u_flat = tup[10]                                # (…, poly_flags_flat, tex_u_flat, (tex_v,orig))
    authored = [float(c) for poly in lvl.actors["Box"].brush.polys for c in poly.texture_u]
    assert tex_u_flat == authored, \
        "unscaled brush texture axes were altered — the covariant pre-cancel must gate on `scaled`"


def test_zero_scale_axis_raises_clean_error_not_zerodivision():
    """A zero/degenerate scale axis makes L singular; the covariant pre-cancel inverts L, so it must
    raise a clear `BuildError` NAMING the brush (repo rule: no bare traceback to the CLI user), never
    a `ZeroDivisionError`.  §92 §34 review requirement."""
    from uedctl.native.materialize import BuildError
    lvl = _one_add_brush_level("Flat", cube(64, 64, 32), post_scale=FScale(scale=(0, 1, 1)))
    with pytest.raises(BuildError, match="Flat"):
        materialize._build_brush_input("Flat", lvl.actors["Flat"])


def _brush578_faces():
    """UNATCO Brush578's SIX faces, VERBATIM from the trunk T3D (verts in the authored ORDER, plus the
    per-face texture axes / flags / texture — all load-bearing for reproducing the twin end-to-end:
    `calc_normal` is order-sensitive at the ULP level (the cube-builder's order gives an EXACT normal),
    and the authored texture axes shape the Vectors pool so the −y face's 0.99999994 normal survives
    dedup instead of collapsing onto an exact axis).  PostScale=(1.062501,0.624999,1), PrePivot/Location
    set by the caller."""
    from uedctl.model import Brush, Polygon
    # (normal, verts, tex_u, tex_v, flags, texture)
    faces = [
        ((0, 0, 1), [(-128, -192, 80), (128, -192, 80), (128, 192, 80), (-128, 192, 80)],
         (1.062501, 0, 0), (0, 0.624999, 0), 8388608, "UNATCO.UN_Wall_Blue"),
        ((0, 0, -1), [(-128, 192, -80), (128, 192, -80), (128, -192, -80), (-128, -192, -80)],
         (1.062501, 0, 0), (0, 0.624999, 0), 8388608, "CoreTexTextile.ClenGrayCarpt_C"),
        ((0, 1, 0), [(-128, 192, -80), (-128, 192, 80), (128, 192, 80), (128, 192, -80)],
         (1.634617, 0, 0), (0, 0, -1.538462), 8388608, "CoreTexWallObj.GrayWoodTWall_C"),
        ((0, -1, 0), [(128, -192, -80), (128, -192, 80), (-128, -192, 80), (-128, -192, -80)],
         (-0.819672, 0, 0), (0, 0, -0.819672), 0, None),
        ((1, 0, 0), [(128, 192, -80), (128, 192, 80), (128, -192, 80), (128, -192, -80)],
         (0, -0.961537, 0), (0, 0, -1.538462), 8388608, "CoreTexWallObj.GrayWoodTWall_C"),
        ((-1, 0, 0), [(-128, -192, -80), (-128, -192, 80), (-128, 192, 80), (-128, 192, -80)],
         (0, 0.961537, 0), (0, 0, -1.538462), 8388608, "CoreTexWallObj.GrayWoodTWall_C"),
    ]
    b = Brush(model_name="Model")
    for n, vs, tu, tv, fl, tx in faces:
        b.polys.append(Polygon(flags=fl, texture=tx, normal=tuple(float(c) for c in n),
                               texture_u=tuple(float(c) for c in tu),
                               texture_v=tuple(float(c) for c in tv),
                               vertices=[tuple(float(c) for c in v) for v in vs]))
    return b


def _y_surf_normal_bits(brush_tuple):
    """Build the single brush through the FULL native CSG+serialize path, return the set of ±y-axis
    surf-normal `.y` bit patterns (the faces whose normal is ~(0,±1,0))."""
    import struct
    import uedctl_native
    from uedctl.native import umodel as UMO
    body = bytes(uedctl_native.serialize_model(uedctl_native.build_geometry_bspcsg([brush_tuple])))
    m = UMO.parse_model_body(body, 0, len(body))
    out = set()
    for s in m.surfs:
        n = m.vectors[s.v_normal]
        if abs(abs(n[1]) - 1) < 0.01 and abs(n[0]) < 0.01 and abs(n[2]) < 0.01:
            out.add(struct.unpack("<I", struct.pack("<f", float(n[1])))[0])
    return out


def test_scaled_brush_stored_normal_bits_match_editor_end_to_end():
    """§92 §43 review (end-to-end, self-contained): build UNATCO Brush578 (PostScale=(1.0625,0.625,1),
    a lone ADD so its faces survive as surfs with NO axis vector to dedup against) through the FULL
    native path (`_build_brush_input` -> `build_geometry_bspcsg` -> `serialize_model`) and assert the
    STORED −y surf-normal bit == the editor's gdb-dumped `0xbf800000` (EXACT unit; golden30 node 359).
    The DISCRIMINATOR: with the covariant VectorXform path REMOVED (vec_xform stripped -> the old
    `calc_normal(world)` path) the same build stores `0xbf7fffff` (the 0.99999994 twin) — asserted
    below — so this test goes RED if the fix is reverted or the covariant normal is wrong."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.builders import make_brush_actor
    a = make_brush_actor("B578", _brush578_faces(), location=(144.0, 1824.0, 314.0), csg="add")
    a.post_scale = FScale(scale=(1.062501, 0.624999, 1.0))
    a.props.append(("PrePivot", "(X=-7.529359,Y=-12.799914,Z=-6.000000)"))
    trunk_model.Level()  # (no level object needed; _build_brush_input takes the actor directly)

    tup = list(materialize._build_brush_input("B578", a))
    assert len(tup[11][2]) == 9, "scaled brush must carry a 9-float covariant VectorXform"

    cov_bits = _y_surf_normal_bits(tuple(tup))
    assert 0xbf80_0000 in cov_bits, \
        f"covariant path must STORE the editor's exact-unit -y normal 0xbf800000; got {[hex(b) for b in cov_bits]}"

    # Remove the covariant map -> the old calc_normal(world) path -> the 0.99999994 twin (0xbf7fffff).
    stripped = list(tup)
    t = list(stripped[11]); t[2] = []; stripped[11] = tuple(t)
    calc_bits = _y_surf_normal_bits(tuple(stripped))
    assert 0xbf7f_ffff in calc_bits and 0xbf80_0000 not in calc_bits, \
        f"calc_normal(world) path IS the twin (0xbf7fffff), != editor 0xbf800000; got {[hex(b) for b in calc_bits]}"


def test_sheared_scaled_brush_raises_clear_error_not_silent_misbuild():
    """§92 §43 review: the covariant face-normal map `(L⁻¹)ᵀ` is built from the DIAGONAL scale only,
    but a non-zero `SheerRate` is baked into `L` by `actor_linear` (`fscale_matrix` adds the
    off-diagonal).  A sheared SCALED brush would therefore get sheared VERTS (via `L`) but an
    un-sheared NORMAL (via the diagonal covariant) — a silent mis-build.  No DX brush uses sheer, so
    `_build_brush_input` must raise a clear `BuildError` NAMING the brush, never mis-build silently."""
    from uedctl.native.materialize import BuildError
    lvl = _one_add_brush_level("Sheared", cube(64, 64, 32),
                               post_scale=FScale(scale=(2, 1, 1), sheer_rate=0.3, sheer_axis="SHEER_XY"))
    with pytest.raises(BuildError, match="Sheared"):
        materialize._build_brush_input("Sheared", lvl.actors["Sheared"])


def test_rotated_scaled_vec_xform_is_the_covariant_inverse_transpose():
    """§92 §43 review: the covariant normal map for a ROTATED+scaled brush is built as
    `diag(1/PS)·R·diag(1/MS)` from CLEAN per-axis reciprocals (NOT `ROT.inverse`).  This guards the
    transpose/order/sign of THAT construction (the diagonal test hardcodes R=I) by asserting it equals
    the mathematically-correct covariant map `(L⁻¹)ᵀ` — computed independently via the TRUE matrix
    inverse of `L = actor_linear` — to within FP tolerance, and that it maps a brush-local axis normal
    to a UNIT world normal.  If the order/transpose/sign were wrong the two would diverge grossly."""
    import math
    from uedctl import rotation as ROT
    lvl = _one_add_brush_level("Yawed", cube(64, 32, 16), post_scale=FScale(scale=(1.25, 1.0, 1.0)))
    a = lvl.actors["Yawed"]
    a.props.append(("Rotation", "(Yaw=16384)"))            # 90 deg — a genuine R != I
    tup = materialize._build_brush_input("Yawed", a)
    vec_xform_flat = tup[11][2]
    assert len(vec_xform_flat) == 9, "a rotated+scaled brush must emit a 9-float VectorXform"
    vx = [vec_xform_flat[r * 3:r * 3 + 3] for r in range(3)]
    # Independent reference: (L⁻¹)ᵀ via the TRUE inverse of the full linear part.
    L = ROT.actor_linear(a)
    ref = ROT.transpose(ROT.inverse(L))
    for r in range(3):
        for c in range(3):
            assert abs(vx[r][c] - ref[r][c]) < 1e-5, \
                f"vec_xform[{r}][{c}]={vx[r][c]} != (L⁻¹)ᵀ ref {ref[r][c]} — wrong transpose/order/sign"
    # And a local axis normal, covariant-mapped THEN renormalized (as the Rust `SafeNormalSlow` does),
    # must point along the L-rotated axis: yaw=90° carries local +x -> world +y.  ((L⁻¹)ᵀ·n is NOT unit
    # pre-normalization — a covector scales by 1/PS — so normalize before checking direction.)
    w = ROT.matvec(vx, (1.0, 0.0, 0.0))
    mag = math.sqrt(w[0] ** 2 + w[1] ** 2 + w[2] ** 2)
    wn = [c / mag for c in w]
    assert abs(wn[1] - 1.0) < 1e-4 and abs(wn[0]) < 1e-4 and abs(wn[2]) < 1e-4, \
        f"local +x normal must covariant-map to world +y under yaw=90; got {wn}"


# ── §92 §45: the rot+scale VERTEX precision lever — editor f32 `FCoords` PointXform + authored base ──
# `_build_brush_input` used to compose the scaled brush's world transform via `rotation.actor_linear`'s
# Python-DOUBLE matmul, and DROP the authored per-poly Origin (base := verts[0]).  Both cost the
# rot+scale committed-tree byte-parity.  The editor builds `PointXform` as an f32 `FCoords` chain
# `((UnitCoords·PostScale)·Rotation)·MainScale` (ABrush::BuildCoords, Engine.dll 0x111390): it multiplies
# by the f32-cast `FVector Scale` (and rounds per FCoords op), where the double matmul multiplies by the
# raw double scale — so the tiny cardinal cross-term `sin(180°)=8.74e-8` times PostScale lands 1 ULP off.
# EVERY DX rot+scale brush has MainScale=identity, so the f32-cast of the scale INPUT is the whole effect
# there (the genuine intermediate second rounding bites only when PS and MS both cross the same off-axis;
# unexercised by DX but reproduced for the general case).  Plus the surf `pBase` the editor stores is the
# TRANSFORMED authored Origin, not a ring corner.  Together these closed all 8 UNATCO N=105 scaled-brush
# vertex/`w` twins (Brush48/236/359/750) and the L-composition twins at N=762 (Brush541/348) — the
# committed incremental tree is otherwise STRUCTURALLY IDENTICAL to the editor's (1637/1637 nodes
# index-for-index on iF/iB/iP/isurf/nv; only precision-twin planes).


def test_pointxform_f32_scale_input_f32_cast_matches_editor_not_double_matmul():
    """The editor's f32-cast `FVector Scale` input vs `actor_linear`'s raw-double scale (§92 §45 review).
    Yaw=180° (cardinal) makes `R[0][1] = -sin(180°) = 8.742278e-08`; under `PostScale.x=0.249997` (and
    MainScale=identity, as EVERY DX rot+scale brush) the element `L[0][1] = f32(f32(PS_x)·R[0][1])` =
    `0x32bbbc9b` — the EXACT bit an UnrealEd gdb `Model->Nodes` dump stores for the real UNATCO Brush541
    (idx 464), because the editor stores `PostScale` as f32.  `actor_linear` multiplies by the RAW double
    `0.249997` and rounds once to `0x32bbbc9a` (1 ULP low — the vertex twin).  With MS=identity the
    'second' f32 stage is a no-op, so THIS case isolates the scale-input f32 cast; the two-stage rounding
    is pinned separately below.  If the fix drops the input f32 cast this flips to `0x32bbbc9a`."""
    import struct
    from uedctl import rotation as ROT
    lvl = _one_add_brush_level("Yaw180", cube(64, 32, 16),
                               post_scale=FScale(scale=(0.249997, 1.0, 1.0)))
    a = lvl.actors["Yaw180"]
    a.props.append(("Rotation", "(Yaw=32768)"))            # 180° — a cardinal cross-term brush
    L = materialize._pointxform_f32(a)

    def bits(x):
        return struct.unpack("<I", struct.pack("<f", float(x)))[0]

    assert bits(L[0][1]) == 0x32bbbc9b, \
        f"PointXform L[0][1] must be the editor's f32-scale bit 0x32bbbc9b; got {bits(L[0][1]):#010x}"
    # And guard the DIRECTION: the old double matmul (raw-double scale) rounds to the twin 0x32bbbc9a.
    Ld = ROT.actor_linear(a)
    assert bits(Ld[0][1]) == 0x32bbbc9a, \
        "actor_linear double matmul is the twin path (0x32bbbc9a); the fix must NOT use it for the vertex R"
    assert bits(L[0][1]) != bits(Ld[0][1]), "the f32 op-order must differ from the double matmul here"

    # C2 (§92 §45 review): guard the WIRING — `_build_brush_input` must actually RETURN the f32 pointxform
    # as the transform matrix (tuple index 6), not the double `L`.  Reverting line 581 back to `L` would
    # leave the math test above green but this red.
    R_returned = materialize._build_brush_input("Yaw180", a)[6]
    assert [[bits(R_returned[r][c]) for c in range(3)] for r in range(3)] \
        == [[bits(L[r][c]) for c in range(3)] for r in range(3)], \
        "_build_brush_input must wire _pointxform_f32 into the transform matrix (tuple[6]), not double L"


def test_pointxform_genuine_two_stage_rounding_when_both_scales_cross_axis():
    """Pin the GENUINE intermediate rounding (§92 §45 review C1): when PostScale AND MainScale are both
    non-unit on the SAME crossed off-axis, `f32(f32(PS·R)·MS)` differs from a single-rounded `f32(PS·R·MS)`.
    Unexercised by DX (all MS=identity) but the editor's FCoords chain rounds per-op, so `_pointxform_f32`
    must too.  Constructed so the two-stage result and the single-rounded product diverge by 1 ULP.

    NOTE: this is a CHANGE-DETECTOR (it re-derives the SUT's own `f32(f32(PS·R)·MS)` expectation), not an
    independent oracle — its job is to catch a silent regression to single-rounding.  The independent,
    editor-anchored pin is `test_pointxform_f32_scale_input_f32_cast_matches_editor_not_double_matmul`
    (bit `0x32bbbc9b` from an UnrealEd gdb dump)."""
    import struct
    from uedctl import rotation as ROT

    def bits(x):
        return struct.unpack("<I", struct.pack("<f", float(x)))[0]

    def f32(x):
        return struct.unpack("f", struct.pack("f", float(x)))[0]

    # Search a few PS/MS pairs on the crossed (x-row, y-col) axis for a case where per-op two-stage f32
    # rounding differs from the single-rounded triple product (the cardinal cross-term R[0][1]).
    r01 = -ROT.gmath_sin(32768)                             # -sin(180°) = 8.742278e-08 (GMath table)
    found = None
    for ps in (0.249997, 0.6, 1.3, 1.7, 2.1, 0.9375):
        for ms in (0.6, 1.3, 1.7, 2.1, 3.0, 0.75):
            two = f32(f32(f32(ps) * f32(r01)) * f32(ms))
            one = f32(f32(ps) * f32(r01) * f32(ms))         # single-rounded triple product
            if bits(two) != bits(one):
                found = (ps, ms, two, one)
                break
        if found:
            break
    assert found is not None, "expected some PS/MS pair to expose the two-stage rounding"
    ps, ms, two, one = found
    lvl = _one_add_brush_level("Cross", cube(64, 32, 16),
                               post_scale=FScale(scale=(ps, 1.0, 1.0)),
                               main_scale=FScale(scale=(1.0, ms, 1.0)))
    a = lvl.actors["Cross"]
    a.props.append(("Rotation", "(Yaw=32768)"))
    L = materialize._pointxform_f32(a)
    assert bits(L[0][1]) == bits(two), \
        f"pointxform must round per-op (two-stage) -> {bits(two):#010x}; got {bits(L[0][1]):#010x}"
    assert bits(L[0][1]) != bits(one), \
        "two-stage per-op rounding must differ from a single-rounded triple product for this PS/MS pair"


def _slanted_scaled_wedge():
    """A single scaled ADD brush: a right-triangular prism (5 faces) so one face — the hypotenuse — has
    a genuine NON-AXIS normal `(1,0,2)/√5`.  Every poly carries an explicit Origin at its face CENTROID
    (a point that is NOT any vertex), so the stored surf `pBase` is a distinct orphan point iff the
    build keeps the authored Origin.  The hypotenuse centroid is `(0,0,0)`, so its transformed base is
    exactly `Location`.  PostScale=(1.25,0.75,1) tilts the covariant normal just off-perpendicular, so
    the two candidate base points (Origin vs `verts[0]`, ~200uu apart) yield DIFFERENT `Normal·Base`
    `w` — the same mechanism as the real UNATCO Brush48/236/359/750 node-`w` twins."""
    from uedctl.model import Brush, Polygon
    e = 96.0
    V0 = (-e, -e, -e); V1 = (e, -e, -e); V2 = (-e, -e, e)
    V3 = (-e, e, -e);  V4 = (e, e, -e);  V5 = (-e, e, e)
    root5 = 5.0 ** 0.5
    faces = [((0, 0, -1), [V0, V1, V4, V3]), ((-1, 0, 0), [V0, V3, V5, V2]),
             ((0, -1, 0), [V0, V2, V1]),     ((0, 1, 0), [V3, V4, V5]),
             ((1 / root5, 0, 2 / root5), [V1, V4, V5, V2])]           # hypotenuse — non-axis normal

    def cen(vs):
        return tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))
    b = Brush(model_name="Model")
    for n, vs in faces:
        b.polys.append(Polygon(flags=0, texture=None, normal=tuple(float(c) for c in n),
                               texture_u=(1.0, 0.0, 0.0), texture_v=(0.0, 1.0, 0.0),
                               vertices=[tuple(float(c) for c in v) for v in vs],
                               origin=tuple(float(c) for c in cen(vs))))
    a = make_brush_actor("Wedge", b, location=(-272.0, 576.0, 240.0), csg="add")
    a.post_scale = FScale(scale=(1.25, 0.75, 1.0))
    return a


def _slanted_node_base_and_w(brush_tuple):
    """Build the wedge end-to-end and return `(w_bits, pBase_point, face_world_verts)` for the ONE node
    whose plane normal is non-axis (the hypotenuse)."""
    import struct
    import uedctl_native
    from uedctl.native import umodel as UMO
    body = bytes(uedctl_native.serialize_model(uedctl_native.build_geometry_bspcsg([tuple(brush_tuple)])))
    m = UMO.parse_model_body(body, 0, len(body))
    for n in m.nodes:
        nx, ny, nz = n.plane[0], n.plane[1], n.plane[2]
        if abs(nx) > 0.1 and abs(nz) > 0.1 and abs(ny) < 0.05:
            s = m.surfs[n.i_surf]
            pbase = tuple(m.points[s.p_base])
            fverts = [tuple(m.points[m.verts[n.i_vert_pool + k].i_vertex]) for k in range(n.num_vertices)]
            return struct.unpack("<I", struct.pack("<f", float(n.plane[3])))[0], pbase, fverts
    raise AssertionError("no non-axis (hypotenuse) node found in the built wedge")


def test_scaled_brush_stores_authored_origin_as_pbase_end_to_end():
    """§92 §45 review (load-bearing pin, end-to-end): a SCALED brush must store the TRANSFORMED authored
    Origin as the surf `pBase` (exactly as the editor's `FPoly::Transform` maps `Base`), NOT `verts[0]`.
    Build a scaled wedge through the FULL native path and assert, for its non-axis (hypotenuse) face:
      (1) `pBase` == the transformed authored Origin `(-272,576,240)` (= Location; centroid is origin),
          and is FAR from every ring vertex (it is the orphan base, not a corner); and
      (2) dropping the Origin (base := `verts[0]`) MOVES the node-plane `w` bits — the covariant non-axis
          normal makes `w = Normal·Base` base-point-dependent (the exact mechanism of the 8 UNATCO N=105
          scaled-brush `w` twins the fix closed).
    This goes RED if `_build_brush_input` reverts to dropping the scaled brush's Origin (`base := verts[0]`)."""
    pytest.importorskip("uedctl_native")
    a = _slanted_scaled_wedge()
    tup = list(materialize._build_brush_input("Wedge", a))
    assert len(tup[11][1]) == 3 * 5, "a scaled brush must forward all authored per-poly Origins"

    w_keep, pbase_keep, fverts = _slanted_node_base_and_w(tup)
    # (1) pBase is the transformed authored Origin (Location), a distinct orphan point (far from corners).
    assert all(abs(pbase_keep[i] - (-272.0, 576.0, 240.0)[i]) < 1e-3 for i in range(3)), \
        f"scaled-face pBase must be the transformed authored Origin (-272,576,240); got {pbase_keep}"
    min_corner_dist = min(sum((pbase_keep[i] - v[i]) ** 2 for i in range(3)) ** 0.5 for v in fverts)
    assert min_corner_dist > 50.0, \
        f"pBase must be the orphan Origin, NOT a ring corner; nearest vertex is {min_corner_dist:.1f}uu away"

    # (2) Strip the Origins -> base := verts[0]; the non-axis normal makes `w` shift (load-bearing).
    stripped = list(tup)
    t = list(stripped[11]); t[1] = []; stripped[11] = tuple(t)
    w_strip, pbase_strip, _ = _slanted_node_base_and_w(stripped)
    assert any(abs(pbase_strip[i] - fverts[0][i]) < 1e-3 for i in range(3)) or pbase_strip != pbase_keep, \
        "with Origins stripped the base must fall back to a ring vertex, not the orphan Origin"
    assert w_keep != w_strip, \
        (f"the authored-Origin base must MOVE the node-plane w for a non-axis normal "
         f"(kept {w_keep:#010x} vs stripped {w_strip:#010x}); if equal, the pBase fix is not load-bearing here")
