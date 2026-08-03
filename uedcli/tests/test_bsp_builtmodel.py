"""Pins for the built-model located BSP check (invisible walls + fall-through).

The committed golden `endgame4_model1.bin` is the built `Model1` body of retail `99_Endgame4.dx`
(a clean map) — it must locate NOTHING. The two defect cases are constructed `Model`s so the
located `Finding` can be asserted exactly.
"""
from pathlib import Path

from uedcli import doctor
from uedcli.bsp import builtmodel as B
from uedcli.builders import PF_NOTSOLID, PF_SEMISOLID
from uedcli.native.umodel import Model, BspNode, BspSurf, BspVert, parse_model_body

_GOLDEN = Path(__file__).resolve().parents[2] / "dev/docs/spikes/bspspike/fixtures/endgame4_model1.bin"
_REAL_DX = Path(__file__).resolve().parent / "fixtures/map_import_bounds/paste.dx"


def test_load_model_from_dx_locates_the_level_model_in_a_real_map():
    """`load_model_from_dx` end-to-end over a real saved `.dx`: parse the package, pick the largest
    Model export, parse its body. (The golden test above feeds a raw body, bypassing this locator;
    every other test stubs it — so without this the package-parse + Model-selection path is
    unexercised.) The RF_HasStack state-frame-skip branch stays uncovered — no in-repo `.dx` fixture
    carries a HasStack Model — so this pins the common path, not that branch."""
    m = B.load_model_from_dx(_REAL_DX.read_bytes())
    assert (len(m.nodes), len(m.surfs)) == (16, 10)
    assert B.analyze_built(m) == []                   # this fixture is a clean solid build


def test_it_parses_the_golden_built_model():
    m = parse_model_body(_GOLDEN.read_bytes(), 0, len(_GOLDEN.read_bytes()))
    assert (len(m.nodes), len(m.surfs), len(m.verts), len(m.points)) == (46, 31, 741, 73)


def test_it_locates_no_defects_in_a_clean_retail_map():
    m = parse_model_body(_GOLDEN.read_bytes(), 0, len(_GOLDEN.read_bytes()))
    assert B.analyze_built(m) == []               # no false positives on a real clean build


def test_it_locates_a_near_zero_area_node_as_an_invisible_wall():
    # three near-coincident points → a node polygon of ~zero area (a phantom/sliver node).
    m = Model(points=[(128.0, 64.0, 0.0), (128.000004, 64.0, 0.0), (128.000008, 64.0, 0.0)],
              verts=[BspVert(i_vertex=0), BspVert(i_vertex=1), BspVert(i_vertex=2)],
              nodes=[BspNode(plane=(0.0, 0.0, 1.0, 0.0), i_vert_pool=0, num_vertices=3, i_surf=5)],
              vectors=[(0.0, 0.0, 1.0)],
              surfs=[BspSurf(poly_flags=0, v_normal=0, p_base=0)])
    findings = B.analyze_built(m)
    assert len(findings) == 1
    f = findings[0]
    assert (f.severity, f.category, f.brush) == (doctor.Severity.WARN, "degenerate", "(built BSP)")
    assert "node 0 (surf 5)" in f.message and "~zero area" in f.message
    assert f.coord is not None                    # located


def test_it_locates_a_non_collidable_floor_surf_as_fall_through():
    # an upward-facing (floor) surf carrying PF_NotSolid → a pawn falls through it.
    m = Model(points=[(-256.0, -256.0, 8.0)],
              vectors=[(0.0, 0.0, 1.0)],           # normal points straight up ⇒ a floor
              surfs=[BspSurf(poly_flags=PF_NOTSOLID, v_normal=0, p_base=0)])
    findings = B.analyze_built(m)
    assert len(findings) == 1
    f = findings[0]
    assert (f.severity, f.category, f.brush) == (doctor.Severity.ERROR, "solidity", "(built BSP)")
    assert "floor surf 0" in f.message and "PF_NotSolid" in f.message
    assert f.coord == (-256.0, -256.0, 8.0)


def test_a_non_collidable_wall_surf_is_not_fall_through():
    # same non-solid flag but a VERTICAL normal (a wall, not a floor) → not fall-through.
    m = Model(points=[(0.0, 0.0, 0.0)],
              vectors=[(1.0, 0.0, 0.0)],           # sideways normal ⇒ a wall
              surfs=[BspSurf(poly_flags=PF_SEMISOLID, v_normal=0, p_base=0)])
    assert B.analyze_built(m) == []
