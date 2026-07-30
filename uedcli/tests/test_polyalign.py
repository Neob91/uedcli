"""`brush poly align` + `brush poly find` (build item 11).

Design: decisions.md 2026-07-18 21:40 UTC; board item `poly-align-brush-poly-find-built`. The load-bearing property
under test is UV CONTINUITY across a shared seam: for a world point on the edge two faces share,
`U=(P−Origin)·TextureU+PanU` computed from BOTH faces must agree.
"""
from __future__ import annotations

import io
import math
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from uedcli import polyalign
from uedcli.builders import cube, cylinder, make_brush_actor
from uedcli.dispatch import dispatch
from uedcli.model import Level


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def _brush(name, brush, loc=(0, 0, 0), rot=None):
    a = make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))
    if rot is not None:
        a.props.append(("Rotation", f"(Pitch={rot[0]},Yaw={rot[1]},Roll={rot[2]})"))
    return a


def _level(*actors):
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
    lv.order = [a.name for a in actors]
    return lv


def _shared_world_points(a1, p1, a2, p2):
    wv1 = polyalign._world_verts(a1, p1)
    wv2 = polyalign._world_verts(a2, p2)
    return [x for x in wv1 for y in wv2 if polyalign._len(polyalign._sub(x, y)) < 0.5]


def _assert_seam_continuous(a1, p1, a2, p2, *, eps=1e-3):
    shared = _shared_world_points(a1, p1, a2, p2)
    assert len(shared) >= 2, "faces must share an edge (2 vertices)"
    for s in shared:
        u1 = polyalign.face_uv(a1, p1, s)
        u2 = polyalign.face_uv(a2, p2, s)
        assert abs(u1[0] - u2[0]) < eps, f"U discontinuity at {s}: {u1} vs {u2}"
        assert abs(u1[1] - u2[1]) < eps, f"V discontinuity at {s}: {u1} vs {u2}"


# --------------------------------------------------------------------- coplanar --wall/--floor

def test_wall_two_brushes_uv_continuous_across_seam():
    """Two side-by-side wall brushes sharing an edge → one shared world frame → the seam is
    seamless. Multi-brush, so the per-brush inverse-transform (not identical stored fields) is
    exercised."""
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    a2 = _brush("W2", cube(64, 8, 128), loc=(96, 0, 0))
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    f2 = polyalign.find_faces(a2, "W2", facing="+Y")[0]
    touched = polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")
    assert touched == ["W1", "W2"]
    _assert_seam_continuous(a1, a1.brush.polys[f1], a2, a2.brush.polys[f2])


def test_wall_continuous_when_second_brush_is_rotated():
    """The continuity is defined in WORLD space and written back via each brush's OWN inverse
    rotation. A rotated neighbour whose stored frame differs must still be seamless in the world."""
    a1 = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))
    # W2 pitched 180° about Y (its +Y face still faces +Y, but the stored texture frame rotates),
    # stacked directly above so the two +Y faces are coplanar (y=4) and share the z=64 edge.
    a2 = _brush("W2", cube(64, 8, 128), loc=(0, 0, 128), rot=(32768, 0, 0))
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    f2 = polyalign.find_faces(a2, "W2", facing="+Y")[0]
    polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")
    # rotated brush ⇒ stored TextureU differs from W1's, but world mapping matches
    assert a2.brush.polys[f2].texture_u != a1.brush.polys[f1].texture_u
    _assert_seam_continuous(a1, a1.brush.polys[f1], a2, a2.brush.polys[f2])


def test_wall_adopt_seed_preserves_seed_pan():
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    a2 = _brush("W2", cube(64, 8, 128), loc=(96, 0, 0))
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    f2 = polyalign.find_faces(a2, "W2", facing="+Y")[0]
    a1.brush.polys[f1].pan = (7, 3)                       # seed already dialled in
    polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")
    # adopt-seed carries the seed's integer pan to every face
    assert a2.brush.polys[f2].pan == (7, 3)


