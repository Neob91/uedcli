"""`brush clip` — the stateless T3D-stdin filter (replaced the by-name in-place trunk edit,
owner 2026-08-02). Clips every brush in a piped set by ONE world plane and emits the clipped
actors to stdout; touches neither trunk nor stash.

The clip math (`uedcli.clip`) is exercised by `test_clip.py`; here the concern is the CLI filter —
the flag matrix, the set semantics (empty/name-list/non-brush/multi-brush), the all-or-nothing
miss/discard rules, and that the emitted T3D is the clipped geometry, not just a face count.
"""
from __future__ import annotations

import argparse
import io
from decimal import Decimal
from unittest import mock

from uedcli import builders
from uedcli.clip import clip_brush
from uedcli.cli.dispatch import dispatch
from uedcli.emit import emit_actor_t3d
from uedcli.model import Actor, parse_t3d, parse_t3d_actors


def _args(**over) -> argparse.Namespace:
    d = dict(cmd="brush", sub="clip", set="-", axis=None, offset=None, plane=None,
             keep="below", project=None)
    d.update(over)
    return argparse.Namespace(**d)


def _run(stdin_text, monkeypatch, capsys, **over):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    rc = dispatch(_args(**over))
    return rc, capsys.readouterr()


def _cube(name="Cube", size=(128, 128, 128), at=(0, 0, 0), **props):
    b = builders.translate_brush(builders.cube(*size), *at)
    a = builders.make_brush_actor(name, b, csg="add")
    for k, v in props.items():
        a.props = [p for p in a.props if p[0] != k] + [(k, v)]
    return a


def _t3d(*actors) -> str:
    return "".join(emit_actor_t3d(a) for a in actors)


# ── the headline pipe: one-pass chamfer ─────────────────────────────────────────


def test_it_clips_a_cube_into_a_seven_face_chamfer_in_one_pipe(monkeypatch, capsys):
    # `brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below` — the chamfered box.
    rc, cap = _run(_t3d(_cube()), monkeypatch, capsys,
                   plane=[(Decimal(96), Decimal(0), Decimal(0)),
                          (Decimal(1), Decimal(0), Decimal(1))])
    assert rc == 0
    assert cap.err == ""
    level = parse_t3d(cap.out)
    assert list(level.actors) == ["Cube"]
    polys = level.actors["Cube"].brush.polys
    assert len(polys) == 7                                  # 5 survivors + truncation + 1 cap
    # The cut cap lies exactly on the plane x+z=96 (normal (1,1)/√2 through (96,0,0)); every one
    # of its vertices satisfies x+z==96, which a plain box never has. Asserting the geometry, not
    # just the count, is what pins the clip actually happened where asked.
    cap_polys = [p for p in polys if all(abs(float(x) + float(z) - 96) < 1e-3 for x, _y, z in p.vertices)]
    assert len(cap_polys) == 1, "exactly one face should lie on the clip plane x+z=96"
    assert len(cap_polys[0].vertices) == 4


def test_it_emits_the_same_geometry_the_clip_math_produces(monkeypatch, capsys):
    # Round-trip parity: the filter's emitted brush equals `clip_brush` applied directly (the
    # by-name path's exact math, unchanged). An unrotated/unscaled brush maps world→local as
    # identity, so the local plane is the world plane.
    src = _cube("Box")
    rc, cap = _run(_t3d(src), monkeypatch, capsys, axis="z", offset=Decimal(0), keep="below")
    assert rc == 0
    expected = clip_brush(src.brush, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), keep_negative=True)
    got = parse_t3d(cap.out).actors["Box"].brush
    assert [p.vertices for p in got.polys] == [p.vertices for p in expected.polys]


# ── set semantics ───────────────────────────────────────────────────────────────


def test_it_treats_empty_stdin_as_a_clean_noop(monkeypatch, capsys):
    rc, cap = _run("", monkeypatch, capsys, axis="z", offset=Decimal(0))
    assert rc == 0
    assert cap.out == "" and cap.err == ""


def test_it_refuses_a_name_list_on_stdin(monkeypatch, capsys):
    # stdin is a T3D snippet, not the newline name list `actor find` prints.
    rc, cap = _run("Cube\nWall\n", monkeypatch, capsys, axis="z", offset=Decimal(0))
    assert rc == 2
    assert cap.out == ""
    assert "no brush actors" in cap.err and "NAME list" in cap.err


def test_it_refuses_a_non_brush_member_naming_it(monkeypatch, capsys):
    lamp = Actor(name="Lamp", cls="Engine.Light",
                 location=(Decimal(0), Decimal(0), Decimal(0)))
    rc, cap = _run(_t3d(_cube("A"), lamp), monkeypatch, capsys, axis="z", offset=Decimal(0))
    assert rc == 2
    assert cap.out == ""                                    # all-or-nothing: nothing emitted
    assert "Lamp" in cap.err and "not a brush" in cap.err


def test_it_clips_every_brush_in_a_multi_brush_set_by_the_one_plane(monkeypatch, capsys):
    a = _cube("CubeA")
    b = _cube("CubeB", at=(256, 0, 0))                      # both straddle z=0
    rc, cap = _run(_t3d(a, b), monkeypatch, capsys, axis="z", offset=Decimal(0), keep="below")
    assert rc == 0
    level = parse_t3d(cap.out)
    assert list(level.actors) == ["CubeA", "CubeB"]
    for name in ("CubeA", "CubeB"):
        polys = level.actors[name].brush.polys
        assert len(polys) == 6                              # 5 survivors + 1 cap
        assert max(float(v[2]) for p in polys for v in p.vertices) <= 1e-3  # nothing above z=0


