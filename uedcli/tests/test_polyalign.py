"""`brush poly align` + `brush poly find` (build item 11).

Design: dev/docs/direction/conventions.md 2026-07-18 21:40 UTC; board item `poly-align-brush-poly-find-built`. The load-bearing property
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

from uedcli import polyalign, query
from uedcli.builders import cube, cylinder, make_brush_actor, revolve
from uedcli.cli.dispatch import dispatch
from uedcli.facing_spec import parse_facing_spec as _fs
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


def _brush_from_quads(name, quads, loc=(0, 0, 0)):
    """A brush actor at `loc` whose polys are the given quads (each a list of four (x,y,z) verts) —
    for hand-assembled run fixtures no builder emits (a varying cross section, a T-junction)."""
    from uedcli.model import Brush, Polygon
    from uedcli.builders import make_brush_actor
    polys = [Polygon(vertices=[tuple(float(c) for c in v) for v in q]) for q in quads]
    return make_brush_actor(name, Brush("Model", polys), location=tuple(Decimal(str(c)) for c in loc))


def _run_seam_shear(actor, idxs):
    """Max |dU|,|dV| over every shared edge among `idxs` (a seam_check port). Independent of the
    implementation's own stderr report, so it can cross-check it. (Buckets coords by _WELD — fine on
    the grid-aligned fixtures here; the implementation itself uses a distance test, never buckets.)"""
    verts = {i: polyalign._world_verts(actor, actor.brush.polys[i]) for i in idxs}
    edges: dict = {}
    for i, wv in verts.items():
        for k in range(len(wv)):
            key = frozenset((tuple(round(c / 0.5) for c in wv[k]),
                             tuple(round(c / 0.5) for c in wv[(k + 1) % len(wv)])))
            edges.setdefault(key, []).append((i, wv[k], wv[(k + 1) % len(wv)]))
    du = dv = 0.0
    for owners in edges.values():
        if len(owners) != 2:
            continue
        (ia, a0, a1), (ib, _, _) = owners
        for p in (a0, a1):
            ua, va = polyalign.face_uv(actor, actor.brush.polys[ia], p)
            ub, vb = polyalign.face_uv(actor, actor.brush.polys[ib], p)
            du, dv = max(du, abs(ua - ub)), max(dv, abs(va - vb))
    return du, dv


# --------------------------------------------------------------------- coplanar wall/floor

def test_wall_two_brushes_uv_continuous_across_seam():
    """Two side-by-side wall brushes sharing an edge → one shared world frame → the seam is
    seamless. Multi-brush, so the per-brush inverse-transform (not identical stored fields) is
    exercised."""
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    a2 = _brush("W2", cube(64, 8, 128), loc=(96, 0, 0))
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    f2 = polyalign.find_faces(a2, "W2", facing=_fs("ny:1"))[0]
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
    f1 = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    f2 = polyalign.find_faces(a2, "W2", facing=_fs("ny:1"))[0]
    polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")
    # rotated brush ⇒ stored TextureU differs from W1's, but world mapping matches
    assert a2.brush.polys[f2].texture_u != a1.brush.polys[f1].texture_u
    _assert_seam_continuous(a1, a1.brush.polys[f1], a2, a2.brush.polys[f2])


def test_wall_zeroes_pan_and_is_unit_on_a_face_square_to_its_axis():
    # The projection family writes Pan=(0,0) and, on a face square to its projection axis, unit axes
    # (a +Y wall projects down Y; proj(X̂)/proj(Ẑ) are then unit). The |proj|-density stretch on a
    # TILTED face is pinned against the editor golden in test_engine_facts (align_wall/floor parity).
    a1 = _brush("W1", cube(64, 8, 128), loc=(32, 0, 0))
    lv = _level(a1)
    f1 = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    a1.brush.polys[f1].pan = (7, 3)
    polyalign.align(lv, [f"W1:{f1}"], "wall")
    p = a1.brush.polys[f1]
    assert p.pan == (0, 0)
    assert abs(polyalign._len(p.texture_u) - 1.0) < 1e-6   # unit ⇒ 1 texel/world-unit


def test_wall_rejects_horizontal_face_on_the_projection_guard():
    # A horizontal face (N ≈ ±Z) ties |N.X| = |N.Y| = 0, so `wall` derives axis X and the
    # |N.X| > 0.05 guard fails — exit 2 (the old "use floor" advice is gone; filter upstream).
    a1 = _brush("W1", cube(64, 64, 8), loc=(0, 0, 0))
    lv = _level(a1)
    f = polyalign.find_faces(a1, "W1", facing=_fs("nz:1"))[0]
    with pytest.raises(polyalign.PolyAlignError, match="too close to horizontal"):
        polyalign.align(lv, [f"W1:{f}"], "wall")


def test_floor_rejects_vertical_face_on_the_projection_guard():
    a1 = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))
    lv = _level(a1)
    f = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    with pytest.raises(polyalign.PolyAlignError, match="too close to vertical"):
        polyalign.align(lv, [f"W1:{f}"], "floor")


def test_wall_guard_names_every_failing_face():
    # The guard is a batch pre-pass: it collects ALL offenders and names each, not just the first.
    a1 = _brush("W1", cube(64, 64, 8), loc=(0, 0, 0))
    lv = _level(a1)
    top = polyalign.find_faces(a1, "W1", facing=_fs("nz:1"))[0]
    bot = polyalign.find_faces(a1, "W1", facing=_fs("nz:-1"))[0]
    with pytest.raises(polyalign.PolyAlignError) as e:
        polyalign.align(lv, [f"W1:{top}", f"W1:{bot}"], "wall")
    msg = str(e.value)
    assert f"W1:{top}" in msg and f"W1:{bot}" in msg      # nothing written; both named


def test_wall_two_planes_each_get_their_own_projected_frame():
    # Replaces the deleted coplanarity guard: a +X and a +Y face in ONE `wall` invocation each get
    # their own world-projected frame (different axes), instead of being rejected as "not coplanar".
    a1 = _brush("W1", cube(64, 64, 128), loc=(0, 0, 0))
    lv = _level(a1)
    fpx = polyalign.find_faces(a1, "W1", facing=_fs("nx:1"))[0]
    fpy = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    polyalign.align(lv, [f"W1:{fpx}", f"W1:{fpy}"], "wall")   # no error
    tux = a1.brush.polys[fpx].texture_u
    tuy = a1.brush.polys[fpy].texture_u
    assert polyalign._len(tux) > 1e-6 and polyalign._len(tuy) > 1e-6
    assert tux != tuy                                        # each keyed to its own plane


def test_wall_opposite_faces_get_an_identical_world_frame():
    # Replaces the deleted co-orientation guard: two coplanar faces pointing OPPOSITE ways get a
    # byte-identical world frame (the projection family is invariant under n → −n). The visual
    # consequence — a texture mirrored on the back face — is the editor's own behaviour (ruling 9).
    a1 = _brush("W1", cube(64, 8, 128), loc=(0, 0, 0))    # +Y face at y=4
    a2 = _brush("W2", cube(64, 8, 128), loc=(0, 8, 0))    # its -Y face at y=4 (same plane, opposite)
    lv = _level(a1, a2)
    f1 = polyalign.find_faces(a1, "W1", facing=_fs("ny:1"))[0]
    f2 = polyalign.find_faces(a2, "W2", facing=_fs("ny:-1"))[0]
    polyalign.align(lv, [f"W1:{f1}", f"W2:{f2}"], "wall")   # no error
    # A shared world corner maps to the same (U,V) from either face ⇒ one continuous world frame.
    _assert_seam_continuous(a1, a1.brush.polys[f1], a2, a2.brush.polys[f2])


def test_wall_frame_is_set_independent_and_idempotent():
    # A world-anchored frame does not depend on which faces were selected together or on order, and
    # re-running changes nothing (§2.3, the property the ruling is for).
    def _frame(a):
        p = a.brush.polys[polyalign.find_faces(a, a.name, facing=_fs("ny:1"))[0]]
        return (p.origin, p.texture_u, p.texture_v, p.pan)
    solo = _brush("W", cube(64, 8, 128), loc=(32, 0, 0))
    lv1 = _level(solo)
    fy = polyalign.find_faces(solo, "W", facing=_fs("ny:1"))[0]
    polyalign.align(lv1, [f"W:{fy}"], "wall")
    once = _frame(solo)
    polyalign.align(lv1, [f"W:{fy}"], "wall")             # re-run
    assert _frame(solo) == once                           # idempotent

    # aligned as part of a larger set (with its +X neighbour) ⇒ the SAME frame for the +Y face
    withset = _brush("W", cube(64, 8, 128), loc=(32, 0, 0))
    lv2 = _level(withset)
    fx = polyalign.find_faces(withset, "W", facing=_fs("nx:1"))[0]
    polyalign.align(lv2, [f"W:{fx}", f"W:{fy}"], "wall")
    assert _frame(withset) == once                        # set-independent


# --------------------------------------------------------------------- ring

def test_run_wrap_seam_continuous_and_perimeter():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "run")
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


def test_run_leave_seam_vs_fit_perimeter():
    # 7 sides ⇒ perimeter does NOT land on an integer texel count at density 1.
    a = _brush("Cyl", cylinder(200, 100, 7), loc=(0, 0, 0))
    lv = _level(a)
    sides = [f"Cyl:{i}" for i in polyalign.find_faces(a, "Cyl", item="Side")]
    perim = 7 * 2 * 100 * math.sin(math.pi / 7)
    assert abs(perim - round(perim)) > 0.1                 # genuinely non-dividing

    # default: leaves the seam — the density is exactly 1, total U is fractional.
    polyalign.align(lv, sides, "run")
    p0 = a.brush.polys[polyalign.find_faces(a, "Cyl", item="Side")[0]]
    assert abs(polyalign._len(p0.texture_u) - 1.0) < 1e-9

    # --fit-perimeter: rescales density so total U texels is the nearest integer (a whole-texel
    # residual remains at the seam — the whole-TILE close arrives with the catalog, step 5).
    a2 = _brush("Cyl", cylinder(200, 100, 7), loc=(0, 0, 0))
    lv2 = _level(a2)
    polyalign.align(lv2, sides, "run", fit_perimeter=True)
    p0b = a2.brush.polys[0]
    density = polyalign._len(p0b.texture_u)
    assert abs(density * perim - round(perim)) < 1e-6      # integer total texels


def test_run_continuous_on_rotated_relocated_cylinder():
    """The ring write-back goes through each face's OWN inverse rotation. A tilted, off-origin
    cylinder must still be seamless in the world — exercises the ring inverse-transform path."""
    a = _brush("Tower", cylinder(256, 128, 8), loc=(1500, -800, 200), rot=(6000, 12000, 3000))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "run")
    for k in range(len(sides) - 1):
        _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]], eps=5e-3)


def test_run_unit_density_and_continuous():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "run")
    assert abs(polyalign._len(a.brush.polys[sides[0]].texture_u) - 1.0) < 1e-6
    for k in range(len(sides) - 1):
        _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]])


def test_run_zeroes_pan_keeping_it_integer():
    # Ruling 8: adopt-seed is gone, so a seed's non-zero pan is DISCARDED — every face resets to
    # Pan=(0,0). The components stay `int` (a poly Pan is always integer texels).
    a = _brush("Tower", cylinder(256, 128, 7), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    a.brush.polys[sides[0]].pan = (3, 5)                  # seed pan is NOT carried
    polyalign.align(lv, [f"Tower:{i}" for i in sides], "run")
    for i in sides:
        p = a.brush.polys[i]
        assert p.pan == (0, 0)
        assert all(isinstance(c, int) for c in p.pan)


def test_run_fit_perimeter_snaps_to_integer_texels():
    """At the closing seam (last face's far edge == first face's seam edge, same world points):
    --fit-perimeter snaps the U difference around the ring to an INTEGER texel count; without it, for
    a non-dividing 7-gon, it is fractional. NB an integer-texel gap is not a closed seam — a texture
    repeats every T texels, so a whole-texel residual can remain; the whole-TILE close arrives with
    the catalog (step 5)."""
    def _closing_gap(fit):
        a = _brush("C", cylinder(200, 100, 7), loc=(0, 0, 0))
        lv = _level(a)
        sides = polyalign.find_faces(a, "C", item="Side")
        polyalign.align(lv, [f"C:{i}" for i in sides], "run", fit_perimeter=fit)
        p_first, p_last = a.brush.polys[sides[0]], a.brush.polys[sides[-1]]
        shared = _shared_world_points(a, p_first, a, p_last)   # the seam edge (2 verts)
        assert len(shared) == 2
        s = shared[0]
        return polyalign.face_uv(a, p_last, s)[0] - polyalign.face_uv(a, p_first, s)[0]

    gap_fit = _closing_gap(True)
    assert abs(gap_fit - round(gap_fit)) < 1e-6            # integer texel meet
    gap_raw = _closing_gap(False)
    assert abs(gap_raw - round(gap_raw)) > 0.1            # left fractional (seam visible)


def test_run_rejects_cap_face_with_the_item_side_hint():
    # A cylinder's cap shares an edge with every side, so all faces are degree ≥ 3: the branch check
    # names them ALL and rides the `--item Side` hint (there is no cap classification, §2.4.1 step 4).
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    lv = _level(a)
    sides = polyalign.find_faces(a, "Tower", item="Side")
    caps = polyalign.find_faces(a, "Tower", item="Cap")
    with pytest.raises(polyalign.PolyAlignError) as e:
        polyalign.align(lv, [f"Tower:{i}" for i in sides] + [f"Tower:{caps[0]}"], "run")
    msg = str(e.value)
    assert "--item Side" in msg and "cannot branch" in msg
    assert f"Tower:{caps[0]}" in msg                     # the cap is among the named offenders


def test_run_rejects_multi_brush():
    a = _brush("C1", cylinder(256, 128, 8), loc=(0, 0, 0))
    b = _brush("C2", cylinder(256, 128, 8), loc=(500, 0, 0))
    lv = _level(a, b)
    with pytest.raises(polyalign.PolyAlignError, match="ONE brush"):
        polyalign.align(lv, ["C1:0", "C2:0"], "run")


# --------------------------------------------------------------------- run §4.2 pins

def _flat_bend(name="Bed"):
    # 6 flat coplanar faces (normal (0,0,-1)) sweeping a 90°+ arc — the curved bed `run` exists for.
    a = _brush(name, revolve([(192, -16), (256, -16), (256, 16), (192, 16)], 180, 6, axis="x"))
    return a, polyalign.find_faces(a, name, item="Side0")


def test_run_cylinder_exact_under_turn():
    # A run whose seams are parallel to the turn axis (cylinder sides) is exactly continuous on BOTH
    # axes at every turn angle (§2.7) — checked on every INTERNAL seam (the closing seam is left open).
    for turn in (0, 8192, 5000):
        a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
        lv = _level(a)
        sides = polyalign.find_faces(a, "Tower", item="Side")
        polyalign.align(lv, [f"Tower:{i}" for i in sides], "run", turn=turn)
        for k in range(len(sides) - 1):
            _assert_seam_continuous(a, a.brush.polys[sides[k]], a, a.brush.polys[sides[k + 1]],
                                    eps=2e-3)


def test_run_turn_selects_the_stored_axis_the_advance_lands_in():
    # Flat bend: at turn 0 the along-run shear is in U (V exact); at a quarter turn it moves to V (U
    # exact); at 8192 it splits across both (§2.4.3, §4.2 "by STORED COMPONENT").
    def sh(turn):
        a, s = _flat_bend()
        polyalign.align(_level(a), [f"Bed:{i}" for i in s], "run", turn=turn)
        return _run_seam_shear(a, s)
    du0, dv0 = sh(0)
    assert du0 > 1.0 and dv0 < 2e-3
    duq, dvq = sh(16384)
    assert duq < 2e-3 and dvq > 1.0
    du8, dv8 = sh(8192)
    assert du8 > 1.0 and dv8 > 1.0 and abs(du8 - dv8) < 2e-3      # split evenly at 45°


def test_run_v_runs_down_on_a_cylinder():
    # V·Ẑ < 0 (a UE1 texture's V=0 row is its top) — the deliberate flip of what --ring wrote (§7.2).
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(_level(a), [f"Tower:{i}" for i in sides], "run")
    for i in sides:
        assert a.brush.polys[i].texture_v[2] < 0


def test_run_v_down_is_the_same_world_direction_on_a_bed_and_its_mirror():
    # On a flat bed the across dominant component is Ŷ; V·Ŷ < 0 whether the walk travels +X̂ or −X̂
    # (a sign leaking from the walk direction would flip between them). §4.2 (b).
    fwd = _brush_from_quads("F", [[(0, -64, 0), (128, -48, 0), (128, 48, 0), (0, 64, 0)],
                                  [(128, -48, 0), (256, -32, 0), (256, 32, 0), (128, 48, 0)]])
    polyalign.align(_level(fwd), ["F:0", "F:1"], "run")
    # mirror across X=0 so the same strip's walk runs −X̂
    mir = _brush_from_quads("M", [[(0, -64, 0), (-128, -48, 0), (-128, 48, 0), (0, 64, 0)],
                                  [(-128, -48, 0), (-256, -32, 0), (-256, 32, 0), (-128, 48, 0)]])
    polyalign.align(_level(mir), ["M:0", "M:1"], "run")
    assert fwd.brush.polys[0].texture_v[1] < 0
    assert mir.brush.polys[0].texture_v[1] < 0                    # same world direction, not flipped


def test_run_across_sign_fixed_at_root_stays_continuous_through_45_degrees():
    # A flat bend turning ≥90° sweeps ĉ through the 45° discontinuity; a per-face world sign rule
    # would mirror V at that one seam. A flat bend SHEARS U by design (§2.7), so only V must stay
    # continuous — fixing the sign at the root and propagating keeps it so across EVERY seam (§2.4.2).
    a, s = _flat_bend()
    polyalign.align(_level(a), [f"Bed:{i}" for i in s], "run")
    for k in range(len(s) - 1):
        shared = _shared_world_points(a, a.brush.polys[s[k]], a, a.brush.polys[s[k + 1]])
        assert len(shared) >= 2
        for p in shared:
            v1 = polyalign.face_uv(a, a.brush.polys[s[k]], p)[1]
            v2 = polyalign.face_uv(a, a.brush.polys[s[k + 1]], p)[1]
            assert abs(v1 - v2) < 5e-3, f"V mirrored at seam {s[k]}|{s[k+1]}: {v1} vs {v2}"


def test_run_across_zero_is_propagated_not_re_derived_per_face():
    # A two-quad bed that NARROWS along the run: the across-zero is the ROOT's entry-edge low
    # endpoint, propagated by V-continuity. A per-face rule would re-derive B's own low endpoint and
    # shift B's V, breaking the seam (§2.4.2). Assert the seam stays V-continuous.
    a = _brush_from_quads("Bed", [[(0, -64, 0), (128, -48, 0), (128, 48, 0), (0, 64, 0)],
                                  [(128, -48, 0), (256, -32, 0), (256, 32, 0), (128, 48, 0)]])
    polyalign.align(_level(a), ["Bed:0", "Bed:1"], "run")
    _assert_seam_continuous(a, a.brush.polys[0], a, a.brush.polys[1], eps=5e-3)


def test_run_walk_direction_on_a_closed_cylinder():
    # U increases with poly index and the OPEN seam is sides[-1]|sides[0], where --ring puts it —
    # not sides[0]|sides[1] (a reversed wrap). Every shipped assertion is direction-agnostic, so this
    # is the only guard against a silently reversed wrap (§2.4.1 step 7).
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    sides = polyalign.find_faces(a, "Tower", item="Side")       # consecutive indices 0..7
    polyalign.align(_level(a), [f"Tower:{i}" for i in sides], "run")
    # the closing (open) seam is the pair whose U gap ≈ the full perimeter
    def gap(i, j):
        s = _shared_world_points(a, a.brush.polys[i], a, a.brush.polys[j])
        return abs(polyalign.face_uv(a, a.brush.polys[j], s[0])[0]
                   - polyalign.face_uv(a, a.brush.polys[i], s[0])[0])
    perim = 8 * 2 * 128 * math.sin(math.pi / 8)
    assert gap(sides[-1], sides[0]) > perim * 0.9               # the open seam sits here
    assert gap(sides[0], sides[1]) < 2 * 128 * math.sin(math.pi / 8) + 1   # an internal seam: ~1 chord


def test_run_order_of_tokens_has_no_bearing_on_the_result():
    # Shuffling ALL tokens (the first included) produces a byte-identical result — the walk is derived
    # from geometry and poly index, never from input order (ruling 3, §2.4.1).
    import random
    def frames_for(order):
        a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
        polyalign.align(_level(a), [f"Tower:{i}" for i in order], "run")
        return [(a.brush.polys[i].origin, a.brush.polys[i].texture_u, a.brush.polys[i].texture_v)
                for i in range(8)]
    base = frames_for(list(range(8)))
    shuffled = list(range(8))
    random.Random(1).shuffle(shuffled)
    assert frames_for(shuffled) == base


def test_run_branch_check_square_prism_with_both_caps():
    # `align run <Box>` — a cube's 6 faces, each adjacent to 4 others — exits 2 (the abandoned
    # degree==|set|-1 predicate did NOT catch this) with the --item Side hint (§2.4.1 step 4).
    a = _brush("Box", cube(128, 128, 128), loc=(0, 0, 0))
    with pytest.raises(polyalign.PolyAlignError, match="cannot branch"):
        polyalign.align(_level(a), ["Box"], "run")


def test_run_branch_check_t_junction():
    # A genuine T-junction of quads (a middle face with 3 neighbours) exits 2 naming the face and its
    # neighbour count.
    a = _brush_from_quads("T", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],           # 0: centre
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)],       # 1: shares +X edge
        [(0, 64, 0), (64, 64, 0), (64, 128, 0), (0, 128, 0)],       # 2: shares +Y edge of centre
        [(0, -64, 0), (64, -64, 0), (64, 0, 0), (0, 0, 0)]])        # 3: shares −Y edge of centre
    with pytest.raises(polyalign.PolyAlignError, match="cannot branch"):
        polyalign.align(_level(a), ["T:0", "T:1", "T:2", "T:3"], "run")


def test_run_connectivity_two_disjoint_chains():
    # Two separate 2-face chains: four degree-1 ends, no branch — caught only by the connectivity
    # check (§2.4.1 step 5).
    a = _brush_from_quads("D", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)],       # chain A: 0-1
        [(0, 200, 0), (64, 200, 0), (64, 264, 0), (0, 264, 0)],
        [(64, 200, 0), (128, 200, 0), (128, 264, 0), (64, 264, 0)]])  # chain B: 2-3
    with pytest.raises(polyalign.PolyAlignError, match="not one connected run"):
        polyalign.align(_level(a), ["D:0", "D:1", "D:2", "D:3"], "run")


def test_run_terminal_faces_open_three_face_run():
    # On a 3-face open run the root's far edge maps to U=0 and the last face's far edge to U=total
    # chord (terminal-face rule, §2.4.2).
    a = _brush_from_quads("R", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)],
        [(128, 0, 0), (192, 0, 0), (192, 64, 0), (128, 64, 0)]])
    polyalign.align(_level(a), ["R:0", "R:1", "R:2"], "run")
    # root far edge (x=0) → U≈0; last far edge (x=192) → U≈192 (3 × 64 chord)
    u_root = polyalign.face_uv(a, a.brush.polys[0], (0, 32, 0))[0]
    u_last = polyalign.face_uv(a, a.brush.polys[2], (192, 32, 0))[0]
    assert abs(u_root) < 1e-3
    assert abs(abs(u_last - u_root) - 192.0) < 1e-2


def test_run_non_quad_rejected_but_after_the_branch_check():
    # A triangle in the set exits 2 naming it; but a cylinder+cap set still reports the BRANCH error
    # (with the --item Side hint), because step 6 runs AFTER step 4 (§2.4.1 step 6 ordering).
    tri = _brush_from_quads("Q", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)]])
    tri.brush.polys.append(__import__("uedcli.model", fromlist=["Polygon"]).Polygon(
        vertices=[(0.0, 0.0, 0.0), (0.0, 64.0, 0.0), (0.0, 0.0, 64.0)]))   # a stray triangle (idx 2)
    with pytest.raises(polyalign.PolyAlignError, match="non-quad"):
        polyalign.align(_level(tri), ["Q:0", "Q:1", "Q:2"], "run")
    # cylinder + cap: the branch check fires first, so the hint is what the author sees
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    sides = polyalign.find_faces(a, "Tower", item="Side")
    cap = polyalign.find_faces(a, "Tower", item="Cap")[0]
    with pytest.raises(polyalign.PolyAlignError, match="cannot branch"):
        polyalign.align(_level(a), [f"Tower:{i}" for i in sides] + [f"Tower:{cap}"], "run")


def test_run_fit_perimeter_guards():
    # --fit-perimeter needs a CLOSED run and a quarter --turn (§2.4.4), else exit 2 naming why.
    a = _brush_from_quads("R", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)]])
    with pytest.raises(polyalign.PolyAlignError, match="CLOSED run"):
        polyalign.align(_level(a), ["R:0", "R:1"], "run", fit_perimeter=True)
    c = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    sides = polyalign.find_faces(c, "Tower", item="Side")
    with pytest.raises(polyalign.PolyAlignError, match="quarter --turn"):
        polyalign.align(_level(c), [f"Tower:{i}" for i in sides], "run", turn=5000, fit_perimeter=True)


def test_run_rejects_fewer_than_two_faces():
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    with pytest.raises(polyalign.PolyAlignError, match="at least 2 faces"):
        polyalign.align(_level(a), ["Tower:0"], "run")


def test_run_rejects_zero_area_face():
    # A degenerate (collinear) face is named before any walk (§2.4.1 step 2).
    a = _brush_from_quads("Z", [[(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
                                [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)]])   # collinear
    with pytest.raises(polyalign.PolyAlignError, match="zero-area"):
        polyalign.align(_level(a), ["Z:0", "Z:1"], "run")


def test_run_rejects_pair_sharing_more_than_one_edge():
    # Two identical quads share every edge — the chord is ambiguous (§2.4.1 step 2).
    q = [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)]
    a = _brush_from_quads("S", [q, list(q)])
    with pytest.raises(polyalign.PolyAlignError, match="run chord is ambiguous"):
        polyalign.align(_level(a), ["S:0", "S:1"], "run")


def test_run_rejects_edge_shared_by_more_than_two_faces():
    # Three quads meeting at one common edge (0,0,0)-(0,0,64): each pair shares only that edge, but
    # the edge belongs to three faces — not a surface strip (§2.4.1 step 3).
    a = _brush_from_quads("E", [
        [(0, 0, 0), (0, 0, 64), (64, 0, 64), (64, 0, 0)],
        [(0, 0, 0), (0, 0, 64), (0, 64, 64), (0, 64, 0)],
        [(0, 0, 0), (0, 0, 64), (-64, 0, 64), (-64, 0, 0)]])
    with pytest.raises(polyalign.PolyAlignError, match="shared by more than two faces"):
        polyalign.align(_level(a), ["E:0", "E:1", "E:2"], "run")


def test_run_rejects_an_isolated_face():
    # A connected pair plus a face touching nothing: the isolated face is its own component (§2.4.1
    # step 5 (ii)).
    a = _brush_from_quads("I", [
        [(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)],
        [(64, 0, 0), (128, 0, 0), (128, 64, 0), (64, 64, 0)],       # shares an edge with face 0
        [(0, 500, 0), (64, 500, 0), (64, 564, 0), (0, 564, 0)]])    # far away, touches nothing
    with pytest.raises(polyalign.PolyAlignError, match="not one connected run"):
        polyalign.align(_level(a), ["I:0", "I:1", "I:2"], "run")


def test_run_shear_report_excludes_a_closed_runs_open_seam(capsys):
    # The stderr report gives the worst INTERNAL seam shear; a closed cylinder's full-perimeter gap
    # (its deliberately-open seam) must NOT appear (§2.4.3).
    a = _brush("Tower", cylinder(256, 128, 8), loc=(0, 0, 0))
    sides = polyalign.find_faces(a, "Tower", item="Side")
    polyalign.align(_level(a), [f"Tower:{i}" for i in sides], "run")
    err = capsys.readouterr().err
    perim = 8 * 2 * 128 * math.sin(math.pi / 8)
    assert f"{perim:.2f}" not in err                    # the ~1567 perimeter gap is not reported
    assert "dU=0.00 dV=0.00" in err                     # internal seams are exact on a cylinder


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
    got = polyalign.find_faces(a, "W1", facing=_fs("nz:1"))
    assert len(got) == 1
    vn = query.visible_normal(a, a.brush.polys[got[0]])      # the matched face's visible normal ≈ +Z
    assert vn[2] > 0.99 and abs(vn[0]) < 0.01 and abs(vn[1]) < 0.01


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
        stack.enter_context(mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src))
        if stdin is not None:
            stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        rc = dispatch(args)
    return rc, src


def test_dispatch_poly_find_prints_selectors(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", names=["Tower"],
                           item="Side", facing=None, texture=None, json=False, container="c")
    rc, _ = _run(args, _level(a))
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.splitlines() == [f"Tower:{i}" for i in range(6)]
    assert "6 face(s) matched" in out.err          # summary → stderr, selectors → stdout


def test_dispatch_poly_find_json(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", names=["Tower"],
                           item="Cap", facing=None, texture=None, json=True, container="c")
    rc, _ = _run(args, _level(a))
    import json as _json
    rows = _json.loads(capsys.readouterr().out)
    assert [r["poly"] for r in rows] == [6, 7] and all(r["item"] == "Cap" for r in rows)


def test_dispatch_poly_find_bad_facing_exit2(capsys):
    a = _brush("Tower", cylinder(256, 128, 6))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", names=["Tower"],
                           item=None, facing="up", texture=None, json=False, container="c")
    rc, _ = _run(args, _level(a))
    assert rc == 2 and "unknown preset 'up'" in capsys.readouterr().err


def test_dispatch_poly_find_unknown_brush_exit2(capsys):
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="find", names=["Nope"],
                           item=None, facing=None, texture=None, json=False, container="c")
    rc, _ = _run(args, _level(_brush("Tower", cube(8, 8, 8))))
    assert rc == 2 and "Actor not found: Nope" in capsys.readouterr().err


def _find_args(names, **over):
    kw = dict(cmd="brush", sub="poly", polysub="find", names=list(names),
              item=None, facing=None, texture=None, json=False, container="c")
    kw.update(over)
    return SimpleNamespace(**kw)


def test_dispatch_poly_find_multi_brush_set(capsys):
    lv = _level(_brush("Wa", cube(8, 8, 8)), _brush("Wb", cube(8, 8, 8)))
    rc, _ = _run(_find_args(["Wa", "Wb"]), lv)
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.splitlines() == [f"Wa:{i}" for i in range(6)] + [f"Wb:{i}" for i in range(6)]
    assert "12 face(s) matched" in out.err


def test_dispatch_poly_find_dash_reads_stdin_and_strips_idx(capsys):
    lv = _level(_brush("Tower", cube(8, 8, 8)))
    rc, _ = _run(_find_args(["-"]), lv, stdin="Tower:2\n")   # a BRUSH:idx line → the brush, idx dropped
    out = capsys.readouterr()
    assert rc == 0 and out.out.splitlines() == [f"Tower:{i}" for i in range(6)]


def test_dispatch_poly_find_dash_empty_stdin_is_noop_exit0(capsys):
    lv = _level(_brush("Tower", cube(8, 8, 8)))
    rc, src = _run(_find_args(["-"]), lv, stdin="")
    assert rc == 0 and capsys.readouterr().out == ""


def test_dispatch_poly_find_dedupes_a_repeated_brush(capsys):
    lv = _level(_brush("Tower", cube(8, 8, 8)))
    rc, _ = _run(_find_args(["Tower", "tower"]), lv)         # case-varied repeat → one brush
    out = capsys.readouterr()
    assert rc == 0 and out.out.splitlines() == [f"Tower:{i}" for i in range(6)]


def test_dispatch_poly_find_warns_and_skips_non_brush(capsys):
    from uedcli.model import Actor
    lv = _level(_brush("Tower", cube(8, 8, 8)))
    lv.actors["P"] = Actor(name="P", cls="Engine.PathNode")
    lv.order.append("P")
    rc, _ = _run(_find_args(["Tower", "P"]), lv)
    out = capsys.readouterr()
    assert rc == 0                                           # the run still succeeds for the brush
    assert out.out.splitlines() == [f"Tower:{i}" for i in range(6)]
    assert "skipping non-brush actor: P" in out.err


def test_dispatch_poly_find_json_has_normal_orientation_role(capsys):
    lv = _level(_brush("Tower", cube(8, 8, 8)))
    rc, _ = _run(_find_args(["Tower"], facing="floor", json=True), lv)
    import json as _json
    rows = _json.loads(capsys.readouterr().out)
    assert rc == 0 and len(rows) == 1                        # the one up-facing cap
    assert rows[0]["role"] == "floor" and rows[0]["orientation"] == "flat"
    assert rows[0]["normal"] == [0.0, 0.0, 1.0]


def test_dispatch_poly_align_positional_saves(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    sides = [f"Tower:{i}" for i in range(8)]
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=sides,
                           align_mode="run", fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a))
    assert rc == 0
    assert src.save.call_args.kwargs["touched"] == ["Tower"]     # touched stays the brush-name list
    # Ruling 2: stdout is the per-face BRUSH:idx selectors it acted on, not the brush name.
    assert capsys.readouterr().out.split() == [f"Tower:{i}" for i in range(8)]


def test_dispatch_poly_align_reads_stdin_selectors(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    stdin = "".join(f"Tower:{i}\n" for i in range(8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-"],
                           align_mode="run", fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin=stdin)
    assert rc == 0 and src.save.called


def test_dispatch_poly_align_empty_stdin_noop(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-"],
                           align_mode="run", fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin="")
    assert rc == 0 and not src.save.called          # clean no-op, nothing written


def test_dispatch_poly_align_mixing_stdin_and_names_exit2(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=["-", "Tower:0"],
                           align_mode="run", fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a), stdin="Tower:1\n")
    assert rc == 2 and not src.save.called          # `-` is the sole source; mixing is exit 2


def test_dispatch_poly_align_error_exit2_no_save(capsys):
    a = _brush("Tower", cylinder(256, 128, 8))
    tokens = [f"Tower:{i}" for i in range(8)] + ["Tower:8"]   # sides + a cap → the run branches
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="align", targets=tokens,
                           align_mode="run", turn=0, fit_perimeter=False, container="c")
    rc, src = _run(args, _level(a))
    assert rc == 2 and not src.save.called
    assert "cannot branch" in capsys.readouterr().err


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
    U-advance uses (dev/docs/direction/conventions.md 2026-07-18 21:40 UTC). Measured from the builder's own geometry,
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
    `brush poly find --facing +Z | brush poly align floor -` then `level materialize` aborted
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
    f = polyalign.find_faces(a, "Box", facing=_fs("nz:1"))[0]
    assert a.brush.polys[f].pan is None                    # a built cube has no Pan anywhere
    polyalign.align(lv, [f"Box:{f}"], "floor")
    assert "Pan" not in canonical_actor_t3d(a)             # …and aligning must not invent one
    d = StubDefaults()
    assert compare_view(_editor_reexport(lv), defaults=d) == compare_view(lv, defaults=d)


# The counterpart guard — that a non-zero Pan reaches the trunk — moved to `brush poly pan --to`
# (the only verb left that writes a non-zero pan) when ruling 8 made every `align` mode zero it:
# see test_surface.py::test_apply_pan_to_a_non_zero_value_reaches_the_trunk.
