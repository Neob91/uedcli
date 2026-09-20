"""CLI wiring for `level graph` (Task 9). Follows this codebase's existing scratch-project +
`dispatch.dispatch(argparse.Namespace(...))` convention (`test_cli_brush_relation_measure.py`,
`test_eventgraph.py`'s dispatch section, `test_tree_flag.py`'s stash helpers) rather than a new
harness. The pure `actorgraph` module (build_graph/scoped_edges/format_text) is already covered by
`test_actorgraph.py`; this file covers only the CLI seam: the parser's --from/--hops/--tree wiring
and `_level_graph`'s dispatch.
"""
import argparse
from decimal import Decimal

import pytest

from uedcli import stash_register, trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser
from uedcli.model import Brush, Level, Polygon
from uedcli.normalize import canonical_actor_t3d
from uedcli.tests.conftest import StubClassIndex


def _brush(name, brush, loc=(0, 0, 0), csg="add"):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc), csg=csg)


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    """The real fixture pattern for a scratch `$UEDCLI_LEVEL` project in a CLI test — copied from
    `test_cli_brush_relation_measure.py`'s `_project`: a bare `uedcli.toml`, a trunk written via
    `trunk.write_level` with a lexicographic-rank sidecar per actor (order comes from the ranks,
    not from `Level.order`), and `$UEDCLI_LEVEL` pointing at it."""
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, *, from_actor=None, hops=None, tree=None):
    return argparse.Namespace(
        cmd="level", sub="graph", project=str(proj), tree=tree,
        from_actor=from_actor, hops=hops,
    )


def _two_touching_subtracts():
    # Same geometry as test_actorgraph.py's test_subtract_subtract_touching_gives_undirected_touches
    # / test_scoped_edges_one_hop: two 64^3 cubes offset by 64 along X, both Subtract, so they share
    # a face exactly.
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0), csg="subtract")
    b = _brush("B", cube(64, 64, 64), loc=(64, 0, 0), csg="subtract")
    return [a, b]


def _three_chained_subtracts():
    # Same geometry as test_actorgraph.py's test_scoped_edges_one_hop: A-B touch, B-C touch, A-C do
    # not (2 hops apart).
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0), csg="subtract")
    b = _brush("B", cube(64, 64, 64), loc=(64, 0, 0), csg="subtract")
    c = _brush("C", cube(64, 64, 64), loc=(128, 0, 0), csg="subtract")
    return [a, b, c]


def test_level_graph_no_from_prints_whole_level_graph(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _two_touching_subtracts())
    rc = dispatch.dispatch(_ns(proj))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "A:0 --touches(4096uu^2)--> B:1"


def test_level_graph_from_and_hops_scopes(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _three_chained_subtracts())
    rc = dispatch.dispatch(_ns(proj, from_actor="A", hops=1))
    assert rc == 0
    out = capsys.readouterr().out
    # Same A<->B edge as the two-brush case above; C is 2 hops from A -- excluded by --hops 1.
    assert out.strip() == "A:0 --touches(4096uu^2)--> B:1"


def test_level_graph_hops_without_from_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _two_touching_subtracts())
    rc = dispatch.dispatch(_ns(proj, hops=1))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--from" in err
    assert "Traceback" not in err


