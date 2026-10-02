"""`actor find --within-bbox` — spatial containment filter (spec 2026-07-24-find-spatial §2/§3/§6).

Full-containment AABB test over `writes.actor_bounds` (transform honoured, Decimal, edge-inclusive):
inside matches, straddling does not, geometry (not just Location) drives it, corner order is free,
it ANDs with the other filters and composes with the `-` universe, and malformed input exits 2 clean
(never a traceback). Drives the real argparse parser through `dispatch()` like the other find tests.
"""
import io
import os
from decimal import Decimal
from unittest import mock

import pytest

from uedcli import trunk
from uedcli.cli import main as cli, dispatch
from uedcli.builders import cube
from uedcli.model import Actor, Level


# ── helpers (mirroring test_folders.py) ──────────────────────────────────────────────

def _mkproject(tmp_path, monkeypatch, actors):
    root = tmp_path / "proj"
    (root / "maps" / "lvl").mkdir(parents=True)
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    lvl = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    ranks = dict(zip([a.name for a in actors], trunk.initial_ranks(len(actors)) or []))
    trunk.write_level(root / "maps" / "lvl", lvl, ranks)
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return root


def _run(argv, stdin=""):
    args = cli.build_parser().parse_args(argv)
    with mock.patch("sys.stdin", io.StringIO(stdin)):
        return dispatch.dispatch(args)


def _light(name, at):
    return Actor(name=name, cls="Engine.Light", location=tuple(Decimal(str(v)) for v in at))


def _brush(name, at, size=20, yaw=None):
    # origin-centered cube of edge `size` → world span is `at` ± size/2 (before rotation)
    props = [("Rotation", f"(Yaw={yaw})")] if yaw is not None else []
    return Actor(name=name, cls="Brush", brush=cube(size, size, size),
                 location=tuple(Decimal(str(v)) for v in at), props=props)


def _names(capsys):
    out = capsys.readouterr().out
    return [ln for ln in out.splitlines() if ln]


# The standard fixture: a box (0,0,0)..(100,100,100). `Inside`/`Edge` point actors are in;
# `Outside` is not; `BrushIn` (world 40..60) is contained; `BrushStraddle` (world 85..105) pokes
# out past x=100 even though its Location (95) is inside — so it must be EXCLUDED.
def _fixture(tmp_path, monkeypatch):
    return _mkproject(tmp_path, monkeypatch, [
        _light("Inside", (50, 50, 50)),
        _light("Outside", (150, 50, 50)),
        _light("Edge", (100, 100, 100)),
        _brush("BrushIn", (50, 50, 50)),
        _brush("BrushStraddle", (95, 50, 50)),
    ])


BOX = "0,0,0,100,100,100"


