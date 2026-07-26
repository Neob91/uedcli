from decimal import Decimal

import pytest

from uedcli.builders import cube
from uedcli.geometry import GeometryError
from uedcli.model import Brush, Polygon
from uedcli.vertex import move_vertices, weld_vertices


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def _two_triangle_quad():
    # A z=0 quad split on the (10,0,0)-(0,10,0) diagonal into two triangles; the
    # diagonal corners are SHARED by both polys (2 refs each).
    t1 = Polygon(vertices=[_D(0, 0, 0), _D(10, 0, 0), _D(0, 10, 0)])
    t2 = Polygon(vertices=[_D(10, 0, 0), _D(10, 10, 0), _D(0, 10, 0)])
    return Brush(model_name="M", polys=[t1, t2])


def test_weld_cube_has_8_corners_each_shared_by_3_polys():
    welds = weld_vertices(cube(64, 64, 64))
    assert len(welds) == 8
    assert all(len(w.refs) == 3 for w in welds)


def test_move_returns_new_brush_leaving_original_unchanged():
    b = cube(64, 64, 64)
    before = [list(p.vertices) for p in b.polys]
    move_vertices(b, [_D(-32, -32, 32), _D(32, -32, 32)], by=_D(0, 0, 16))
    assert [list(p.vertices) for p in b.polys] == before


def test_move_by_raising_a_top_edge_stays_valid_and_watertight():
    moved = move_vertices(cube(64, 64, 64), [_D(-32, -32, 32), _D(32, -32, 32)], by=_D(0, 0, 16))
    welds = weld_vertices(moved)
    coords = {w.coord for w in welds}
    assert len(welds) == 8
    assert _D(-32, -32, 48) in coords and _D(32, -32, 48) in coords
    assert _D(-32, -32, 32) not in coords and _D(32, -32, 32) not in coords
    # the relocated corners are still each shared by 3 faces (solid stays closed)
    for w in welds:
        if w.coord in {_D(-32, -32, 48), _D(32, -32, 48)}:
            assert len(w.refs) == 3


def test_move_single_cube_corner_is_rejected_as_non_planar():
    with pytest.raises(GeometryError):
        move_vertices(cube(64, 64, 64), [_D(-32, -32, 32)], by=_D(0, 0, 16))


def test_move_to_updates_every_poly_sharing_the_corner():
    moved = move_vertices(_two_triangle_quad(), [_D(10, 0, 0)], to=_D(12, 0, 0))
    welds = weld_vertices(moved)
    coords = {w.coord for w in welds}
    assert _D(12, 0, 0) in coords and _D(10, 0, 0) not in coords
    shared = next(w for w in welds if w.coord == _D(12, 0, 0))
    assert len(shared.refs) == 2


def test_move_to_requires_exactly_one_at_selector():
    with pytest.raises(ValueError, match="single|one"):
        move_vertices(cube(64, 64, 64), [_D(-32, -32, 32), _D(32, -32, 32)], to=_D(0, 0, 0))


def test_move_selector_matching_no_corner_raises_with_value():
    with pytest.raises(ValueError, match="9999"):
        move_vertices(cube(64, 64, 64), [_D(9999, 0, 0)], by=_D(0, 0, 16))


def test_move_requires_exactly_one_of_to_by():
    with pytest.raises(ValueError):
        move_vertices(cube(64, 64, 64), [_D(-32, -32, 32)])
    with pytest.raises(ValueError):
        move_vertices(cube(64, 64, 64), [_D(-32, -32, 32)], to=_D(0, 0, 0), by=_D(0, 0, 1))
