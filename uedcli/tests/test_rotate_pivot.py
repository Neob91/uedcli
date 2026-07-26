from decimal import Decimal

from uedcli.model import parse_t3d
from uedcli.rotation import best_grid_pivot


def _lvl(t3d):
    return list(parse_t3d("Begin Map\n" + t3d + "End Map\n").actors.values())


def test_best_grid_pivot_prefers_the_highest_power_of_two_vertex():
    # (256,256,0) is uniquely 2^8-aligned (align 8); (255,..)=odd (0), (260,..)=4*65 (2). The
    # brush Location (0,0,0) is NOT a candidate (only world vertices), so it can't win on v2(0)=∞.
    actors = _lvl(
        "Begin Actor Class=Brush Name=B\n    Location=(X=0,Y=0,Z=0)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +255.000000,+0.000000,+0.000000\n"
        "          Vertex +256.000000,+256.000000,+0.000000\n"
        "          Vertex +260.000000,+0.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal(256), Decimal(256), Decimal(0))


def test_best_grid_pivot_falls_back_to_bbox_centre_when_all_fractional():
    actors = _lvl(
        "Begin Actor Class=Light Name=L1\n    Location=(X=10.500000,Y=0.500000,Z=0.500000)\n    Name=\"L1\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=L2\n    Location=(X=20.500000,Y=0.500000,Z=0.500000)\n    Name=\"L2\"\nEnd Actor\n")
    px, py, pz = best_grid_pivot(actors)
    assert (round(float(px)), round(float(py)), round(float(pz))) == (16, 0, 0)   # bbox centre, grid-snapped


def test_best_grid_pivot_prefers_the_bbox_centre_on_a_total_align_tie():
    """The ContainerYard case: a 128x128 XZ sheet at Y=228. v2(228)=2 caps EVERY candidate's align,
    and all four corners are equidistant from the centre — a total tie that used to fall through to
    the lexicographic tiebreak and return the MIN CORNER (992,228,48), swinging the sheet a full
    128 uu sideways. The centre is a candidate and wins the tie, so the flip is in place."""
    actors = _lvl(
        "Begin Actor Class=Brush Name=S\n    Location=(X=0,Y=0,Z=0)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +992.000000,+228.000000,+48.000000\n"
        "          Vertex +1120.000000,+228.000000,+48.000000\n"
        "          Vertex +1120.000000,+228.000000,+176.000000\n"
        "          Vertex +992.000000,+228.000000,+176.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"S\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal(1056), Decimal(228), Decimal(112))


def test_best_grid_pivot_still_prefers_a_strictly_more_aligned_vertex_over_the_centre():
    """Align dominates the centre — that is what keeps rotated geometry on the power-of-two grid.
    Vertices span 0..96 on X, so the centre X=48 scores v2=4 while the vertex at 0 scores 64."""
    actors = _lvl(
        "Begin Actor Class=Brush Name=B\n    Location=(X=0,Y=0,Z=0)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +0.000000,+0.000000,+0.000000\n"
        "          Vertex +96.000000,+0.000000,+0.000000\n"
        "          Vertex +96.000000,+96.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal(0), Decimal(0), Decimal(0))


def test_best_grid_pivot_ignores_a_fractional_centre():
    """A fractional centre scores _v2 = -1 and must not beat an on-grid vertex: vertices at X 0 and
    X 65 put the centre at 32.5, which would take on-grid geometry off-grid if used as the pivot."""
    actors = _lvl(
        "Begin Actor Class=Brush Name=B\n    Location=(X=0,Y=0,Z=0)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +0.000000,+0.000000,+0.000000\n"
        "          Vertex +65.000000,+0.000000,+0.000000\n"
        "          Vertex +65.000000,+64.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal(0), Decimal(0), Decimal(0))


def test_best_grid_pivot_uses_point_actor_locations():
    actors = _lvl(
        "Begin Actor Class=Light Name=L1\n    Location=(X=128.000000,Y=128.000000,Z=0.000000)\n    Name=\"L1\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=L2\n    Location=(X=130.000000,Y=2.000000,Z=0.000000)\n    Name=\"L2\"\nEnd Actor\n")
    # L1 (128,128,0): align 7; L2 (130,2,0): min(v2(130)=1,v2(2)=1)=1. L1 wins.
    assert best_grid_pivot(actors) == (Decimal(128), Decimal(128), Decimal(0))
