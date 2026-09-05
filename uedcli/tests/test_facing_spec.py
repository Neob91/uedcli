"""`brush poly find --facing` grammar + the visible-normal math it predicates on.

Covers: the grammar parser (presets, ranges, OR-lists, AND-terms, and every error path), the
`match_facing`/`orientation`/`role` predicates, the inverse-transpose visible normal under
non-uniform scale, and the SUBTRACT-brush normal-flip pinned against `brush_subtract.t3d`.
"""
from __future__ import annotations

import pytest

from uedcli import query
from uedcli.facing_spec import match_facing, orientation, parse_facing_spec, role
from uedcli.model import parse_t3d_actors


def _fixture(name):
    import pathlib
    return pathlib.Path(__file__).parent / "fixtures" / name


# ── grammar: valid ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec,normal,expected", [
    ("floor", (0, 0, 1), True), ("floor", (0, 0, -1), False),
    ("ceiling", (0, 0, -1), True), ("ceiling", (0, 0, 1), False),
    ("flat", (0, 0, 1), True), ("flat", (0, 0, -1), True), ("flat", (1, 0, 0), False),
    ("wall", (1, 0, 0), True), ("wall", (0, 0, 1), False),
    ("nz:-1,1", (0, 0, 1), True), ("nz:-1,1", (0, 0, -1), True), ("nz:-1,1", (1, 0, 0), False),
    ("nx:1", (1, 0, 0), True), ("nx:1", (0, 1, 0), False),
    ("nz:-0.5..0.5", (0, 0, 0.3), True), ("nz:-0.5..0.5", (0, 0, 0.9), False),
    ("wall;ny:0.7..1", (0, 0.8, 0.05), True),        # vertical AND north-ish
    ("wall;ny:0.7..1", (0.8, 0, 0.05), False),       # vertical but not north
    ("nz:0", (0, 0, 0.04), True), ("nz:0", (0, 0, 0.1), False),   # scalar ± EPS
])
def test_match(spec, normal, expected):
    assert match_facing(tuple(map(float, normal)), parse_facing_spec(spec)) is expected


def test_orientation_and_role():
    assert orientation((0, 0, 1)) == "flat" and role((0, 0, 1)) == "floor"
    assert orientation((0, 0, -1)) == "flat" and role((0, 0, -1)) == "ceiling"
    assert orientation((1, 0, 0)) == "wall" and role((1, 0, 0)) is None
    assert orientation((0.6, 0, 0.8)) == "ramp" and role((0.6, 0, 0.8)) is None


# ── grammar: errors (each exit-2 path names the token) ────────────────────────────

@pytest.mark.parametrize("bad,needle", [
    ("floot", "unknown preset"), ("nq:0", "unknown axis"), ("nz:", "empty value"),
    ("nz:a", "not a number"), ("nz:1..", "malformed range"), ("nz:1..2..3", "malformed range"),
    ("nz:0;;nx:1", "empty term"), ("nz:0;", "empty term"), ("", "empty term"),
])
def test_parse_errors(bad, needle):
    with pytest.raises(ValueError, match=needle):
        parse_facing_spec(bad)


def test_duplicate_axis_ands():
    # nz:0 AND nz:1 is a legal (empty-result) query, not a parse error.
    spec = parse_facing_spec("nz:0;nz:1")
    assert not match_facing((0.0, 0.0, 0.0), spec) and not match_facing((0.0, 0.0, 1.0), spec)


# ── visible normal: inverse-transpose under non-uniform scale ──────────────────────

def test_visible_normal_uses_inverse_transpose_not_forward():
    # A face with local normal ∝ (1,1,0) under MainScale diag(2,1,1). The covariant map (L⁻¹)ᵀ =
    # diag(0.5,1,1) sends it to (0.5,1,0) → |ny| ≈ 2|nx|; the WRONG forward map L would give (2,1,0)
    # → |nx| ≈ 2|ny|. Pin the ratio so a regression to the forward transform fails.
    t = ("Begin Map\nBegin Actor Class=Brush Name=D\n"
         "    MainScale=(Scale=(X=2.000000,Y=1.000000,Z=1.000000))\n"
         "    Location=(X=0,Y=0,Z=0)\n    Begin Brush Name=M\n       Begin PolyList\n"
         "         Begin Polygon\n"
         "          Vertex -32.000000,+32.000000,+0.000000\n"
         "          Vertex +32.000000,-32.000000,+0.000000\n"
         "          Vertex +32.000000,-32.000000,+96.000000\n"
         "          Vertex -32.000000,+32.000000,+96.000000\n         End Polygon\n"
         "       End PolyList\n    End Brush\n    Name=\"D\"\nEnd Actor\nEnd Map")
    a = parse_t3d_actors(t)[0]
    nx, ny, nz = query.visible_normal(a, a.brush.polys[0])
    assert abs(nz) < 1e-6
    assert abs(ny) > 1.9 * abs(nx)                    # inverse-transpose signature (not forward)


# ── subtract-brush normal flip: engine-facts regression (spec R-A; t3d.md winding) ─

def test_subtract_brush_flips_visible_normal():
    # Verified fact (two cold reviews): on `brush_subtract.t3d` (CSG_Subtract) the top cap's stored
    # outward Normal is +Z, but the VISIBLE (playable) surface is the ceiling → nz ≈ -1; the bottom
    # cap → floor nz ≈ +1. If this flip regresses, `floor`/`ceiling` silently invert on real rooms.
    a = parse_t3d_actors(_fixture("brush_subtract.t3d").read_text())[0]
    assert query.csg_is_subtract(a)
    top, bottom = query.visible_normal(a, a.brush.polys[0]), query.visible_normal(a, a.brush.polys[1])
    assert top[2] < -0.99 and role(top) == "ceiling"
    assert bottom[2] > 0.99 and role(bottom) == "floor"


def test_find_faces_floor_ceiling_on_subtract_brush():
    from uedcli import polyalign
    a = parse_t3d_actors(_fixture("brush_subtract.t3d").read_text())[0]
    assert polyalign.find_faces(a, "Brush938", facing=parse_facing_spec("floor")) == [1]
    assert polyalign.find_faces(a, "Brush938", facing=parse_facing_spec("ceiling")) == [0]


def test_degenerate_scale_brush_yields_undefined_normal_not_a_crash():
    # A collapsed scale axis makes the covariant map non-invertible. visible_normal must DEGRADE to
    # (0,0,0) — "?" orientation in `poly list` — never raise (else `list`/`find --json` traceback).
    t = ("Begin Map\nBegin Actor Class=Brush Name=Z\n"
         "    MainScale=(Scale=(X=0.000000,Y=1.000000,Z=1.000000))\n"
         "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
         "          Vertex +0.000000,+0.000000,+0.000000\n"
         "          Vertex +64.000000,+0.000000,+0.000000\n"
         "          Vertex +64.000000,+64.000000,+0.000000\n         End Polygon\n"
         "       End PolyList\n    End Brush\n    Name=\"Z\"\nEnd Actor\nEnd Map")
    a = parse_t3d_actors(t)[0]
    assert query.visible_normal(a, a.brush.polys[0]) == (0.0, 0.0, 0.0)
    assert query.list_polys(a)[0]["orientation"] == "?"      # no exception reaches the caller