def test_wall_fresh_frame_zeroes_pan_and_uses_unit_axes():
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    lv = _level(a1)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    a1.brush.polys[f1].pan = (7, 3)
    polyalign.align(lv, [f"W1:{f1}"], "wall", fresh_frame=True)
    p = a1.brush.polys[f1]
    assert p.pan == (0, 0)
    assert abs(polyalign._len(p.texture_u) - 1.0) < 1e-6   # unit ⇒ 1 texel/world-unit


def test_wall_rejects_horizontal_face():
    a1 = _brush("W1", cube(64, 64, 8), loc=(0, 0, 0))
    lv = _level(a1)
    f = polyalign.find_faces(a1, "W1", facing="+Z")[0]
    with pytest.raises(polyalign.PolyAlignError, match="horizontal"):
        polyalign.align(lv, [f"W1:{f}"], "wall")


def test_floor_rejects_vertical_face():
    a1 = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))
    lv = _level(a1)
    f = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    with pytest.raises(polyalign.PolyAlignError, match="vertical"):
        polyalign.align(lv, [f"W1:{f}"], "floor")


def test_wall_rejects_non_coplanar_set():
    a1 = _brush("W1", cube(64, 64, 128), loc=(0, 0, 0))
    lv = _level(a1)
    fpx = polyalign.find_faces(a1, "W1", facing="+X")[0]
    fpy = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    with pytest.raises(polyalign.PolyAlignError, match="not coplanar"):
        polyalign.align(lv, [f"W1:{fpx}", f"W1:{fpy}"], "wall")


def test_wall_rejects_coplanar_but_opposite_facing_faces():
    """Two faces on the SAME plane but pointing opposite ways must be rejected (aligning them would
    render the texture mirrored on the reverse face), not silently mirrored."""
    a1 = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))    # +Y face at y=4
    a2 = _brush("W2", cube(64, 8, 128), loc=(0, 8, 0))    # its -Y face at y=4 (same plane, opposite)
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    f2 = polyalign.find_faces(a2, "W2", facing="-Y")[0]
    with pytest.raises(polyalign.PolyAlignError, match="different directions"):
        polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")


# --------------------------------------------------------------------- ring

def test_ring_wrap_seam_continuous_and_perimeter():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "ring")
    # every INTERNAL seam is continuous
    for k in range(len(sides) - 1):
        _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]])
    # closing seam: total U advance == perimeter texels (density 1), so U wraps to that value
    chord = 2 * 128 * math.sin(math.pi / 8)
    # U at the last face's far edge (relative to its own frame origin) should be N*chord
    p_last = a.brush.polys[sides[-1]]
    wv = polyalign._world_verts(a, p_last)
    us = [polyalign.face_uv(a, p_last, v)[0] for v in wv]
    assert abs((max(us) - min(us)) - chord) < 1e-3         # each facet spans exactly one chord


def test_ring_leave_seam_vs_fit_perimeter():
    # 7 sides ⇒ perimeter does NOT land on an integer texel count at density 1.
    a = _brush("Cyl", cylinder(200, 100, 7), loc=(0, 0, 0))
    lv = _level(a)
    sides = [f"Cyl:{i}" for i in polyalign.find_faces(a, "Cyl", item="Side")]
    perim = 7 * 2 * 100 * math.sin(math.pi / 7)
    assert abs(perim - round(perim)) > 0.1                 # genuinely non-dividing

    # default: leaves the seam — the density is exactly 1, total U is fractional.
    polyalign.align(lv, sides, "ring")
    p0 = a.brush.polys[polyalign.find_faces(a, "Cyl", item="Side")[0]]
    assert abs(polyalign._len(p0.texture_u) - 1.0) < 1e-9

    # --fit-perimeter: rescales density so total U texels is the nearest integer (exact meet).
    a2 = _brush("Cyl", cylinder(200, 100, 7), loc=(0, 0, 0))
    lv2 = _level(a2)
    polyalign.align(lv2, sides, "ring", fit_perimeter=True)
    p0b = a2.brush.polys[0]
    density = polyalign._len(p0b.texture_u)
    assert abs(density * perim - round(perim)) < 1e-6      # integer total texels


