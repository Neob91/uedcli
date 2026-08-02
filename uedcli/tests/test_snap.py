"""`uedcli.snap.snap_brush` — round near-grid LOCAL vertex components to a grid (model-side).

The CLI filter (`brush snap`) is exercised by `test_brush_snap.py`; here the concern is the pure
snap math: per-axis/per-vertex independence, the round-half-toward-+inf boundary, re-weld,
idempotence, and the non-planar refusal.
"""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from uedcli import builders
from uedcli.geometry import GeometryError
from uedcli.model import Brush, Polygon
from uedcli.snap import snap_brush
from uedcli.vertex import weld_vertices


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def _flat_quad(*verts) -> Brush:
    # A single z=0 polygon — validate_brush checks each poly independently (planarity/coincidence/
    # degeneracy), so one planar face is enough to exercise snapping without a closed solid.
    return Brush(model_name="M", polys=[Polygon(vertices=[_D(*v) for v in verts])])


def _decimal_cube(delta: Decimal) -> Brush:
    # An exact Decimal cube (corners at ±64, all multiples of 16), each component offset by `delta`.
    src = builders.cube(128, 128, 128)
    polys = []
    for p in src.polys:
        np = copy.deepcopy(p)
        np.vertices = [tuple(Decimal(str(c)) + delta for c in v) for v in p.vertices]
        polys.append(np)
    return Brush(model_name=src.model_name, polys=polys)


def test_it_snaps_near_integer_noise_to_the_exact_grid():
    snapped = snap_brush(_decimal_cube(Decimal("0.0001")), grid=Decimal(1), tolerance=Decimal("0.01"))
    comps = {c for p in snapped.polys for v in p.vertices for c in v}
    assert comps == {Decimal(-64), Decimal(64)}


def test_it_snaps_per_axis_leaving_a_genuinely_offgrid_axis_in_place():
    # x=8.5 is 7.5 from the nearest grid line (16) — far beyond tolerance, so it survives; the
    # near-grid y and z on the same vertex snap. Per-axis independence.
    b = _flat_quad((8.5, 16.0001, 0), (48, 16.0001, 0), (48, 48, 0), (8.5, 48, 0))
    snapped = snap_brush(b, grid=Decimal(16), tolerance=Decimal("0.01"))
    assert snapped.polys[0].vertices[0] == _D(8.5, 16, 0)


def test_it_snaps_a_noisy_component_but_leaves_a_real_halfgrid_value():
    # grid 16: 15.9997 -> 16 (noise); 8.5 stays (7.5 from 16, past tolerance).
    b = _flat_quad((15.9997, 8.5, 0), (48, 8.5, 0), (48, 48, 0), (16, 48, 0))
    snapped = snap_brush(b, grid=Decimal(16), tolerance=Decimal("0.01"))
    assert snapped.polys[0].vertices[0] == _D(16, 8.5, 0)


def test_it_rounds_half_toward_positive_infinity_at_the_boundary():
    # A component exactly grid/2 from a line, within tolerance: 0.5 -> 1 and -0.5 -> 0 (both the
    # +inf choice), never 0 / -1. floor(x + 0.5), not banker's round().
    b = _flat_quad((0.5, -0.5, 0), (5, -0.5, 0), (5, 5, 0), (0.5, 5, 0))
    snapped = snap_brush(b, grid=Decimal(1), tolerance=Decimal("0.5"))
    assert snapped.polys[0].vertices[0] == _D(1, 0, 0)


def test_it_rewelds_drifted_copies_of_a_corner_onto_one_grid_point():
    # Two triangles share the (0,10,0) corner; the (10,0,0) corner drifted to (10.02,-0.02,0) in the
    # second, so pre-snap it is a SEPARATE welded corner. Both copies snap onto (10,0,0) — re-weld.
    t1 = Polygon(vertices=[_D(0, 0, 0), _D(10, 0, 0), _D(0, 10, 0)])
    t2 = Polygon(vertices=[_D(10.02, -0.02, 0), _D(10, 10, 0), _D(0, 10, 0)])
    b = Brush(model_name="M", polys=[t1, t2])
    assert len(weld_vertices(b)) == 5                      # the two (10,0,0) copies are distinct
    snapped = snap_brush(b, grid=Decimal(1), tolerance=Decimal("0.05"))
    after = weld_vertices(snapped)
    assert len(after) == 4                                 # they welded into one corner
    assert _D(10, 0, 0) in {w.coord for w in after}


def test_it_raises_when_snapping_pushes_a_face_nonplanar():
    # A planar tilted quad (z = 0.1x + 0.1y). Its two z=1.5 vertices snap to z=2 while the z=0 and
    # z=3 vertices stay, so the four no longer share a plane — refused, not emitted.
    tilted = Brush(model_name="M", polys=[Polygon(vertices=[
        _D(0, 0, 0), _D(15, 0, 1.5), _D(15, 15, 3.0), _D(0, 15, 1.5)])])
    with pytest.raises(GeometryError):
        snap_brush(tilted, grid=Decimal(1), tolerance=Decimal("0.6"))


def test_it_leaves_an_on_grid_brush_unchanged_and_returns_a_new_brush():
    b = _decimal_cube(Decimal(0))
    before = [list(p.vertices) for p in b.polys]
    snapped = snap_brush(b, grid=Decimal(1), tolerance=Decimal("0.01"))
    assert snapped is not b
    assert [list(p.vertices) for p in snapped.polys] == before   # idempotent on an on-grid brush
    assert [list(p.vertices) for p in b.polys] == before         # original untouched
