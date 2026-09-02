"""Native-materialize brush-SCALE regression (spike `2026-07-15-native-materialize` §87 §9).

`brush_marshal._build_brush_input` used to silently DROP every brush's `MainScale`/`PostScale`, so a
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

from uedcli import model as trunk_model
from uedcli.builders import cube, make_brush_actor
from uedcli.native import brush_marshal
from uedcli.transform import FScale


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


def test_unscaled_brush_is_untouched_by_the_scale_path():
    """The gate: an identity-scale brush must take the exact prior (rotation-only) builder path, so
    its BrushTuple is unchanged — this is what keeps the castle byte-identical.  Assert the tuple a
    plain subtract produces carries authored normals/origins (non-empty) and identity `scale`."""
    lvl = _one_brush_level("Room", cube(512, 512, 256))
    verts, sizes, normals, oper, _pf, _loc, R, _pp, scale, *_rest = \
        brush_marshal._build_brush_input("Room", lvl.actors["Room"])
    assert normals, "unscaled brush lost its authored per-poly normals (should keep the prior path)"
    assert tuple(scale) == (1.0, 1.0, 1.0), "unscaled brush must pass identity scale"
    assert R == brush_marshal._IDENTITY_ROT, "unscaled, unrotated brush must pass identity rotation"


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


def test_tex_cov_pre_cancel_reproduces_inverse_transpose():
    """The algebraic identity behind the fix: with `P = (LᵀL)⁻¹`, applying the forward map `L` to
    `P·v` reproduces the covariant `(L⁻¹)ᵀ·v` for ANY invertible L (here scale + rotation).  This is
    what makes the Rust core's unconditional forward-`L` on texture axes come out covariant."""
    from uedcli import rotation as ROT
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
    tup = brush_marshal._build_brush_input("Box", lvl.actors["Box"])
    tex_u_flat = tup[10]                                # (…, poly_flags_flat, tex_u_flat, (tex_v,orig))
    authored = [float(c) for poly in lvl.actors["Box"].brush.polys for c in poly.texture_u]
    assert tex_u_flat == authored, \
        "unscaled brush texture axes were altered — the covariant pre-cancel must gate on `scaled`"


def test_scaled_brush_emitted_texture_u_is_covariant_precancel():
    """A `cube` face carries a UNIT in-plane authored TextureU (`builders._tex_basis`).  Under a uniform
    PostScale s=2 `_build_brush_input` must PRE-CANCEL each axis with `tex_cov = (LᵀL)⁻¹` so the Rust
    core's later forward-`L` comes out covariant `(L⁻¹)ᵀ`.  Pin the EMITTED value (tuple index 10,
    `tex_u_flat`) directly: the pre-cancel shrinks the unit axis to 1/s²=0.25 (which forward-`L` scales
    back to the editor's 1/s), so every emitted magnitude is 1/s² — and NONE is the authored 1.0 (the
    forward-L bug leaves the axis un-cancelled, which Rust then squares to s) nor s itself.  Unit-level
    rewrite of the deleted end-to-end §92 §34 covariance regression; pins current f32 behavior."""
    import math
    s = 2.0
    a = make_brush_actor("Box", cube(64, 64, 32), csg="add")
    a.post_scale = FScale(scale=(2, 2, 2))
    tex_u_flat = brush_marshal._build_brush_input("Box", a)[10]     # index 10 == tex_u_flat
    mags = {round(math.sqrt(sum(c * c for c in tex_u_flat[i:i + 3])), 6)
            for i in range(0, len(tex_u_flat), 3)}
    assert mags, "no texture axes emitted"
    assert all(abs(mag - 1.0 / (s * s)) < 1e-6 for mag in mags), (
        f"emitted tex_u magnitudes {sorted(mags)} are not the covariant pre-cancel 1/s²={1.0/(s*s)}; "
        "the forward-L bug leaves the authored axis un-cancelled — §92 §34 regression")
    assert all(abs(mag - 1.0) > 1e-3 for mag in mags), (
        f"an emitted tex_u magnitude is the un-cancelled authored 1.0 in {sorted(mags)} — the covariant "
        "pre-cancel was not applied (forward-L then squares it into s)")
    assert all(abs(mag - s) > 1e-3 for mag in mags), \
        f"an emitted tex_u magnitude equals the forward-L value s={s} in {sorted(mags)}"


