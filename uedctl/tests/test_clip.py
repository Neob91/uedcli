import math

import pytest

from uedctl.model import Brush, Polygon
from uedctl.geometry import GeometryError
from uedctl.clip import clip_brush, classify_clip, axis_plane, _signed_dist


def _cube(h=100.0):
    """A unit-textured cube brush of half-extent h, CCW-from-outside winding."""
    faces = [
        [(h, -h, -h), (h, h, -h), (h, h, h), (h, -h, h)],      # +X
        [(-h, h, -h), (-h, -h, -h), (-h, -h, h), (-h, h, h)],  # -X
        [(h, h, -h), (-h, h, -h), (-h, h, h), (h, h, h)],      # +Y
        [(-h, -h, -h), (h, -h, -h), (h, -h, h), (-h, -h, h)],  # -Y
        [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)],      # +Z
        [(-h, h, -h), (h, h, -h), (h, -h, -h), (-h, -h, -h)],  # -Z
    ]
    return Brush(model_name="Brush",
                 polys=[Polygon(flags=0, texture="T", vertices=f) for f in faces])


def _newell_normal(verts):
    nx = ny = nz = 0.0
    m = len(verts)
    for i in range(m):
        a = [float(c) for c in verts[i]]                 # clip now returns Decimal verts
        b = [float(c) for c in verts[(i + 1) % m]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def test_clip_cone_on_slanted_face_stays_planar_with_fractions_preserved():
    # Regression for the cone-clip non-planar failure: a cone's side faces are
    # slanted, and the OLD integer grid-snap pushed clipped cut points off their
    # tilted plane (vertex ~0.865 off, tol 0.5). Preserving fractions keeps them
    # planar, so the clip validates instead of raising.
    from uedctl.builders import cone

    out = clip_brush(cone(height=100, radius=100, sides=8), *axis_plane("z", 0),
                     keep_negative=True)
    assert len(out.polys) >= 4          # frustum faces + a cap, no GeometryError


def test_axis_plane_helper():
    p, n = axis_plane("z", 128)
    assert p == (0.0, 0.0, 128.0)
    assert n == (0.0, 0.0, 1.0)


def test_clip_cube_keeps_negative_half_and_caps():
    cube = _cube(100)
    point, normal = axis_plane("x", 0)
    out = clip_brush(cube, point, normal, keep_negative=True)
    # +X face dropped, -X kept, 4 side faces truncated, +1 cap = 6 polys
    assert len(out.polys) == 6
    # every vertex is on the kept side (x <= 0, within tolerance)
    for poly in out.polys:
        for vx, _, _ in poly.vertices:
            assert vx <= 1e-3
    # exactly one cap face: all verts at x≈0
    caps = [p for p in out.polys if all(abs(v[0]) < 1e-3 for v in p.vertices)]
    assert len(caps) == 1
    assert len(caps[0].vertices) == 4


def test_clip_cap_winding_normal_points_outward():
    cube = _cube(100)
    point, normal = axis_plane("x", 0)
    out = clip_brush(cube, point, normal, keep_negative=True)
    cap = next(p for p in out.polys if all(abs(v[0]) < 1e-3 for v in p.vertices))
    n = _newell_normal(cap.vertices)
    # cap faces OUT of the kept (x<=0) solid → +X
    assert n[0] > 0
    # texture vectors are non-degenerate (zero-length texU/V would crash REBUILD)
    assert math.sqrt(sum(c * c for c in cap.texture_u)) > 0.5
    assert math.sqrt(sum(c * c for c in cap.texture_v)) > 0.5


def test_clip_keep_positive_half():
    cube = _cube(100)
    point, normal = axis_plane("x", 0)
    out = clip_brush(cube, point, normal, keep_negative=False)
    for poly in out.polys:
        for vx, _, _ in poly.vertices:
            assert vx >= -1e-3
    cap = next(p for p in out.polys if all(abs(v[0]) < 1e-3 for v in p.vertices))
    assert _newell_normal(cap.vertices)[0] < 0          # faces out toward -X


def test_clip_plane_outside_keeps_whole_brush_no_cap():
    cube = _cube(100)
    point, normal = axis_plane("x", 1000)               # far beyond the cube
    out = clip_brush(cube, point, normal, keep_negative=True)
    assert len(out.polys) == 6                           # untouched, no cap added


def test_clip_removing_whole_brush_raises():
    cube = _cube(100)
    point, normal = axis_plane("x", -1000)               # keep x <= -1000 → nothing
    with pytest.raises(GeometryError, match="removed the entire brush"):
        clip_brush(cube, point, normal, keep_negative=True)


def test_clip_diagonal_plane_validates_and_caps():
    cube = _cube(100)
    # cut a corner with a diagonal plane through the origin
    out = clip_brush(cube, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), keep_negative=True)
    assert len(out.polys) >= 4
    # all kept vertices satisfy x+y+z <= 0 (within tolerance)
    for poly in out.polys:
        for v in poly.vertices:
            assert _signed_dist(v, (0, 0, 0), (1, 1, 1)) <= 1.0
    # a cap exists (the diagonal cross-section) — a poly lying on x+y+z≈0
    caps = [p for p in out.polys
            if all(abs(_signed_dist(v, (0, 0, 0), (1, 1, 1))) < 1.0 for v in p.vertices)]
    assert caps


def test_classify_clip_detects_a_plane_that_misses_the_interior():
    # Board bug 4: a plane sitting on/outside a corner leaves the whole brush on one side. classify
    # returns 'whole' (a no-op the dispatcher reports) rather than silently clipping nothing.
    cube = _cube(100)
    assert classify_clip(cube, *axis_plane("x", 500), keep_negative=True) == "whole"   # all x<=100
    assert classify_clip(cube, *axis_plane("x", 100), keep_negative=True) == "whole"   # tangent
    # A plane through the middle really cuts:
    assert classify_clip(cube, *axis_plane("x", 0), keep_negative=True) == "clips"
    # Everything on the discarded side → 'empty' (clip_brush raises for this one):
    assert classify_clip(cube, *axis_plane("x", -500), keep_negative=True) == "empty"


def test_clip_zero_normal_raises():
    with pytest.raises(GeometryError):
        clip_brush(_cube(100), (0, 0, 0), (0, 0, 0))


def test_clip_brush_accepts_decimal_vertex_brushes():
    # Model brushes carry Decimal vertices (make_brush_actor finalizes via emit.clean); clip computes
    # in float, so it must coerce them. It used to TypeError (Decimal − float) on any real brush.
    from decimal import Decimal
    from uedctl.builders import cube as build_cube, make_brush_actor
    brush = make_brush_actor("B", build_cube(64, 64, 64),
                             location=(Decimal(0), Decimal(0), Decimal(0))).brush
    assert any(isinstance(c, Decimal) for c in brush.polys[0].vertices[0])   # precondition
    out = clip_brush(brush, *axis_plane("z", 0), keep_negative=True)
    assert len(out.polys) == 6                            # 5 truncated/kept faces + 1 cap


def test_clip_brush_accepts_decimal_point_and_normal():
    # The `--plane` CLI path parses point/normal as Decimal (parse_coord); clip must coerce them too
    # (the Decimal normal used to crash _normalize at `Decimal * float`).
    from decimal import Decimal
    out = clip_brush(_cube(100), (Decimal(0), Decimal(0), Decimal(0)),
                     (Decimal(0), Decimal(0), Decimal(1)), keep_negative=True)
    assert len(out.polys) == 6
