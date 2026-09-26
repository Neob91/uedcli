"""The `actor survey` CLI seam: parser wiring, dispatch, output shape, exit codes.

Follows this codebase's real CLI-test convention (`test_cli_actor_relation_compare.py`,
`test_cli_level_graph.py`): a hand-built `argparse.Namespace` handed to `dispatch.dispatch`, output
read through `capsys`. argparse itself is never invoked except where a test is specifically about
parsing. `conftest._stub_mover_class_index` is autouse, so `resources.mover_index` already returns a
`StubClassIndex` here.
"""
import argparse

import pytest

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.model import Level
from uedcli.tests import survey_scenarios as scen


def _project(tmp_path, monkeypatch, scenario, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    order = scenario.level.order
    trunk.write_level(proj / "maps" / name,
                      Level(actors=dict(scenario.level.actors)),
                      {n: f"{i:04d}" for i, n in enumerate(order)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, name, tree=None):
    return argparse.Namespace(cmd="actor", sub="survey", project=str(proj), tree=tree, name=name)


def test_survey_prints_raw_lines_and_a_stderr_summary(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    raw = [ln for ln in out.out.splitlines() if ln.startswith("raw ")]
    assert raw
    assert "raw fact(s)" in out.err


def test_survey_unknown_actor_exits_2_naming_it(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "NoSuchActor")) == 2
    assert "Actor not found: NoSuchActor" in capsys.readouterr().err


def test_survey_subparser_exists_and_takes_a_name_and_tree():
    from uedcli.cli.main import build_parser
    ns = build_parser().parse_args(["actor", "survey", "Wall"])
    assert (ns.cmd, ns.sub, ns.name) == ("actor", "survey", "Wall")
    assert hasattr(ns, "tree")


def test_survey_prints_raw_block_then_csg_block_then_a_two_number_summary(
        tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    lines = out.out.splitlines()
    raw = [i for i, ln in enumerate(lines) if ln.startswith("raw ")]
    csg = [i for i, ln in enumerate(lines) if ln.startswith("csg ")]
    assert raw and csg
    assert min(csg) > max(raw)
    assert f"{len(raw)} raw fact(s), {len(csg)} resolved CSG fact(s) for Wall" in out.err


def test_survey_every_line_starts_with_its_tier_token(tmp_path, monkeypatch, capsys):
    """A tier token as the FIRST WORD, never a section header — so the guarantee survives grep,
    truncation, or one line quoted mid-context into a later prompt (spec, Output shape)."""
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    for line in capsys.readouterr().out.splitlines():
        assert line == "" or line.split()[0] in ("raw", "csg")


def test_survey_degenerate_surveyed_brush_exits_2_naming_it(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_degenerate_brush())
    assert dispatch.dispatch(_ns(proj, "BadBrush")) == 2
    assert "BadBrush" in capsys.readouterr().err


def test_survey_location_less_actor_exits_2_naming_it_not_a_traceback(tmp_path, monkeypatch, capsys):
    """`actor_survey.ActorHasNoLocationError` must be mapped to exit 2 like every other survey
    failure mode -- final-review finding: this path was never caught in the CLI handler, despite
    the exception's own docstring already promising it would be."""
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_location_less_actor())
    assert dispatch.dispatch(_ns(proj, "Ghost")) == 2
    assert "Ghost" in capsys.readouterr().err


def test_survey_malformed_neighbor_collision_exits_2_naming_it_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    """`actor_survey.CollisionPropertyError` on a NEIGHBOR (not the surveyed actor itself) must also
    be mapped to exit 2 -- final-review finding, same missing `except` clause as
    `ActorHasNoLocationError` above.

    `Bad`'s class has no real schema in this lightweight CLI project (no `.u` binaries), so the
    collision gate's own `defaults.for_class` call would raise `SchemaError` before ever reaching
    the malformed `CollisionRadius` -- same reason `test_survey_unresolvable_class_exits_2_not_a_
    traceback` above substitutes `ClassDefaults`. Using `scen.stub_defaults()` here instead of
    `failing_defaults()` keeps class resolution trivially successful so the real target
    (`CollisionPropertyError`) is what actually fires."""
    pytest.importorskip("uedcli_native")
    from uedcli.cli.commands.actor import survey as survey_cmd
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_malformed_collision_neighbor())
    monkeypatch.setattr(survey_cmd, "ClassDefaults", lambda resolver: scen.stub_defaults())
    assert dispatch.dispatch(_ns(proj, "Room")) == 2
    assert "Bad" in capsys.readouterr().err


def test_survey_warns_on_a_placed_intersect_and_still_exits_0(tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_placed_intersect())
    assert dispatch.dispatch(_ns(proj, "Inter")) == 0
    err = capsys.readouterr().err
    assert "Inter" in err and "contributes nothing" in err


def test_survey_unresolvable_class_exits_2_not_a_traceback(tmp_path, monkeypatch, capsys):
    """A `uprops.SchemaError` from the collision gate must never reach the user — and must be THIS
    handler's message, which names the surveyed actor, not `dispatch.py`'s generic
    `except SchemaError` backstop, which does not.

    The raise comes from `defaults.for_class(...)` inside `survey`, so the test substitutes a
    class-defaults object whose `for_class` raises — `survey_scenarios.failing_defaults()`, the
    same helper Task 11's unit test uses. Patching `resources.schema_resolver_for` would prove
    nothing: it returns a resolver over an empty search path and cannot raise `SchemaError`."""
    pytest.importorskip("uedcli_native")
    from uedcli.cli.commands.actor import survey as survey_cmd
    proj = _project(tmp_path, monkeypatch, scen.room_with_a_flush_mounted_prop())
    monkeypatch.setattr(survey_cmd, "ClassDefaults", lambda resolver: scen.failing_defaults())
    assert dispatch.dispatch(_ns(proj, "Keypad")) == 2
    err = capsys.readouterr().err          # read ONCE: readouterr() drains the buffer
    assert "Keypad" in err
    assert "schema" in err
