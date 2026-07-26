from uedcli.model import parse_t3d
from uedcli.query import level_bounds, level_center


def test_level_center_is_the_bbox_midpoint_of_actor_locations():
    lv = parse_t3d(
        "Begin Map\n"
        "Begin Actor Class=Light Name=A\n    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
        "    Name=\"A\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=B\n    Location=(X=200.000000,Y=100.000000,Z=-40.000000)\n"
        "    Name=\"B\"\nEnd Actor\nEnd Map")
    assert level_center(lv) == (100.0, 50.0, -20.0)


def test_level_bounds_is_none_for_an_empty_level():
    assert level_bounds(parse_t3d("Begin Map\nEnd Map")) is None
    assert level_center(parse_t3d("Begin Map\nEnd Map")) is None


def test_level_bounds_includes_brush_vertices_offset_by_location():
    lv = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=Bx\n"
        "    Location=(X=1000.000000,Y=0.000000,Z=0.000000)\n"
        "    Begin Brush Name=Model0\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +0.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+64.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"Bx\"\nEnd Actor\nEnd Map")
    x0, y0, z0, x1, y1, z1 = level_bounds(lv)
    assert (x0, x1) == (1000.0, 1064.0)        # vertices are local → offset by Location.X


def test_level_bounds_applies_actor_rotation():
    # A 64-long brush along +X, yawed 90°, spans +Y instead of +X (bounds reflect the rotation).
    lv = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B\n"
        "    Location=(X=0,Y=0,Z=0)\n    Rotation=(Yaw=16384)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +0.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+8.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\nEnd Map")
    x0, y0, z0, x1, y1, z1 = level_bounds(lv)
    assert round(y1) == 64 and round(x1) <= 1     # +X extent rotated into +Y
