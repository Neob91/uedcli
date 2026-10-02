from decimal import Decimal

from uedcli.model import parse_t3d
from uedcli.rotation import world_vertices, actor_rotation_uu


def test_world_vertices_offsets_local_verts_by_location_when_unrotated():
    a = parse_t3d("Begin Map\nBegin Actor Class=Brush Name=B\n"
                  "    Location=(X=100.000000,Y=0,Z=0)\n"
                  "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
                  "          Vertex +0.000000,+0.000000,+0.000000\n"
                  "          Vertex +64.000000,+0.000000,+0.000000\n"
                  "          Vertex +64.000000,+64.000000,+0.000000\n         End Polygon\n"
                  "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\nEnd Map").actors["B"]
    pts = world_vertices(a)
    assert (100.0, 0.0, 0.0) in [(round(x, 3), round(y, 3), round(z, 3)) for x, y, z in pts]
    assert (164.0, 0.0, 0.0) in [(round(x, 3), round(y, 3), round(z, 3)) for x, y, z in pts]


def test_world_vertices_applies_yaw_rotation():
    # A +X-extending vertex, yawed 90°, lands on +Y in world space.
    a = parse_t3d("Begin Map\nBegin Actor Class=Brush Name=B\n"
                  "    Location=(X=0,Y=0,Z=0)\n    Rotation=(Yaw=16384)\n"
                  "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
                  "          Vertex +0.000000,+0.000000,+0.000000\n"
                  "          Vertex +64.000000,+0.000000,+0.000000\n"
                  "          Vertex +64.000000,+8.000000,+0.000000\n         End Polygon\n"
                  "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\nEnd Map").actors["B"]
    pts = [(round(x, 3), round(y, 3), round(z, 3)) for x, y, z in world_vertices(a)]
    assert (0.0, 64.0, 0.0) in pts          # (64,0,0) → (0,64,0)


def test_actor_rotation_uu_defaults_to_identity_when_absent():
    a = parse_t3d("Begin Map\nBegin Actor Class=Light Name=L\n    Name=\"L\"\nEnd Actor\nEnd Map").actors["L"]
    assert actor_rotation_uu(a) == (0, 0, 0)


def test_actor_rotation_uu_parses_single_axis_with_omitted_components():
    a = parse_t3d("Begin Map\nBegin Actor Class=Light Name=L\n"
                  "    Rotation=(Yaw=16384)\n    Name=\"L\"\nEnd Actor\nEnd Map").actors["L"]
    assert actor_rotation_uu(a) == (0, 16384, 0)


def test_actor_rotation_uu_normalizes_a_full_turn_to_identity():
    # A full turn (orientation-identical to identity) must read as (0,0,0) so the identity gates
    # (actor_matrix fast-path + the clip/vertex guard) aren't fooled.
    a = parse_t3d("Begin Map\nBegin Actor Class=Light Name=L\n"
                  "    Rotation=(Yaw=65536)\n    Name=\"L\"\nEnd Actor\nEnd Map").actors["L"]
    assert actor_rotation_uu(a) == (0, 0, 0)
