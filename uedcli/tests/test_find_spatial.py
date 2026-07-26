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

from uedcli import cli, dispatch, trunk
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
    # trunk's `fmt_loc`/`clean` snaps sub-tolerance fractions to the grid, and the filter itself is
    # exact-Decimal — so the meaningful boundary at trunk precision is integer-grid.)
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


@pytest.mark.parametrize("bad", [
    "1,2,3", "1,2,3,4,5", "1,2,3,4,5,6,7", "a,b,c,d,e,f", "1,2,3,4,5,x",
    "nan,0,0,1,1,1", "snan,0,0,1,1,1", "inf,0,0,1,1,1", "-inf,0,0,1,1,1",   # Decimal accepts these
])
def test_within_bbox_malformed_exits_2_not_traceback(bad):
    # argparse turns the ArgumentTypeError into a clean SystemExit(2) — never a raw traceback
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["actor", "find", "--within-bbox", bad])
    assert e.value.code == 2