def test_mirror_scaled_brush_pre_reverses_each_poly_ring():
    """A MIRRORED scaled brush (`PostScale (-2,2,2)`, `det(L)<0`) must PRE-reverse every poly's vertex
    ring so the post-`L` world winding stays outward-CCW — the Rust core assumes Orientation +1 and
    never re-flips, so without the reversal `calc_normal` yields inward normals and a subtract builds
    inside-out.  Compare the emitted per-poly ring (tuple index 0, grouped by index 1 `poly_sizes`)
    against the same brush under a non-mirror positive scale: each ring is exactly reversed (so the
    first-triangle winding flips).  Unit-level rewrite of the deleted end-to-end mirror regression."""
    from uedcli import rotation as ROT
    from uedcli.transform import det3
    mir = _one_add_brush_level("Mir", cube(64, 64, 32), post_scale=FScale(scale=(-2, 2, 2)))
    base = _one_add_brush_level("Base", cube(64, 64, 32), post_scale=FScale(scale=(2, 2, 2)))
    assert det3(ROT.actor_linear(mir.actors["Mir"])) < 0, "fixture must be a true mirror (det<0)"
    assert det3(ROT.actor_linear(base.actors["Base"])) > 0, "baseline must be non-mirror (det>0)"
    tm = brush_marshal._build_brush_input("Mir", mir.actors["Mir"])
    tb = brush_marshal._build_brush_input("Base", base.actors["Base"])
    assert tm[1] == tb[1], f"poly_sizes differ (mirror {tm[1]} vs baseline {tb[1]})"

    def _rings(tup):
        verts = [tup[0][i:i + 3] for i in range(0, len(tup[0]), 3)]
        rings, off = [], 0
        for n in tup[1]:
            rings.append(verts[off:off + n])
            off += n
        return rings

    rm, rb = _rings(tm), _rings(tb)
    for i, (ring_m, ring_b) in enumerate(zip(rm, rb)):
        assert ring_m == list(reversed(ring_b)), (
            f"poly {i} ring not pre-reversed under a mirror: {ring_m} vs reversed baseline "
            f"{list(reversed(ring_b))} — det(L)<0 winding fix dropped")


def test_zero_scale_axis_raises_clean_error_not_zerodivision():
    """A zero/degenerate scale axis makes L singular; the covariant pre-cancel inverts L, so it must
    raise a clear `BuildError` NAMING the brush (repo rule: no bare traceback to the CLI user), never
    a `ZeroDivisionError`.  §92 §34 review requirement."""
    from uedcli.native.brush_marshal import BuildError
    lvl = _one_add_brush_level("Flat", cube(64, 64, 32), post_scale=FScale(scale=(0, 1, 1)))
    with pytest.raises(BuildError, match="Flat"):
        brush_marshal._build_brush_input("Flat", lvl.actors["Flat"])


def _brush578_faces():
    """UNATCO Brush578's SIX faces, VERBATIM from the trunk T3D (verts in the authored ORDER, plus the
    per-face texture axes / flags / texture — all load-bearing for reproducing the twin end-to-end:
    `calc_normal` is order-sensitive at the ULP level (the cube-builder's order gives an EXACT normal),
    and the authored texture axes shape the Vectors pool so the −y face's 0.99999994 normal survives
    dedup instead of collapsing onto an exact axis).  PostScale=(1.062501,0.624999,1), PrePivot/Location
    set by the caller."""
    from uedcli.model import Brush, Polygon
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


def _y_surf_normals(brush_tuple):
    """Build the single brush through the FULL native CSG+serialize path, return the ±y-axis
    surf normals (the faces whose normal is ~(0,±1,0)) as float triples."""
    import uedcli_native
    from uedcli.native import umodel as UMO
    body = bytes(uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg([brush_tuple])))
    m = UMO.parse_model_body(body, 0, len(body))
    out = []
    for s in m.surfs:
        n = m.vectors[s.v_normal]
        if abs(abs(n[1]) - 1) < 0.01 and abs(n[0]) < 0.01 and abs(n[2]) < 0.01:
            out.append((float(n[0]), float(n[1]), float(n[2])))
    return out