def test_within_bbox_contains_inside_edge_and_fully_contained_brush(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--within-bbox", BOX]) == 0
    assert sorted(_names(capsys)) == ["BrushIn", "Edge", "Inside"]


def test_within_bbox_excludes_outside_and_straddling(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--within-bbox", BOX])
    got = _names(capsys)
    assert "Outside" not in got
    # geometry-honoured: Location (95) is inside the box, but the brush's world box (…105) is not
    assert "BrushStraddle" not in got


def test_within_bbox_corner_order_is_free(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--within-bbox", "100,100,100,0,0,0"])   # opposite corner order
    assert sorted(_names(capsys)) == ["BrushIn", "Edge", "Inside"]


def test_within_bbox_edge_is_inclusive(tmp_path, monkeypatch, capsys):
    # a point actor exactly on the max corner IS contained
    _mkproject(tmp_path, monkeypatch, [_light("OnCorner", (100, 100, 100))])
    _run(["actor", "find", "--within-bbox", BOX])
    assert _names(capsys) == ["OnCorner"]


def test_within_bbox_ands_with_exact_class(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--within-bbox", BOX, "--exact-class", "Engine.Light"])
    # only the CONTAINED lights — BrushIn is dropped by the class filter
    assert sorted(_names(capsys)) == ["Edge", "Inside"]


def test_within_bbox_composes_with_stdin_universe(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    # restrict the universe to {Inside, Outside}; the bbox predicate then keeps only Inside
    _run(["actor", "find", "--within-bbox", BOX, "-"], stdin="Inside\nOutside\n")
    assert _names(capsys) == ["Inside"]


def test_within_bbox_exclude_negates_over_universe(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    # --exclude keeps the piped actors that are NOT contained → the complement over the universe
    _run(["actor", "find", "--within-bbox", BOX, "--exclude", "-"], stdin="Inside\nOutside\n")
    assert _names(capsys) == ["Outside"]


def test_within_bbox_honours_rotation_true_world_box(tmp_path, monkeypatch, capsys):
    # A 64-edge cube at (60,60,50) spans 28..92 unrotated (inside 0..100), but yawed 45° its footprint
    # grows to ±32√2 ≈ ±45.25 → ~14.75..105.25 on X/Y, poking past 100. The TRUE (rotated) world box
    # must drive the match: the rotated brush is EXCLUDED though its unrotated box would be contained.
    _mkproject(tmp_path, monkeypatch, [
        _brush("Axis", (60, 60, 50), size=64),            # unrotated → contained
        _brush("Yawed", (60, 60, 50), size=64, yaw=8192),  # 8192 uu = 45° → pokes out
    ])
    _run(["actor", "find", "--within-bbox", BOX])
    got = _names(capsys)
    assert got == ["Axis"]                                # Yawed excluded by its true rotated box


def test_within_bbox_brush_boundary_edge_inclusive_vs_over(tmp_path, monkeypatch, capsys):
    # A brush whose max FACE sits exactly on the box edge IS contained (edge-inclusive, geometry —
    # not just a point on the corner); one unit past is excluded. (Sub-unit epsilon isn't tested: the
    # trunk's `fmt_loc`/`clean` snaps sub-tolerance fractions to the grid, and the filter compares
    # within that SAME `emit.CLEAN_EPS` band — so the meaningful boundary at trunk precision is the
    # integer grid, and the 1-uu "over" case is three orders clear of the tolerance. The tolerance is
    # what makes a rotated actor contained in its own reported bbox; see
    # `dev/docs/rationale/reported-coordinates.md`.)
    # size-20 cube = half-extent 10: at x=90 → max 100 (on edge); at x=91 → max 101 (over).
    _mkproject(tmp_path, monkeypatch, [
        _brush("OnEdge", (90, 50, 50), size=20),
        _brush("Over", (91, 50, 50), size=20),
    ])
    _run(["actor", "find", "--within-bbox", BOX])
    assert _names(capsys) == ["OnEdge"]


def test_within_bbox_accepts_negative_coordinates(tmp_path, monkeypatch, capsys):
    # a leading-dash bbox token must parse as a VALUE (not be read as an option)
    _mkproject(tmp_path, monkeypatch, [_light("Origin", (0, 0, 0))])
    assert _run(["actor", "find", "--within-bbox", "-50,-50,-50,50,50,50"]) == 0
    assert _names(capsys) == ["Origin"]


def test_within_bbox_zero_volume_box_matches_only_a_point_on_it(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [_light("At", (5, 5, 5)), _light("Off", (6, 5, 5))])
    _run(["actor", "find", "--within-bbox", "5,5,5,5,5,5"])
    assert _names(capsys) == ["At"]


@pytest.mark.parametrize("flag", ["--within-bbox", "--overlapping-bbox"])
@pytest.mark.parametrize("bad", [
    "1,2,3", "1,2,3,4,5", "1,2,3,4,5,6,7", "a,b,c,d,e,f", "1,2,3,4,5,x",
    "nan,0,0,1,1,1", "snan,0,0,1,1,1", "inf,0,0,1,1,1", "-inf,0,0,1,1,1",   # Decimal accepts these
])
def test_bbox_malformed_exits_2_not_traceback(flag, bad):
    # argparse turns the ArgumentTypeError into a clean SystemExit(2) — never a raw traceback
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["actor", "find", flag, bad])
    assert e.value.code == 2


# ── --overlapping-bbox: the intersection filter ──────────────────────────────────────

def test_overlapping_bbox_catches_straddler_that_within_drops(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--overlapping-bbox", BOX]) == 0
    got = _names(capsys)
    # everything within is still in, PLUS the straddler that --within-bbox dropped; Outside stays out
    assert sorted(got) == ["BrushIn", "BrushStraddle", "Edge", "Inside"]


def test_overlapping_bbox_corner_order_is_free(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--overlapping-bbox", "100,100,100,0,0,0"])   # opposite corner order
    assert sorted(_names(capsys)) == ["BrushIn", "BrushStraddle", "Edge", "Inside"]


def test_overlapping_bbox_edge_touch_counts(tmp_path, monkeypatch, capsys):
    # a size-20 cube at x=110 spans 100..120: its min FACE sits exactly on the box max edge → overlaps
    # (edge-inclusive shared face); one unit further out (x=111 → 101..121) is disjoint.
    _mkproject(tmp_path, monkeypatch, [
        _brush("Touch", (110, 50, 50), size=20),
        _brush("Clear", (111, 50, 50), size=20),
    ])
    _run(["actor", "find", "--overlapping-bbox", BOX])
    assert _names(capsys) == ["Touch"]


def test_overlapping_bbox_ands_with_kind_brush(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--overlapping-bbox", BOX, "--kind", "brush"])
    # the two brushes that overlap; the point lights are dropped by --kind
    assert sorted(_names(capsys)) == ["BrushIn", "BrushStraddle"]


def test_overlapping_bbox_composes_with_stdin_universe(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--overlapping-bbox", BOX, "-"], stdin="BrushStraddle\nOutside\n")
    assert _names(capsys) == ["BrushStraddle"]


def test_overlapping_bbox_exclude_negates_over_universe(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    _run(["actor", "find", "--overlapping-bbox", BOX, "--exclude", "-"],
         stdin="BrushStraddle\nOutside\n")
    assert _names(capsys) == ["Outside"]


def test_both_bbox_flags_and_to_within_result(tmp_path, monkeypatch, capsys):
    # no exclusion group (owner 2026-08-02): both flags are accepted and AND together; since
    # within ⊆ overlapping, the straddler is dropped and the result is the --within-bbox set.
    _fixture(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--within-bbox", BOX, "--overlapping-bbox", BOX]) == 0
    assert sorted(_names(capsys)) == ["BrushIn", "Edge", "Inside"]


# ── writes.aabb_intersects unit ──────────────────────────────────────────────────────

def _box(lo, hi):
    return (tuple(Decimal(str(v)) for v in lo), tuple(Decimal(str(v)) for v in hi))


def test_aabb_intersects_overlap_edge_disjoint_and_containment():
    from uedcli import writes
    a = _box((0, 0, 0), (10, 10, 10))
    overlap = _box((5, 5, 5), (15, 15, 15))
    edge = _box((10, 0, 0), (20, 10, 10))       # shared face on x=10
    disjoint = _box((11, 0, 0), (20, 10, 10))
    inside = _box((2, 2, 2), (8, 8, 8))          # within ⇒ intersects
    assert writes.aabb_intersects(a, overlap) is True
    assert writes.aabb_intersects(a, edge) is True
    assert writes.aabb_intersects(a, disjoint) is False
    assert writes.aabb_intersects(a, inside) is True
    # symmetric in its arguments
    for other in (overlap, edge, disjoint, inside):
        assert writes.aabb_intersects(a, other) == writes.aabb_intersects(other, a)