def test_ring_continuous_on_rotated_relocated_cylinder():
    """The ring write-back goes through each face's OWN inverse rotation. A tilted, off-origin
    cylinder must still be seamless in the world — exercises the ring inverse-transform path."""
    a = _brush("Tower", cylinder(256, 128, 8), loc=(1500, -800, 200), rot=(6000, 12000, 3000))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "ring")
    for k in range(len(sides) - 1):
        _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]], eps=5e-3)


def test_ring_fresh_frame_unit_density_and_continuous():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "ring", fresh_frame=True)
    assert abs(polyalign._len(a.brush.polys[sides[0]].texture_u) - 1.0) < 1e-6
    for k in range(len(sides) - 1):
        _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]])


def test_ring_keeps_pan_integer():
    a = _brush("Tower", cylinder(256, 128, 7), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    a.brush.polys[sides[0]].pan = (3, 5)                  # seed pan carried, stays integer
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "ring")
    for i in sides:
        p = a.brush.polys[i]
        assert p.pan == (3, 5)
        assert all(isinstance(c, int) for c in p.pan)


def test_ring_fit_perimeter_closes_the_seam():
    """The closing seam (last face's far edge == first face's seam edge, same world points): with
    --fit-perimeter the U difference around the ring is an INTEGER texel count (an exact meet);
    without it, for a non-dividing 7-gon, it is fractional (the seam is left)."""
    def _closing_gap(fit):
        a = _brush("C", cylinder(200, 100, 7), loc=(0, 0, 0))
        lv = _level(a)
        sides = polyalign.find_faces(a, "C", item="Side")
        polyalign.align(lv, [f"C:{i}" for i in sides], "ring", fit_perimeter=fit)
        p_first, p_last = a.brush.polys[sides[0]], a.brush.polys[sides[-1]]
        shared = _shared_world_points(a, p_first, a, p_last)   # the seam edge (2 verts)
        assert len(shared) == 2
        s = shared[0]
        return polyalign.face_uv(a, p_last, s)[0] - polyalign.face_uv(a, p_first, s)[0]

    gap_fit = _closing_gap(True)
    assert abs(gap_fit - round(gap_fit)) < 1e-6            # integer texel meet
    gap_raw = _closing_gap(False)
    assert abs(gap_raw - round(gap_raw)) > 0.1            # left fractional (seam visible)


def test_ring_rejects_cap_face():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    caps = polyalign.find_faces(a, "Tower", item="Cap")
    with pytest.raises(polyalign.PolyAlignError, match="not a ring side face"):
        polyalign.align(lv, [f"Tower:{i}" for i in sides] + [f"Tower:{caps[0]}"], "ring")


def test_ring_rejects_multi_brush():
    a = _brush("C1", cylinder(256, 128, 8), loc=(0, 0, 0))
    b = _brush("C2", cylinder(256, 128, 8), loc=(500, 0, 0))
    lv = _level(a, b)
    with pytest.raises(polyalign.PolyAlignError, match="ONE cylinder brush"):
        polyalign.align(lv, ["C1:0", "C2:0"], "ring")


def test_fit_perimeter_requires_ring():
    a = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))
    lv = _level(a)
    with pytest.raises(polyalign.PolyAlignError, match="fit-perimeter applies only to --ring"):
        polyalign.align(lv, ["W1:2"], "wall", fit_perimeter=True)


# --------------------------------------------------------------------- target resolution + find

def test_align_empty_tokens_is_noop():
    a = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))
    lv = _level(a)
    assert polyalign.align(lv, [], "wall") == []


def test_resolve_targets_bare_name_is_all_polys_ordered():
    a = _brush("W1", cube(64, 64, 64), loc=(0, 0, 0))
    lv = _level(a)
    assert polyalign.resolve_align_targets(lv, ["W1"]) == [("W1", i) for i in range(6)]


