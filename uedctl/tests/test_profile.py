"""The shared 2D profile layer behind `brush build extrude` / `brush build revolve`
(`uedctl/profile.py`) — token parsing, cleanup, the non-simple-ring rejection, winding
normalization and the convex decomposition. Pure 2D: no brush, no world coordinates, no T3D."""
from decimal import Decimal

import pytest

from uedctl import profile
from uedctl.geometry import GeometryError
from uedctl.profile import ProfileError


def _P(*pairs):
    return [(Decimal(str(u)), Decimal(str(v))) for u, v in pairs]


SQUARE = _P((0, 0), (128, 0), (128, 64), (0, 64))            # CCW


# --- ProfileError is the clean-exit route -------------------------------------------------------


def test_profile_error_is_a_geometry_error():
    # dispatch() catches GeometryError and prints it without a traceback; it has NO bare
    # ValueError arm, so this subclassing is what makes every rejection below exit 2 cleanly.
    assert issubclass(ProfileError, GeometryError)


# --- parse_point ---------------------------------------------------------------------------------


def test_parse_point_reads_two_fields_exactly():
    assert profile.parse_point("128,-64.5") == (Decimal("128"), Decimal("-64.5"))


@pytest.mark.parametrize("token", ["128", "1,2,3", ",", "128,"])
def test_parse_point_rejects_a_wrong_field_count_naming_the_token(token):
    with pytest.raises(ProfileError) as e:
        profile.parse_point(token)
    assert "two comma-separated numbers" in str(e.value)
    assert repr(token) in str(e.value)


@pytest.mark.parametrize("token", ["a,b", "12,nan", "inf,0"])
def test_parse_point_rejects_a_non_numeric_or_non_finite_field(token):
    with pytest.raises(ProfileError) as e:
        profile.parse_point(token)
    assert "must be numbers" in str(e.value) and repr(token) in str(e.value)


# --- clean_profile -------------------------------------------------------------------------------


def test_clean_profile_welds_a_repeated_final_point():
    # The ring is implicitly closed, so repeating the first point as the last is harmless.
    ring = profile.clean_profile(SQUARE + [SQUARE[0]])
    assert ring == SQUARE


def test_clean_profile_welds_consecutive_near_duplicates():
    ring = profile.clean_profile(_P((0, 0), (0, 0.0001), (128, 0), (128, 64), (0, 64)))
    assert len(ring) == 4


def test_clean_profile_drops_a_collinear_midpoint():
    # (64,0) sits on the edge (0,0)→(128,0): the engine's own RemoveColinears deletes it at build
    # time, so dropping it up front keeps the emitted face count equal to the built one.
    ring = profile.clean_profile(_P((0, 0), (64, 0), (128, 0), (128, 64), (0, 64)))
    assert ring == SQUARE


def test_clean_profile_rejects_a_ring_with_fewer_than_three_distinct_points():
    with pytest.raises(ProfileError) as e:
        profile.clean_profile(_P((0, 0), (128, 0), (128, 0.0002)))
    assert "at least 3 points" in str(e.value)


# --- check_simple --------------------------------------------------------------------------------


def test_check_simple_accepts_a_plain_square():
    profile.check_simple(SQUARE)              # no raise


def test_check_simple_accepts_a_concave_l():
    profile.check_simple(_P((0, 0), (96, 0), (96, 32), (32, 32), (32, 96), (0, 96)))


def test_check_simple_rejects_a_bowtie():
    with pytest.raises(ProfileError) as e:
        profile.check_simple(_P((0, 0), (128, 128), (128, 0), (0, 128)))
    assert "not simple" in str(e.value)


def test_check_simple_rejects_a_pinch_where_non_adjacent_edges_touch():
    # Edge 3 (0,64)→(64,0) ENDS on edge 0's interior point (64,0)… a touch, not a crossing, so a
    # strict "proper crossing" test would wave it through.
    with pytest.raises(ProfileError) as e:
        profile.check_simple(_P((0, 0), (128, 0), (128, 64), (64, 0), (0, 64)))
    assert "not simple" in str(e.value) and "edge" in str(e.value)


def test_check_simple_rejects_collinear_overlapping_edges():
    with pytest.raises(ProfileError):
        profile.check_simple(_P((0, 0), (128, 0), (64, 0), (64, 64)))


