from decimal import Decimal

import pytest

from uedcli.model import Brush, parse_t3d, Polygon
from uedcli.geometry import validate_brush, GeometryError
from uedcli.tests.conftest import read_fixture


def _poly(verts):
    return Polygon(vertices=verts)


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def test_validate_accepts_subgrid_distinct_vertices():
    # Two corners 0.4 apart are DISTINCT once fractions are preserved; the old
    # int-grid snap would collapse them and wrongly raise "coincide".
    b = Brush(model_name="M", polys=[_poly([_D(0, 0, 0), _D(0.4, 0, 0), _D(0, 10, 0)])])
    validate_brush(b)  # must not raise


def test_validate_flags_vertices_within_clean_eps_as_coincident():
    # 0.0005 is within CLEAN_EPS of 0 -> cleans onto the first vertex -> coincident.
    b = Brush(model_name="M", polys=[_poly([_D(0, 0, 0), _D(0.0005, 0, 0), _D(0, 10, 0)])])
    with pytest.raises(GeometryError, match="coincide"):
        validate_brush(b)


def test_validate_accepts_planar_slanted_fractional_face():
    # A tilted face whose vertices are genuinely fractional stays planar when the
    # fractions are preserved (the cone-clip non-planar failure mode).
    b = Brush(model_name="M", polys=[_poly([
        _D(0, 0, 0), _D(10, 0, "3.333333"), _D(10, 10, "3.333333"), _D(0, 10, 0)])])
    validate_brush(b)  # must not raise


def test_valid_cube_passes():
    a = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]
    validate_brush(a.brush)  # no raise


def test_coincident_vertices_rejected():
    b = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"].brush
    b.polys[0].vertices[2] = b.polys[0].vertices[1]  # collapse two verts
    with pytest.raises(GeometryError, match="coincide"):
        validate_brush(b)


def test_collinear_face_rejected():
    b = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"].brush
    b.polys[0].vertices = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (30.0, 0.0, 0.0)]
    with pytest.raises(GeometryError, match="degenerate|collinear"):
        validate_brush(b)


def test_nonplanar_face_rejected():
    b = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"].brush
    p = b.polys[0]
    p.vertices = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0), (0.0, 100.0, 50.0)]
    with pytest.raises(GeometryError, match="non-planar|planar"):
        validate_brush(b)


def test_shared_corner_across_polys_is_ok():
    # cube corners are shared across faces — must NOT be flagged
    a = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]
    validate_brush(a.brush)  # already shares corners; no raise