def test_resolve_targets_dedups_preserving_order():
    a = _brush("W1", cube(64, 64, 64), loc=(0, 0, 0))
    lv = _level(a)
    got = polyalign.resolve_align_targets(lv, ["W1:2", "W1:0", "W1:2"])
    assert got == [("W1", 2), ("W1", 0)]


def test_resolve_targets_unknown_brush():
    lv = _level(_brush("W1", cube(8, 8, 8)))
    with pytest.raises(polyalign.PolyAlignError, match="unknown brush 'Nope'"):
        polyalign.resolve_align_targets(lv, ["Nope:0"])


def test_resolve_targets_bad_selector():
    lv = _level(_brush("W1", cube(8, 8, 8)))
    with pytest.raises(polyalign.PolyAlignError, match="bad poly index"):
        polyalign.resolve_align_targets(lv, ["W1:99x"])


def test_find_faces_item_filter_drops_caps():
    a = _brush("Tower", cylinder(256, 128, 6), loc=(0, 0, 0))
    assert polyalign.find_faces(a, "Tower", item="Side") == [0, 1, 2, 3, 4, 5]
    assert polyalign.find_faces(a, "Tower", item="cap") == [6, 7]     # case-insensitive


def test_find_faces_facing_filter():
    a = _brush("W1", cube(64, 64, 64), loc=(0, 0, 0))
    got = polyalign.find_faces(a, "W1", facing="+Z")
    assert len(got) == 1
    assert polyalign._poly_facing(polyalign._world_verts(a, a.brush.polys[got[0]])) == "+Z"


def test_find_faces_texture_filter_last_component():
    a = _brush("W1", cube(64, 64, 64), loc=(0, 0, 0))
    a.brush.polys[0].texture = "DeusExDeco.Textures.Wood"
    assert polyalign.find_faces(a, "W1", texture="wood") == [0]
    assert polyalign.find_faces(a, "W1", texture="DeusExDeco.Textures.Wood") == [0]
    assert polyalign.find_faces(a, "W1", texture="stone") == []


def test_find_faces_non_brush_raises():
    from uedcli.model import Actor
    lv = _level()
    lv.actors["P"] = Actor(name="P", cls="Engine.PathNode")
    with pytest.raises(polyalign.PolyAlignError, match="not a brush"):
        polyalign.find_faces(lv.actors["P"], "P", item="Side")


# --------------------------------------------------------------------- dispatch (CLI seam)

def _fake_src(level):
    src = mock.Mock()
    src.load.return_value = level
    return src


def _run(args, level, stdin=None):
    import contextlib
    src = _fake_src(level)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("uedcli.dispatch.Driver"))
        stack.enter_context(mock.patch("uedcli.dispatch._resolve_level_source", return_value=src))
        if stdin is not None:
            stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        rc = dispatch(args)
    return rc, src


def test_dispatch_poly_find_prints_selectors(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", name="Tower",
                           item="Side", facing=None, texture=None, json=False, container="c")
    rc, _ = _run(args, _level(a))
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.splitlines() == [f"Tower:{i}" for i in range(6)]
    assert "6 face(s) matched" in out.err          # summary → stderr, selectors → stdout


def test_dispatch_poly_find_json(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", name="Tower",
                           item="Cap", facing=None, texture=None, json=True, container="c")
    rc, _ = _run(args, _level(a))
    import json as _json
    rows = _json.loads(capsys.readouterr().out)
    assert [r["poly"] for r in rows] == [6, 7] and all(r["item"] == "Cap" for r in rows)


def test_dispatch_poly_find_bad_facing_exit2(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", name="Tower",
                           item=None, facing="up", texture=None, json=False, container="c")
    rc, _ = _run(args, _level(a))
    assert rc == 2 and "invalid value" in capsys.readouterr().err


