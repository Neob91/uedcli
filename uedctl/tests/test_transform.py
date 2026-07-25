"""Offline tests for scale/sheer/apply-transform (spec 2026-07-18-scale-support §8).

Covers: the FScale parse/emit byte-match + de-dup, the forward transform for every combo
(MainScale/PostScale/rotation/PrePivot/sheer/mirror + compositions), the inverse round-trip
`world_to_local(local_to_world(v)) == v`, the bake → PolyList + winding reversal + field reset,
texture-lock under mirror+shear (its own cases), and the guards. Editor-parity of the exact
combined scale+sheer geometry is the `-m integration` differential harness (test below, deselected
by default) — these assert the offline contract + the single-effect cases the live spike pinned.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from uedctl import emit, rotation as R, transform as T
from uedctl.builders import cube, make_brush_actor
from uedctl.model import Actor, Brush, Polygon, parse_t3d

D = Decimal


# ── parse / emit ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "(SheerAxis=SHEER_ZX)",                                            # identity
    "(Scale=(X=2.000000),SheerAxis=SHEER_ZX)",                        # single axis
    "(Scale=(X=2.000000,Y=2.000000,Z=2.000000),SheerAxis=SHEER_ZX)",  # uniform
    "(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)",                       # mirror
    "(Scale=(X=2.000000,Y=0.500000),SheerRate=0.300000,SheerAxis=SHEER_YZ)",
    "(SheerRate=0.250000,SheerAxis=SHEER_XY)",                        # sheer only, no scale
])
def test_fscale_emission_byte_matches_the_editor(text):
    # Every string here is a verbatim editor MAP EXPORT readback (spike §1) — parse→emit must be a
    # byte-identical round trip or H3 post-verify fails on every authored-scale brush.
    assert T.emit_fscale(T.parse_fscale(text)) == text


def test_fscale_parse_defaults():
    fs = T.parse_fscale("(SheerAxis=SHEER_ZX)")
    assert fs.scale == (D(1), D(1), D(1)) and fs.sheer_rate == D(0) and fs.is_identity()


def test_identity_emits_the_shear_axis_default():
    assert T.emit_fscale(T.IDENTITY) == "(SheerAxis=SHEER_ZX)"


# ── emission de-dup (spec §10): typed fields, never a props copy ────────────────────────────────

def test_scale_is_pulled_out_of_props_and_not_double_emitted():
    src = ("Begin Map\nBegin Actor Class=Engine.Brush Name=B\n"
           "    MainScale=(Scale=(X=2.000000),SheerAxis=SHEER_ZX)\n"
           "    PostScale=(SheerAxis=SHEER_ZX)\n"
           "    Location=(X=100.000000)\n"
           "End Actor\nEnd Map\n")
    a = parse_t3d(src).actors["B"]
    # parsed OUT of props into the typed fields
    assert not any(k in ("MainScale", "PostScale") for k, _ in a.props)
    assert a.main_scale.scale[0] == D(2) and a.post_scale.is_identity()
    out = emit.emit_actor(a)
    assert out.count("MainScale=") == 1 and out.count("PostScale=") == 1
    assert "MainScale=(Scale=(X=2.000000),SheerAxis=SHEER_ZX)" in out


def test_builder_brush_emits_identity_scale_from_the_typed_field():
    a = make_brush_actor("C", cube(64, 64, 64))
    assert a.main_scale is T.IDENTITY and a.post_scale is T.IDENTITY
    out = emit.emit_actor(a)
    assert out.count("MainScale=(SheerAxis=SHEER_ZX)") == 1
    assert out.count("PostScale=(SheerAxis=SHEER_ZX)") == 1


def test_point_actor_emits_no_scale_lines():
    a = Actor(name="L", cls="Engine.Light", props=[("bStatic", "True")], location=(D(1), D(2), D(3)))
    out = emit.emit_actor(a)
    assert "MainScale" not in out and "PostScale" not in out


# ── forward transform (spike-verified single effects) ───────────────────────────────────────────

def _cube_actor(main=None, post=None, rot=None, prepivot=None, loc=(0, 0, 0)):
    a = make_brush_actor("C", cube(128, 64, 32), location=tuple(D(c) for c in loc))
    if main is not None:
        a.main_scale = main
    if post is not None:
        a.post_scale = post
    if rot is not None:
        a.props = [(k, v) for k, v in a.props if k != "Rotation"] + [("Rotation", rot)]
    if prepivot is not None:
        a.props += [("PrePivot", prepivot)]
    return a


def test_mainscale_doubles_the_named_local_axis():
    a = _cube_actor(main=T.FScale((D(2), D(1), D(1))))
    xs = sorted({round(w[0], 3) for w in R.world_vertices(a)})
    assert xs == [-128.0, 128.0]                      # half-extent 64 → ±128 after ×2


def test_mainscale_is_pre_rotation_postscale_is_post_rotation():
    # Test B/C of the spike: MainScale X=2 + Yaw90 lands the doubled axis on world Y; PostScale on X.
    main = _cube_actor(main=T.FScale((D(2), D(1), D(1))), rot="(Yaw=16384)")
    post = _cube_actor(post=T.FScale((D(2), D(1), D(1))), rot="(Yaw=16384)")
    def extent(a, i):
        cs = [w[i] for w in R.world_vertices(a)]
        return round(max(cs) - min(cs))
    # unrotated local extents: X=128, Y=64. Yaw90 swaps X<->Y. MainScale(x2 local X) => world Y=256.
    assert extent(main, 1) == 256 and extent(main, 0) == 64
    # PostScale(x2 world X) after the swap => world X doubled from the swapped-in Y (64)=128.
    assert extent(post, 0) == 128


def test_mirror_negates_and_flips_determinant():
    a = _cube_actor(main=T.FScale((D(-1), D(1), D(1))))
    xs = sorted({round(w[0], 3) for w in R.world_vertices(a)})
    assert xs == [-64.0, 64.0]                        # reflected, same extent
    assert T.det3(R.actor_linear(a)) < 0


def test_sheer_offdiagonal_matches_the_live_scan():
    # SHEER_XY rate r: Y_new = Y + f(r)·X (spike §3 table). Cube half-X=1024, base half-Y=32.
    for rate, k in [(D("0.10"), 0.05), (D("0.50"), 0.45), (D("0.60"), 0.50), (D("0.70"), 0.55)]:
        a = make_brush_actor("S", cube(2048, 64, 64))
        a.main_scale = T.FScale((D(1), D(1), D(1)), rate, "SHEER_XY")
        wv = R.world_vertices(a)
        plus_x = [w for w in wv if round(w[0]) == 1024]
        assert plus_x, rate
        assert round(max(w[1] for w in plus_x)) == round(32 + k * 1024), (rate, k)


# ── inverse round-trip (any invertible L) ────────────────────────────────────────────────────────

@pytest.mark.parametrize("kw", [
    {"main": T.FScale((D(2), D("0.5"), D(3)))},
    {"post": T.FScale((D("1.5"), D(2), D(1)))},
    {"main": T.FScale((D(2), D(1), D(1))), "post": T.FScale((D(1), D(3), D(1)))},
    {"main": T.FScale((D(2), D(1), D(1))), "rot": "(Yaw=8192,Pitch=4096)"},
    {"main": T.FScale((D(-1), D(2), D(1))), "rot": "(Yaw=16384)", "prepivot": "(X=16.000000)"},
    {"main": T.FScale((D(2), D(1), D(1)), D("0.3"), "SHEER_XY")},
])
def test_world_to_local_round_trips(kw):
    a = _cube_actor(loc=(50, -20, 10), **kw)
    for w in R.world_vertices(a):
        local = R.world_to_local_point(a, w)
        L = R.actor_linear(a)
        pp = R.actor_prepivot(a)
        loc = a.location
        off = R.matvec(L, tuple(float(local[i] - pp[i]) for i in range(3)))
        back = tuple(off[i] + float(loc[i]) for i in range(3))
        assert all(abs(back[i] - w[i]) < 1e-3 for i in range(3)), (kw, w, back)


def test_world_to_local_normal_is_the_transpose_pullback():
    # A world plane x+y=c under diag(2,1,1) has LOCAL normal (2,1,0) (2·lx + ly = c) — transpose(L).
    a = _cube_actor(main=T.FScale((D(2), D(1), D(1))))
    n = R.world_to_local_normal(a, (1.0, 1.0, 0.0))
    assert abs(n[0] - 2.0) < 1e-9 and abs(n[1] - 1.0) < 1e-9 and abs(n[2]) < 1e-9


def test_unscaled_unrotated_keeps_the_none_fast_path():
    a = make_brush_actor("C", cube(64, 64, 64))
    assert R.actor_linear(a) is None                  # identity sentinel preserved


# ── bake (apply-transform) ───────────────────────────────────────────────────────────────────────

def test_bake_folds_scale_and_resets_fields():
    a = _cube_actor(main=T.FScale((D(2), D(1), D(1))), loc=(100, 0, 0), prepivot="(X=16.000000)")
    before = sorted({round(w[0], 3) for w in R.world_vertices(a)})
    baked = T.bake(a)
    assert baked.main_scale.is_identity() and baked.post_scale.is_identity()
    assert not any(k == "Rotation" for k, _ in baked.props)
    # world geometry is preserved by the bake (v'=L·v, PrePivot'=L·PrePivot, Location kept)
    assert sorted({round(w[0], 3) for w in R.world_vertices(baked)}) == before
    # PrePivot rewritten to L·PrePivot = 2·16 = 32
    pp = R.actor_prepivot(baked)
    assert pp[0] == D(32)


def test_bake_reverses_winding_on_negative_determinant():
    from uedctl.emit import clean
    from uedctl.geometry import validate_brush
    a = _cube_actor(main=T.FScale((D(-1), D(1), D(1))))
    L = R.actor_linear(a)
    orig = [list(p.vertices) for p in a.brush.polys]
    baked = T.bake(a)
    assert T.det3(L) < 0                               # precondition: a real reflection
    for before, poly in zip(orig, baked.brush.polys):
        # winding reversed: baked ring == L·(reversed original ring)
        expect = [tuple(clean(c) for c in R.matvec(L, tuple(float(x) for x in v)))
                  for v in reversed(before)]
        assert [tuple(v) for v in poly.vertices] == expect
    validate_brush(baked.brush)                        # not inside-out → CSG-valid


def test_bake_folds_main_and_post_scale_together():
    # Both non-identity + rotation (the composition-order case where bugs hide, spec §8): the bake
    # must preserve world geometry through L = PostScale·R·MainScale.
    a = _cube_actor(main=T.FScale((D(2), D(1), D(1))), post=T.FScale((D(1), D(3), D(1))),
                    rot="(Yaw=8192)", loc=(20, -10, 5))
    before = {tuple(round(c, 3) for c in w) for w in R.world_vertices(a)}
    baked = T.bake(a)
    assert baked.main_scale.is_identity() and baked.post_scale.is_identity()
    after = {tuple(round(c, 3) for c in w) for w in R.world_vertices(baked)}
    assert before == after


def test_bake_rotation_only_bakes_rotation():
    a = _cube_actor(rot="(Yaw=16384)")                # 90° yaw, no scale
    before = {tuple(round(c, 3) for c in w) for w in R.world_vertices(a)}
    baked = T.bake(a)
    # The field is RESET TO AN EXPLICIT ZERO, not deleted: an omitted `Rotation` re-imports as the
    # CLASS DEFAULT (non-zero for `TNM.LavaSpitter`), which would rotate the just-flattened geometry
    # a second time. 2026-07-25 — same rule as the `PrePivot` reset beside it.
    assert ("Rotation", "(Pitch=0,Yaw=0,Roll=0)") in baked.props
    after = {tuple(round(c, 3) for c in w) for w in R.world_vertices(baked)}
    assert before == after


def test_bake_does_not_invent_a_rotation_for_an_actor_that_had_none():
    """The reset only rewrites a field the actor actually carried. Adding `(Pitch=0,Yaw=0,Roll=0)`
    to an actor that never had one would CHANGE its orientation on a class whose default rotation
    is non-zero — the mirror image of the bug the reset fixes."""
    a = _cube_actor()                                 # no Rotation prop at all
    a.main_scale = T.FScale((D(2), D(2), D(2)))       # a real transform, so the bake does work
    baked = T.bake(a)
    assert not any(k == "Rotation" for k, _ in baked.props)


# ── texture lock (its own corpus — the hardest parity surface, §10) ──────────────────────────────

def _textured_poly() -> Polygon:
    p = Polygon()
    p.origin = (10.0, 0.0, 0.0)
    p.texture_u = (1.0, 0.0, 0.0)
    p.texture_v = (0.0, 1.0, 0.0)
    p.vertices = [(D(0), D(0), D(0)), (D(0), D(64), D(0)), (D(64), D(64), D(0)), (D(64), D(0), D(0))]
    return p


def _one_poly_actor(fs: T.FScale) -> Actor:
    a = Actor(name="T", cls="Engine.Brush", location=(D(0), D(0), D(0)),
              brush=Brush(model_name="M", polys=[_textured_poly()]), main_scale=fs)
    return a


def test_texture_lock_on_transforms_axes_by_inverse_transpose_under_mirror():
    # Texture axes are covectors → they bake by (L⁻¹)ᵀ (glued texture), NOT L. Under mirror X +
    # scale Y (diag(-1,2,1)): (L⁻¹)ᵀ = diag(-1, 0.5, 1). Origin (a POINT) bakes by L.
    a = _one_poly_actor(T.FScale((D(-1), D(2), D(1))))
    baked = T.bake(a, lock_textures=True)
    p = baked.brush.polys[0]
    assert p.texture_u[0] == pytest.approx(-1.0)          # U mirrored on X (±1 self-inverse)
    assert p.texture_v[1] == pytest.approx(0.5)           # V on Y by 1/scale, NOT ×2 (density fixed)
    assert p.origin[0] == pytest.approx(-10.0)            # origin (point) mirrored by L


def test_texture_lock_on_transforms_axes_by_inverse_transpose_under_shear():
    # SHEER_XY k=0.45: L has L[1][0]=0.45. (L⁻¹)ᵀ shears the OTHER off-diagonal: U=(1,0,0) stays
    # (1,0,0) (a glued U along X is unaffected), V=(0,1,0) → (−0.45,1,0).
    a = _one_poly_actor(T.FScale((D(1), D(1), D(1)), D("0.5"), "SHEER_XY"))
    baked = T.bake(a, lock_textures=True)
    p = baked.brush.polys[0]
    assert p.texture_u[1] == pytest.approx(0.0)           # U unchanged (inverse-transpose, not L)
    assert p.texture_v[0] == pytest.approx(-0.45)


def test_texture_lock_off_leaves_the_axes():
    a = _one_poly_actor(T.FScale((D(2), D(2), D(2))))
    baked = T.bake(a, lock_textures=False)
    p = baked.brush.polys[0]
    assert p.texture_u == (1.0, 0.0, 0.0) and p.texture_v == (0.0, 1.0, 0.0)
    assert p.origin == (10.0, 0.0, 0.0)                  # unchanged
    # geometry still baked though
    assert p.vertices[2] == (D(128), D(128), D(0))


# ── guards ────────────────────────────────────────────────────────────────────────────────────

def test_scale_eps_guard_value():
    assert T.SCALE_EPS == Decimal("0.0001")


# ── ScaleField prop-verb routing (spec §10 nested-struct + no-silent-garbage) ────────────────────

def test_scalefield_get_set_unset_round_trip():
    from uedctl.propedit import TYPED_FIELDS, parse_token
    sf = TYPED_FIELDS["mainscale"]
    fs = sf.apply(parse_token("MainScale.Scale.X=2", expect_value=True), "set", None)
    assert fs.scale[0] == D(2)
    assert sf.get(parse_token("MainScale.Scale.X", expect_value=False), fs) == ("MainScale.Scale.X", "2")
    fs2 = sf.apply(parse_token("MainScale.SheerRate=0.3", expect_value=True), "set", fs)
    assert fs2.sheer_rate == D("0.3")
    # whole get renders the full struct
    key, val = sf.get(None, fs2)
    assert key == "MainScale" and "Scale=(X=2" in val and "SheerRate=0.3" in val
    # unset a member reverts to the class default
    fs3 = sf.apply(parse_token("MainScale.Scale.X", expect_value=False), "unset", fs2)
    assert fs3.scale[0] == D(1)


def test_scalefield_rejects_garbage_whole_value():
    from uedctl.propedit import PropEditError, TYPED_FIELDS, parse_token
    sf = TYPED_FIELDS["mainscale"]
    with pytest.raises(PropEditError):                # non-numeric axis, not a silent identity
        sf.apply(parse_token("MainScale=(Scale=(X=abc))", expect_value=True), "set", None)
    with pytest.raises(PropEditError):                # unknown member
        sf.apply(parse_token("MainScale=(Foo=1)", expect_value=True), "set", None)
    with pytest.raises(PropEditError):                # bad member path
        sf.apply(parse_token("MainScale.Nope=1", expect_value=True), "set", None)