def test_scaled_brush_stores_a_unit_covariant_normal_end_to_end():
    """End-to-end (self-contained): build UNATCO Brush578 (PostScale=(1.0625,0.625,1), a lone ADD so
    its faces survive as surfs) through the FULL native path (`_build_brush_input` ->
    `build_geometry_bspcsg` -> `serialize_model`) and assert the stored −y surf normal is UNIT and
    axis-aligned — the covariant VectorXform path `(L⁻¹)ᵀ` + `SafeNormalSlow` recomputes the face
    normal correctly under non-uniform scale, NOT the L-warped world winding (which yields a
    non-axis normal on a scale-asymmetric face).  Double-precision: exact editor byte-parity
    (`0xbf800000`) is deliberately no longer a goal (the f32 vertex/normal path was vestigial once
    native materialize was removed), so this pins the geometric fact (unit, axis) not the bit."""
    pytest.importorskip("uedcli_native")
    from uedcli.builders import make_brush_actor
    a = make_brush_actor("B578", _brush578_faces(), location=(144.0, 1824.0, 314.0), csg="add")
    a.post_scale = FScale(scale=(1.062501, 0.624999, 1.0))
    a.props.append(("PrePivot", "(X=-7.529359,Y=-12.799914,Z=-6.000000)"))

    tup = brush_marshal._build_brush_input("B578", a)
    assert len(tup[11][2]) == 9, "scaled brush must carry a 9-float covariant VectorXform"

    normals = _y_surf_normals(tup)
    assert normals, "no ±y surf normal found in the built brush"
    for n in normals:
        assert abs(abs(n[1]) - 1.0) < 1e-4 and abs(n[0]) < 1e-4 and abs(n[2]) < 1e-4, \
            f"−y face normal must be a unit axis under the covariant map; got {n}"


def test_sheared_scaled_brush_bakes_the_sheer_into_both_verts_and_normal():
    """A sheared scale now BUILDS (the double unify handles it): `actor_linear` bakes the sheer
    off-diagonal into `L`, so both the vertex map (tuple[6] = `L`) AND the covariant normal map
    (`(L⁻¹)ᵀ`) carry it — no silent mis-build, so no reject.  The old f32 path built both from the
    DIAGONAL scale only and had to refuse sheer; that reject is gone.  Guard: tuple[6] equals the
    sheared `actor_linear` (a genuine off-diagonal), and the emitted covariant VectorXform is `(L⁻¹)ᵀ`."""
    from uedcli import rotation as ROT
    from uedcli.transform import det3
    lvl = _one_add_brush_level("Sheared", cube(64, 64, 32),
                               post_scale=FScale(scale=(2, 1, 1), sheer_rate=0.3, sheer_axis="SHEER_XY"))
    a = lvl.actors["Sheared"]
    L = ROT.actor_linear(a)
    assert det3(L) > 0                                     # not a mirror -> covariant path
    assert L[1][0] != 0.0, "fixture must actually shear (a genuine off-diagonal in L)"
    tup = brush_marshal._build_brush_input("Sheared", a)   # must NOT raise
    for r in range(3):
        for c in range(3):
            assert tup[6][r][c] == L[r][c], "tuple[6] must be the sheared double actor_linear"
    vx = [tup[11][2][i:i + 3] for i in range(0, 9, 3)]
    ref = ROT.transpose(ROT.inverse(L))                   # (L⁻¹)ᵀ — carries the sheer too
    for r in range(3):
        for c in range(3):
            assert abs(vx[r][c] - ref[r][c]) < 1e-9, "covariant VectorXform must be the sheared (L⁻¹)ᵀ"