def test_check_simple_rejects_a_vertex_repeated_non_consecutively():
    # `A B C A D E` — a figure-eight that a consecutive-only weld AND a strict crossing test both
    # miss, because the ring merely revisits a point.
    a, b, c, d, e = (0, 0), (128, 0), (128, 64), (64, -64), (0, -64)
    with pytest.raises(ProfileError) as err:
        profile.check_simple(_P(a, b, c, a, d, e))
    assert "same vertex" in str(err.value)


# --- normalize_winding ---------------------------------------------------------------------------


def test_normalize_winding_keeps_a_ccw_ring_and_flips_a_cw_one():
    assert profile.normalize_winding(SQUARE) == SQUARE
    assert profile.normalize_winding(list(reversed(SQUARE))) == SQUARE


def test_normalize_winding_rejects_a_zero_area_ring():
    with pytest.raises(ProfileError) as e:
        profile.normalize_winding(_P((0, 0), (64, 0), (128, 0), (64, 0)))
    assert "zero area" in str(e.value)


def test_signed_area_is_exact_for_decimal_input():
    assert profile.signed_area(SQUARE) == Decimal("8192")


# --- convex_pieces -------------------------------------------------------------------------------


def test_convex_pieces_passes_a_convex_ring_through_as_one_piece():
    # THE invariant: a convex ≤16-vertex profile decomposes to exactly ONE piece, so a plain box
    # still emits exactly two cap faces.
    assert profile.convex_pieces(SQUARE) == [SQUARE]


def _assert_well_formed_tiling(ring, pieces):
    """Every piece convex and within the engine's FPoly bound; the pieces cover exactly the ring's
    own vertices (no new ones); and every piece edge is either an ORIGINAL ring edge or a DIAGONAL
    shared by exactly two pieces — the no-T-junction property that keeps the swept solid
    watertight."""
    assert len(pieces) > 1
    for piece in pieces:
        assert profile.is_convex(piece), piece
        assert 3 <= len(piece) <= profile.MAX_FPOLY_VERTS
    assert {tuple(p) for piece in pieces for p in piece} == {tuple(p) for p in ring}
    ring_edges = {(tuple(ring[i]), tuple(ring[(i + 1) % len(ring)])) for i in range(len(ring))}
    directed = [(tuple(piece[i]), tuple(piece[(i + 1) % len(piece)]))
                for piece in pieces for i in range(len(piece))]
    assert len(directed) == len(set(directed)), "a directed edge is used twice"
    for e in directed:
        assert e in ring_edges or (e[1], e[0]) in directed, f"edge {e} is neither boundary nor diagonal"


L_PROFILE = _P((0, 0), (96, 0), (96, 32), (32, 32), (32, 96), (0, 96))


def test_convex_pieces_tiles_a_concave_l_into_convex_pieces():
    pieces = profile.convex_pieces(L_PROFILE)
    _assert_well_formed_tiling(L_PROFILE, pieces)
    # Hertel–Mehlhorn merging must beat plain ear-clip triangles (n−2 = 4 of them here): an L is
    # two convex quads.
    assert len(pieces) == 2


def test_convex_pieces_splits_a_ring_longer_than_the_fpoly_bound():
    import math
    ring = _P(*[(round(100 * math.cos(2 * math.pi * i / 17), 6),
                 round(100 * math.sin(2 * math.pi * i / 17), 6)) for i in range(17)])
    pieces = profile.convex_pieces(ring)
    _assert_well_formed_tiling(ring, pieces)


def test_convex_pieces_tiles_a_deeply_notched_comb():
    # Several independent reflex corners, so the merge step cannot fuse everything back into one.
    comb = _P((0, 0), (128, 0), (128, 64), (96, 64), (96, 24), (72, 24),
              (72, 64), (40, 64), (40, 24), (16, 24), (16, 64), (0, 64))
    _assert_well_formed_tiling(comb, profile.convex_pieces(comb))


def test_is_convex_sees_the_notch_in_an_l():
    assert not profile.is_convex(_P((0, 0), (96, 0), (96, 32), (32, 32), (32, 96), (0, 96)))
    assert profile.is_convex(SQUARE)
