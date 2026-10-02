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


_RAW_RELATIONS = ("encloses", "crosses", "touches", "coincides")
_CSG_RELATIONS = ("touches", "crosses", "occupies", "carves", "connects")


def test_survey_prints_raw_lines_tagged_raw(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    raw = [ln for ln in out.out.splitlines()
           if any(f" --raw:{r}--> " in ln for r in _RAW_RELATIONS)]
    assert raw
    assert "fact(s)" not in out.err   # the trailing summary line is gone (spec)


def test_survey_unknown_actor_exits_2_naming_it(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "NoSuchActor")) == 2
    assert "Actor not found: NoSuchActor" in capsys.readouterr().err


def test_survey_subparser_exists_and_takes_a_name_and_tree():
    from uedcli.cli.main import build_parser
    ns = build_parser().parse_args(["actor", "survey", "Wall"])
    assert (ns.cmd, ns.sub, ns.name) == ("actor", "survey", "Wall")
    assert hasattr(ns, "tree")


def test_survey_prints_raw_block_then_csg_block_with_no_trailing_summary(
        tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    lines = out.out.splitlines()
    raw = [i for i, ln in enumerate(lines) if any(f" --raw:{r}--> " in ln for r in _RAW_RELATIONS)]
    csg = [i for i, ln in enumerate(lines) if any(f" --csg:{r}--> " in ln for r in _CSG_RELATIONS)]
    assert raw and csg
    assert min(csg) > max(raw)
    assert "fact(s)" not in out.err   # the trailing summary line is gone (spec)


def test_survey_tags_every_relation_with_its_tier(tmp_path, monkeypatch, capsys):
    """Every relation name is prefixed `raw:`/`csg:` (spec) -- replaces the old design's bare verb
    plus block ordering as the only tier signal. Fixed order (raw block, then csg block) plus the
    blank separator between them still holds too."""
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert not any(ln.startswith("raw ") or ln.startswith("csg ") for ln in lines)
    relation_lines = [ln for ln in lines if " --" in ln]
    assert relation_lines
    assert all(" --raw:" in ln or " --csg:" in ln for ln in relation_lines)
    raw = [i for i, ln in enumerate(lines) if any(f" --raw:{r}--> " in ln for r in _RAW_RELATIONS)]
    csg = [i for i, ln in enumerate(lines) if any(f" --csg:{r}--> " in ln for r in _CSG_RELATIONS)]
    assert raw and csg
    assert min(csg) > max(raw)
    assert lines[max(raw) + 1] == ""


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


def test_survey_warns_on_a_placed_intersect_and_still_exits_0(tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_placed_intersect())
    assert dispatch.dispatch(_ns(proj, "Inter")) == 0
    err = capsys.readouterr().err
    assert "Inter" in err and "contributes nothing" in err


## test_survey_unresolvable_class_exits_2_not_a_traceback removed: its premise (the collision
## gate's `defaults.for_class` call) no longer exists -- `region_of`/`survey` never resolve class
## schema now that CollisionRadius/CollisionHeight handling is gone (spec scope: brush-vs-brush
## only). `grep -rn "for_class" old/uedcli/actor_survey.py` confirms zero remaining call sites.