def test_dispatch_poly_find_unknown_brush_exit2(capsys):
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", name="Nope",
                           item=None, facing=None, texture=None, json=False, container="c")
    rc, _ = _run(args, _level(_brush("Tower", cube(8, 8, 8))))
    assert rc == 2 and "Actor not found: Nope" in capsys.readouterr().err


def test_dispatch_poly_align_positional_saves(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    sides = [f"Tower:{i}" for i in range(8)]
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=sides,
                           mode="ring", fresh_frame=False, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a))
    assert rc == 0
    assert src.save.call_args.kwargs["touched"] == ["Tower"]
    assert capsys.readouterr().out.strip() == "Tower"


def test_dispatch_poly_align_reads_stdin_selectors(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    stdin = "".join(f"Tower:{i}\n" for i in range(8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-"],
                           mode="ring", fresh_frame=False, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin=stdin)
    assert rc == 0 and src.save.called


def test_dispatch_poly_align_empty_stdin_noop(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-"],
                           mode="ring", fresh_frame=False, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin="")
    assert rc == 0 and not src.save.called          # clean no-op, nothing written


def test_dispatch_poly_align_mixing_stdin_and_names_exit2(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-", "Tower:0"],
                           mode="ring", fresh_frame=False, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin="Tower:1\n")
    assert rc == 2 and not src.save.called          # `-` is the sole source; mixing is exit 2


def test_dispatch_poly_align_error_exit2_no_save(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    tokens = [f"Tower:{i}" for i in range(8)] + ["Tower:8"]   # sides + a cap → not a ring
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=tokens,
                           mode="ring", fresh_frame=False, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a))
    assert rc == 2 and not src.save.called
    assert "ring side face" in capsys.readouterr().err


# --------------------------------------------------------------------- engine-fact regressions
# Per uedcli dev/docs/rules/spikes.md "pin the finding" — re-assert the two load-bearing facts poly align's
# math rests on, so a change to the UV convention or the cylinder builder trips a red test.
# Evidence: board item `poly-align-brush-poly-find-built` (UV convention §) — render.rs:159-165 +
# texframe.world_uv_frame; builders.cylinder radius placement (builders.py:206-207).

def test_engine_fact_uv_formula_is_base_relative_plus_pan():
    """The canonical UV is `U=(Vertex−Origin)·TextureU+PanU` (V analogously), scale in |TextureU|.
    A committed frame with hand-computed UVs pins it: a UNIT TextureU gives 1 texel/world-unit, and
    PanU is an additive texel offset. Anchored to render.rs:159-165 (the renderer uses the authored
    Origin as uv_base and adds the surface Pan)."""
    from uedcli.model import Polygon
    from uedcli.texframe import world_uv_frame
    p = Polygon()
    p.origin = (10.0, 20.0, 0.0)
    p.texture_u = (1.0, 0.0, 0.0)         # unit ⇒ 1 texel per world unit along +X
    p.texture_v = (0.0, 1.0, 0.0)
    p.pan = (5, 7)
    p.vertices = [_D(10, 20, 0), _D(74, 20, 0), _D(74, 84, 0), _D(10, 84, 0)]
    a = _brush("F", cube(8, 8, 8))        # a carrier actor (identity transform)
    a.brush.polys = [p]
    base, tu, tv, pan = world_uv_frame(a, p)
    assert base == (10.0, 20.0, 0.0) and tu == (1.0, 0.0, 0.0) and pan == (5.0, 7.0)
    # hand-computed: vertex (74,20) is 64 world units along +X from Origin ⇒ U = 64*1 + 5 = 69.
    u, v = polyalign.face_uv(a, p, (74.0, 84.0, 0.0))
    assert abs(u - (64 * 1.0 + 5)) < 1e-9
    assert abs(v - (64 * 1.0 + 7)) < 1e-9


def test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n():
    """A `cylinder` side facet's flat width is the chord `2r·sin(π/N)` — the density unit the ring
    U-advance uses (decisions.md 2026-07-18 21:40 UTC). Measured from the builder's own geometry,
    so a change to `builders.cylinder`'s vertex placement trips this."""
    for r, n in [(128.0, 8), (100.0, 7), (256.0, 12)]:
        a = _brush("C", cylinder(200.0, r, n))
        side0 = polyalign.find_faces(a, "C", item="Side")[0]
        wv = polyalign._world_verts(a, a.brush.polys[side0])
        # the facet's two BOTTOM vertices (min z) define the chord
        zmin = min(v[2] for v in wv)
        bottom = [v for v in wv if abs(v[2] - zmin) < 1e-6]
        assert len(bottom) == 2
        measured = polyalign._len(polyalign._sub(bottom[0], bottom[1]))
        assert abs(measured - 2 * r * math.sin(math.pi / n)) < 1e-6


def _editor_reexport(level):
    """The intended level as UnrealEd would RE-EXPORT it after a `level materialize` round trip,
    modelled on the one difference that matters here: the editor's `MAP EXPORT` never writes a
    zero polygon `Pan`. It writes `Pan U=<u> V=<v>` only when at least one component is non-zero
    (no `Pan U=0 V=0` appears in any real editor export in this repo's fixtures), because an absent
    Pan already means zero — the poly Pan has no class default behind it, unlike an actor property.

    So: emit the level exactly as the trunk/`MAP IMPORT` payload does, drop any zero-Pan line, and
    parse it back. Everything else (coordinates, texture vectors, properties) round-trips through
    the compare view's own float32/typed reductions and is not modelled here."""
    from uedcli.emit import emit_map
    from uedcli.model import parse_t3d
    text = emit_map(list(level.actors.values()))
    kept = [ln for ln in text.splitlines() if ln.strip() != "Pan      U=0 V=0"]
    out = parse_t3d("\n".join(kept) + "\n")
    out.order = list(level.order)
    return out


def test_align_emits_no_zero_pan_so_materialize_can_verify_the_built_map():
    """REGRESSION (shipped bug, 2026-07-26). `brush build cube | actor add -` then
    `brush poly find --facing +Z | brush poly align --floor -` then `level materialize` aborted
    with `post-verify mismatch: … differs in GEOMETRY at line 43` and wrote NOTHING — the entire
    documented `poly find | poly align` workflow could not complete.

    Cause: align writes the seed's pan onto every target face, and a freshly built brush carries no
    Pan at all, so the aligned face GAINED a `Pan U=0 V=0` line in the emitted trunk. The editor
    imports that (zero pan == no pan) but omits it again on export, and the post-verify compares
    brush text LINE BY LINE — so the extra line shifted every following line and the compare
    aborted the build. The fix is in `emit_polygon`: a zero pan is the default spelling and is
    never written, so the trunk states exactly what the editor would.
    """
    from uedcli.normalize import canonical_actor_t3d, compare_view
    from uedcli.tests.conftest import StubDefaults
    a = _brush("Box", cube(256, 256, 256))
    lv = _level(a)
    f = polyalign.find_faces(a, "Box", facing="+Z")[0]
    assert a.brush.polys[f].pan is None                    # a built cube has no Pan anywhere
    polyalign.align(lv, [f"Box:{f}"], "floor")
    assert "Pan" not in canonical_actor_t3d(a)             # …and aligning must not invent one
    d = StubDefaults()
    assert compare_view(_editor_reexport(lv), defaults=d) == compare_view(lv, defaults=d)


def test_align_still_carries_a_non_zero_seed_pan_into_the_trunk():
    """The counterpart guard: only the all-zero pan is a spelling of the default. A seed pan the
    user dialled in is real content and must reach the trunk, or align would silently discard it."""
    from uedcli.normalize import canonical_actor_t3d
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    a2 = _brush("W2", cube(64, 8, 128), loc=(96, 0, 0))
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing="+Y")[0]
    f2 = polyalign.find_faces(a2, "W2", facing="+Y")[0]
    a1.brush.polys[f1].pan = (7, 3)
    polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")
    assert "Pan      U=7 V=3" in canonical_actor_t3d(a2)