def test_level_graph_from_without_hops_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _two_touching_subtracts())
    rc = dispatch.dispatch(_ns(proj, from_actor="A"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--hops" in err
    assert "Traceback" not in err


def test_level_graph_unknown_from_name_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _two_touching_subtracts())
    rc = dispatch.dispatch(_ns(proj, from_actor="Nope", hops=1))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Nope" in err
    assert "Traceback" not in err


def test_level_graph_tree_stash_analyzes_stash_not_live_level(tmp_path, monkeypatch, capsys):
    # The live $UEDCLI_LEVEL carries an actor ("LiveOnly") that must NOT appear in the graph when
    # --tree stash/bay is given -- proves the verb reads the stash, not the ambient level.
    proj = _project(tmp_path, monkeypatch,
                    [_brush("LiveOnly", cube(32, 32, 32), csg="subtract")])
    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    stash_a = _brush("StashA", cube(64, 64, 64), loc=(0, 0, 0), csg="subtract")
    stash_b = _brush("StashB", cube(64, 64, 64), loc=(64, 0, 0), csg="subtract")
    reg.write_stash("bay",
                    full_level={"StashA": canonical_actor_t3d(stash_a),
                                "StashB": canonical_actor_t3d(stash_b)},
                    order=["StashA", "StashB"], packages=[], meta={})
    rc = dispatch.dispatch(_ns(proj, tree="stash/bay"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "StashA" in out and "StashB" in out
    assert "LiveOnly" not in out


def test_level_graph_unresolvable_class_exits_2_not_traceback(tmp_path, monkeypatch, capsys):
    # `movers.is_mover` raises `ClassRefError` when an actor's own class is off the composed search
    # path (uedcli/movers.py, the "in cls" branch). Exactly one of a touching pair must be a
    # Subtract for `classify_pair` to need `is_mover` at all (see actorgraph.classify_pair's own
    # docstring) -- an Add whose class the stub index doesn't carry triggers it. Mirrors
    # `test_dispatch_error_boundary.py`'s generic "class_ref" guard case and
    # `test_movers.py::test_is_mover_raises_on_an_unknown_bare_class`'s trigger condition, at the
    # CLI/dispatch layer for THIS verb specifically (no literal `test_cli_level_doctor.py`/
    # verb-specific existing test for this exact end-to-end scenario was found in this codebase --
    # see task-9-report.md "Deviations").
    sub = _brush("Room", cube(64, 64, 64), loc=(0, 0, 0), csg="subtract")
    odd = _brush("Odd", cube(64, 64, 64), loc=(64, 0, 0), csg="add")
    odd.cls = "SomeMod.Unresolvable"
    proj = _project(tmp_path, monkeypatch, [sub, odd])
    monkeypatch.setattr(resources, "mover_index",
                        lambda args, verb, project=None: StubClassIndex(unknown=("SomeMod.Unresolvable",)))
    rc = dispatch.dispatch(_ns(proj))
    assert rc == 2
    err = capsys.readouterr().err
    assert "SomeMod.Unresolvable" in err
    assert "Traceback" not in err


def test_hops_flag_parses_through_the_real_parser():
    # `_hops_arg`'s validation (positive int, or the literal 'all') is argparse-level, not
    # application-level -- pin it against the REAL parser, mirroring test_cli.py's
    # `build_parser().parse_args(...)` + `pytest.raises(SystemExit)` convention (e.g.
    # test_clip_offset_flag_rejects_bad_values_cleanly).
    p = build_parser()
    assert p.parse_args(["level", "graph", "--from", "A", "--hops", "3"]).hops == 3
    assert p.parse_args(["level", "graph", "--from", "A", "--hops", "all"]).hops == "all"
    for bad in ("0", "-2", "x"):
        with pytest.raises(SystemExit):
            p.parse_args(["level", "graph", "--from", "A", "--hops", bad])


def test_level_graph_skipped_degenerate_brush_reported_not_crashed(tmp_path, monkeypatch, capsys):
    # The design spec's own test strategy names this case explicitly: a degenerate brush is a
    # reported, skipped node, never a crash. `_level_graph`'s `for name, reason in graph.skipped`
    # stderr loop is the CLI-level surface for
    # test_actorgraph.py::test_build_graph_degenerate_brush_is_skipped_not_crashed's module-level
    # guarantee -- untested at the CLI layer before this.
    good = _brush("Good", cube(64, 64, 64), csg="subtract")
    bad_brush = Brush(model_name="Model_Bad", polys=[Polygon(vertices=[])])
    bad = make_brush_actor("Bad", bad_brush, csg="subtract")
    proj = _project(tmp_path, monkeypatch, [good, bad])
    rc = dispatch.dispatch(_ns(proj))
    assert rc == 0                          # a skipped brush is reported, not a failure
    cap = capsys.readouterr()
    assert "Bad" in cap.err                 # names the skipped actor
    assert cap.out == ""                    # no edges (only one good, unpaired brush) -> no stdout
