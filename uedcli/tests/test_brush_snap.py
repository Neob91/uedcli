"""`brush snap` — the stateless T3D-stdin filter (peer of `brush clip`).

The snap math (`uedcli.snap`) is exercised by `test_snap.py`; here the concern is the CLI filter —
the flag matrix (required grid/tolerance, sign checks, the >= grid/2 note), the set semantics
(empty/name-list/non-brush), all-or-nothing on a non-planar snap, and that the emitted T3D is the
snapped geometry.
"""
from __future__ import annotations

import argparse
import copy
import io
from decimal import Decimal
from unittest import mock

import pytest

from uedcli import builders
from uedcli.cli.dispatch import dispatch
from uedcli.cli.main import build_parser
from uedcli.emit import emit_actor_t3d
from uedcli.model import Actor, Brush, parse_t3d


def _args(**over) -> argparse.Namespace:
    d = dict(cmd="brush", sub="snap", set="-", grid=Decimal(16), tolerance=Decimal("0.05"),
             project=None)
    d.update(over)
    return argparse.Namespace(**d)


def _run(stdin_text, monkeypatch, capsys, **over):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    rc = dispatch(_args(**over))
    return rc, capsys.readouterr()


def _noisy_cube(name="Cube", noise="0.01") -> Actor:
    # A cube whose ±64 corners (multiples of 16) each drifted by `noise` — past emit's CLEAN_EPS so
    # the emitted T3D actually carries the off-grid value for snap to correct.
    src = builders.cube(128, 128, 128)
    d = Decimal(noise)
    polys = []
    for p in src.polys:
        np = copy.deepcopy(p)
        np.vertices = [tuple(Decimal(str(c)) + d for c in v) for v in p.vertices]
        polys.append(np)
    return builders.make_brush_actor(name, Brush(model_name=src.model_name, polys=polys), csg="add")


def _t3d(*actors) -> str:
    return "".join(emit_actor_t3d(a) for a in actors)


def test_it_snaps_a_noisy_cube_back_onto_the_grid(monkeypatch, capsys):
    rc, cap = _run(_t3d(_noisy_cube()), monkeypatch, capsys, grid=Decimal(16), tolerance=Decimal("0.05"))
    assert rc == 0
    assert cap.err == ""
    brush = parse_t3d(cap.out).actors["Cube"].brush
    comps = {float(c) for p in brush.polys for v in p.vertices for c in v}
    assert comps == {-64.0, 64.0}                          # every corner is back on the 16-grid


def test_it_treats_empty_stdin_as_a_clean_noop(monkeypatch, capsys):
    rc, cap = _run("", monkeypatch, capsys)
    assert rc == 0
    assert cap.out == "" and cap.err == ""


def test_it_refuses_a_name_list_on_stdin(monkeypatch, capsys):
    rc, cap = _run("Cube\nWall\n", monkeypatch, capsys)
    assert rc == 2
    assert cap.out == ""
    assert "no brush actors" in cap.err and "NAME list" in cap.err


def test_it_refuses_a_non_brush_member_naming_it(monkeypatch, capsys):
    lamp = Actor(name="Lamp", cls="Engine.Light",
                 location=(Decimal(0), Decimal(0), Decimal(0)))
    rc, cap = _run(_t3d(_noisy_cube("A"), lamp), monkeypatch, capsys)
    assert rc == 2
    assert cap.out == ""                                   # all-or-nothing: nothing emitted
    assert "Lamp" in cap.err and "not a brush" in cap.err


def test_it_collects_every_non_brush_member_before_failing(monkeypatch, capsys):
    # All-or-nothing: with two point actors in the set, BOTH are named in the one error.
    lamp = Actor(name="Lamp", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    urn = Actor(name="Urn", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    rc, cap = _run(_t3d(_noisy_cube("A"), lamp, urn), monkeypatch, capsys)
    assert rc == 2
    assert cap.out == ""
    assert "Lamp" in cap.err and "Urn" in cap.err


def test_it_exits_two_on_a_non_positive_grid(monkeypatch, capsys):
    rc, cap = _run(_t3d(_noisy_cube()), monkeypatch, capsys, grid=Decimal(0))
    assert rc == 2
    assert cap.out == ""
    assert "--grid must be positive" in cap.err and "0" in cap.err


def test_it_exits_two_on_a_negative_tolerance(monkeypatch, capsys):
    rc, cap = _run(_t3d(_noisy_cube()), monkeypatch, capsys, tolerance=Decimal("-0.5"))
    assert rc == 2
    assert cap.out == ""
    assert "--tolerance must be >= 0" in cap.err


def test_it_notes_but_still_snaps_when_tolerance_reaches_half_the_grid(monkeypatch, capsys):
    rc, cap = _run(_t3d(_noisy_cube()), monkeypatch, capsys, grid=Decimal(16), tolerance=Decimal(8))
    assert rc == 0
    assert "half the grid" in cap.err                      # the destroy-angles warning, not an error
    assert parse_t3d(cap.out).actors["Cube"].brush is not None


def test_it_names_the_actor_on_a_non_planar_snap_result(monkeypatch, capsys):
    from uedcli.geometry import GeometryError
    with mock.patch("uedcli.snap.snap_brush", autospec=True,
                    side_effect=GeometryError("non-planar poly")):
        rc, cap = _run(_t3d(_noisy_cube("Wonky")), monkeypatch, capsys)
    assert rc == 2
    assert cap.out == ""
    assert "Wonky" in cap.err and "non-planar poly" in cap.err


def test_it_requires_grid_and_tolerance_at_the_parser():
    # Both flags are required — no silent default grid/tolerance. argparse exits 2.
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["brush", "snap", "-"])
    assert exc.value.code == 2