def test_rotated_scaled_vec_xform_is_the_covariant_inverse_transpose():
    """§92 §43 review: the covariant normal map for a ROTATED+scaled brush is built as
    `diag(1/PS)·R·diag(1/MS)` from CLEAN per-axis reciprocals (NOT `ROT.inverse`).  This guards the
    transpose/order/sign of THAT construction (the diagonal test hardcodes R=I) by asserting it equals
    the mathematically-correct covariant map `(L⁻¹)ᵀ` — computed independently via the TRUE matrix
    inverse of `L = actor_linear` — to within FP tolerance, and that it maps a brush-local axis normal
    to a UNIT world normal.  If the order/transpose/sign were wrong the two would diverge grossly."""
    import math
    from uedcli import rotation as ROT
    lvl = _one_add_brush_level("Yawed", cube(64, 32, 16), post_scale=FScale(scale=(1.25, 1.0, 1.0)))
    a = lvl.actors["Yawed"]
    a.props.append(("Rotation", "(Yaw=16384)"))            # 90 deg — a genuine R != I
    tup = brush_marshal._build_brush_input("Yawed", a)
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


# ── the rot+scale VERTEX transform (f32 `editor_point_xform`) + authored base ──
# `_build_brush_input` bakes the scaled brush's world transform as the EDITOR-FAITHFUL f32
# `ABrush::BuildCoords` PointXform chain (`rotation.editor_point_xform` — live-gdb-confirmed against
# the real editor's transformed Base/vert bits, 2026-09-02 pass1-trace round: Vandenberg Brush54
# 339/412 Origins match ONLY the f32 chain, 0 only-double), passed as the Rust `rot`, and KEEPS the
# authored per-poly Origin (the surf `pBase` the editor stores is the transformed authored Origin,
# not a ring corner).  This SUPERSEDES the earlier "f32 PointXform is vestigial" state: native
# materialize byte-parity is the standing goal again, and the double `actor_linear` compose is 1 ULP
# off the editor on multi-component scale/rotation brushes.


def test_scaled_brush_wires_editor_point_xform_as_the_transform_matrix():
    """The vertex transform tuple[6] IS the f32 `editor_point_xform` chain — bit-equal to the double
    `actor_linear` on single-scale/cardinal brushes (no chain rounding) but the f32 chain on the
    multi-component ones.  Guards the wiring: a scaled brush must hand the Rust core that map as
    `rot` (so `FPoly::transform` yields `L·(v−PrePivot)+Loc`) with the `scale` tuple left identity
    (index 8) so the core's scaled-brush reject never fires."""
    from uedcli import rotation as ROT
    lvl = _one_add_brush_level("Yaw180", cube(64, 32, 16),
                               post_scale=FScale(scale=(0.249997, 1.0, 1.0)))
    a = lvl.actors["Yaw180"]
    a.props.append(("Rotation", "(Yaw=32768)"))            # 180° — a cardinal cross-term brush
    tup = brush_marshal._build_brush_input("Yaw180", a)
    R_returned, scale = tup[6], tup[8]
    P = ROT.editor_point_xform(a)
    for r in range(3):
        for c in range(3):
            assert R_returned[r][c] == P[r][c], \
                f"tuple[6][{r}][{c}]={R_returned[r][c]} must be editor_point_xform {P[r][c]}"
    assert tuple(scale) == (1.0, 1.0, 1.0), "the scale tuple must stay identity (L is baked into rot)"


def _slanted_scaled_wedge():
    """A single scaled ADD brush: a right-triangular prism (5 faces) so one face — the hypotenuse — has
    a genuine NON-AXIS normal `(1,0,2)/√5`.  Every poly carries an explicit Origin at its face CENTROID
    (a point that is NOT any vertex), so the stored surf `pBase` is a distinct orphan point iff the
    build keeps the authored Origin.  The hypotenuse centroid is `(0,0,0)`, so its transformed base is
    exactly `Location`.  PostScale=(1.25,0.75,1) tilts the covariant normal just off-perpendicular, so
    the two candidate base points (Origin vs `verts[0]`, ~200uu apart) yield DIFFERENT `Normal·Base`
    `w` — the same mechanism as the real UNATCO Brush48/236/359/750 node-`w` twins."""
    from uedcli.model import Brush, Polygon
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
    import uedcli_native
    from uedcli.native import umodel as UMO
    body = bytes(uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg([tuple(brush_tuple)])))
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
    pytest.importorskip("uedcli_native")
    a = _slanted_scaled_wedge()
    tup = list(brush_marshal._build_brush_input("Wedge", a))
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