_BUILDER_BRUSH_BLOCK = (                                    # Class=Brush + inner model `Brush`, no CsgOper
    "Begin Actor Class=Brush Name=Brush0\n"
    "    Begin Brush Name=Brush\n"
    "        Begin PolyList\n"
    "            Begin Polygon\n"
    "                Vertex   -00128.000000,-00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,+00128.000000\n"
    "            End Polygon\n"
    "        End PolyList\n"
    "    End Brush\n"
    '    Name="Brush0"\n'
    "End Actor\n"
)


def test_it_drops_a_builder_brush_from_the_set(monkeypatch, capsys):
    # A `MAP EXPORT`-derived stream carries the transient red builder brush; every ingest path
    # drops it. Here the set is builder-brush + one real cube → only the cube is clipped/emitted.
    rc, cap = _run(_BUILDER_BRUSH_BLOCK + _t3d(_cube("Real")), monkeypatch, capsys,
                   axis="z", offset=Decimal(0), keep="below")
    assert rc == 0
    assert list(parse_t3d(cap.out).actors) == ["Real"]


# ── miss vs discard (all-or-nothing) ─────────────────────────────────────────────


def test_it_passes_a_missed_brush_through_unchanged_with_a_note(monkeypatch, capsys):
    # A plane far above the cube misses its interior: emit it unchanged, note on stderr, exit 0.
    src = _cube("Cube")
    rc, cap = _run(_t3d(src), monkeypatch, capsys,
                   axis="z", offset=Decimal(100000), keep="below")
    assert rc == 0
    assert "did not intersect brush Cube" in cap.err
    got = parse_t3d(cap.out).actors["Cube"].brush
    assert [p.vertices for p in got.polys] == [p.vertices for p in src.brush.polys]  # untouched


def test_it_exits_two_when_the_plane_discards_a_whole_brush(monkeypatch, capsys):
    rc, cap = _run(_t3d(_cube("Cube")), monkeypatch, capsys,
                   axis="z", offset=Decimal(100000), keep="above")
    assert rc == 2
    assert cap.out == ""                                    # nothing written on the failed run
    assert "discards the whole brush" in cap.err and "Cube" in cap.err


def test_it_collects_every_discarded_brush_before_failing(monkeypatch, capsys):
    # All-or-nothing: with two brushes both wholly on the discarded side, BOTH are named.
    a = _cube("CubeA")
    b = _cube("CubeB", at=(256, 0, 0))
    rc, cap = _run(_t3d(a, b), monkeypatch, capsys,
                   axis="z", offset=Decimal(100000), keep="above")
    assert rc == 2
    assert cap.out == ""
    assert "CubeA" in cap.err and "CubeB" in cap.err


def test_it_names_the_actor_on_a_degenerate_clip_result(monkeypatch, capsys):
    # A clip whose result fails `validate_brush` raises GeometryError; the filter wraps it as a
    # clean exit 2 naming the offending actor, never a bare traceback.
    from uedcli.geometry import GeometryError
    with mock.patch("uedcli.clip.clip_brush", autospec=True,
                    side_effect=GeometryError("non-planar poly")):
        rc, cap = _run(_t3d(_cube("Wonky")), monkeypatch, capsys,
                       axis="z", offset=Decimal(0), keep="below")
    assert rc == 2
    assert cap.out == ""
    assert "Wonky" in cap.err and "non-planar poly" in cap.err


# ── rotation awareness ───────────────────────────────────────────────────────────


def test_it_clips_a_rotated_brush_in_its_own_local_frame(monkeypatch, capsys):
    # A yaw-90 cube clipped by world plane z=0. Yaw is about Z, so the world plane maps to local
    # z=0: the cube halves (5 faces + cap) and the Rotation field survives, so it materializes as
    # the intended world clip — the same rotation-aware result the deleted by-name form gave.
    from uedcli.rotation import world_to_local_normal, world_to_local_point
    src = _cube("B1", Rotation="(Yaw=16384)")
    rc, cap = _run(_t3d(src), monkeypatch, capsys, axis="z", offset=Decimal(0), keep="below")
    assert rc == 0
    actor = parse_t3d_actors(cap.out)[0]
    assert ("Rotation", "(Yaw=16384)") in actor.props            # Rotation preserved
    # Exact geometry parity: the filter maps the world plane into the actor's local frame and runs
    # the SAME `clip_brush` the deleted by-name path did — assert vertex-for-vertex, not just count.
    lp = world_to_local_point(src, (0.0, 0.0, 0.0))
    ln = world_to_local_normal(src, (0.0, 0.0, 1.0))
    expected = clip_brush(src.brush, lp, ln, keep_negative=True)
    assert [p.vertices for p in actor.brush.polys] == [p.vertices for p in expected.polys]


# ── flag matrix ──────────────────────────────────────────────────────────────────


def test_it_exits_two_when_both_plane_and_axis_are_given(monkeypatch, capsys):
    rc, cap = _run(_t3d(_cube()), monkeypatch, capsys,
                   axis="z", offset=Decimal(0),
                   plane=[(Decimal(0), Decimal(0), Decimal(0)),
                          (Decimal(0), Decimal(0), Decimal(1))])
    assert rc == 2
    assert cap.out == ""
    assert "not both" in cap.err


def test_it_exits_two_when_no_plane_is_given(monkeypatch, capsys):
    rc, cap = _run(_t3d(_cube()), monkeypatch, capsys)      # no --axis/--offset, no --plane
    assert rc == 2
    assert cap.out == ""
    assert "--axis" in cap.err and "--plane" in cap.err
