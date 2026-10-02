"""`level paths define` (spec §5): the stdout/stderr contract, the `auto-path-<token>` batch label,
name/rank reuse across runs, faithful moves, and the `pathing` gate. The world BSP is the real
native build (the committed UED22 `.u` as the schema); the placement is a fake `placer`."""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

import pytest

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.model import parse_t3d
from uedcli.native import pathplace
from uedcli.tests.test_native_roundtrip import _room_t3d

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

pytestmark = pytest.mark.skipif(not (_UED22 / "Engine.u").is_file(),
                                reason="committed UED22/Engine.u not present")


def _project(tmp_path, monkeypatch, *, pathing: str | None = "ued22-469") -> Path:
    home = tmp_path / "home"
    home.mkdir()
    line = "" if pathing is None else f'pathing = "{pathing}"\n'
    (home / "config.toml").write_text(f'[games.deusex]\npaths = "{_UED22}"\n{line}')
    monkeypatch.setenv("UEDCLI_HOME", str(home))
    proj = tmp_path / "repo"
    (proj / "maps").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    level = parse_t3d(_room_t3d().replace(
        "End Map\n",
        "Begin Actor Class=Engine.PathNode Name=Hand_1\n"
        "    Location=(X=64.000000,Y=0.000000,Z=-80.000000)\n    Name=\"Hand_1\"\nEnd Actor\n"
        "Begin Actor Class=Engine.PathNode Name=PathNode_old1\n"
        "    Location=(X=-100.000000,Y=0.000000,Z=-80.000000)\n"
        "    Name=\"PathNode_old1\"\nEnd Actor\n"
        "End Map\n"))
    level.actors["PathNode_old1"].labels = frozenset({"auto-path-abc123", "keep"})
    level.order = list(level.actors)
    ranks = dict(zip(level.order, trunk.initial_ranks(len(level.order))))
    trunk.write_level(proj / "maps" / "lvl", level, ranks)
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return proj


def _placer_returning(created, moved=(), removed=()):
    calls = []

    def fake(model_body, movers, navs, zones, level_zone, starts):
        calls.append(dict(model_body=model_body, movers=movers, navs=navs, zones=zones,
                          level_zone=level_zone, starts=starts))
        return pathplace.Placement(created=tuple(created), moved=tuple(moved),
                                   removed=tuple(removed), log=("Built Paths: 2",))
    return fake, calls


def _run(proj):
    return dispatch.dispatch(argparse.Namespace(cmd="level", sub="paths", paths_sub="define",
                                                project=str(proj), tree=None))


def test_define_places_moves_reuses_and_labels(tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch)
    fake, calls = _placer_returning(
        created=[(-100.0, 0.0, -80.0), (200.0, 0.0, -80.0)],      # 1st within 1 uu of the stripped
        moved=[(1, (70.0, 5.0, -80.0))])                          # nav 1 = Hand_1 (Start0 is 0)
    monkeypatch.setattr(pathplace, "placer", fake)
    monkeypatch.setattr("uedcli.t3dtree._rand_suffix", lambda: "zz9zz9")
    before = trunk.read_level_with_bodies(proj / "maps" / "lvl")[1]
    assert _run(proj) == 0
    out, err = capsys.readouterr()
    assert out.splitlines() == ["PathNode_old1", "PathNode_zz9zz9", "Hand_1"]
    assert "removed previous auto node: PathNode_old1" in err
    assert "batch label: auto-path-zz9zz9" in err
    assert "starts walked: 1; created: 2; merged: 0; moved: 1; removed: 1" in err
    # what reached the placer: the stripped node is gone, PlayerStart is a start
    (call,) = calls
    assert [n[1] for n in call["navs"]] == ["playerstart", "navigationpoint"]
    assert call["starts"] == [0] and call["movers"] == [] and call["level_zone"][0] == 0
    # the trunk: reused name keeps its rank, both new nodes carry the batch label, Hand_1 moved
    level, ranks, _bodies, _folders = trunk.read_level_with_bodies(proj / "maps" / "lvl")
    assert level.actors["PathNode_old1"].labels == {"auto-path-zz9zz9"}
    assert level.actors["PathNode_zz9zz9"].labels == {"auto-path-zz9zz9"}
    assert level.actors["PathNode_zz9zz9"].cls == "Engine.PathNode"
    assert level.actors["Hand_1"].location == (Decimal("70.0"), Decimal("5.0"), Decimal("-80.0"))
    assert ranks["PathNode_old1"] == before["PathNode_old1"]     # reused name keeps its rank
    assert ranks["PathNode_zz9zz9"] > max(before.values())       # a fresh node appends


def test_define_under_pathing_none_exits_2_naming_the_key(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, pathing="none")
    monkeypatch.setattr(pathplace, "placer", lambda *a: pytest.fail("must not place"))
    assert _run(proj) == 2
    assert '[games.deusex].pathing is "none"' in capsys.readouterr().err


def test_define_with_no_pathing_key_exits_2_naming_key_and_values(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, pathing=None)
    assert _run(proj) == 2
    err = capsys.readouterr().err
    assert "[games.deusex].pathing" in err and "deusex-1112fm, ued22-469, none" in err


def test_a_placer_failure_is_a_named_exit_2_and_writes_nothing(tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch)

    def boom(*a):
        raise pathplace.PathPlaceError("native path placement failed: scout fell out of the world")
    monkeypatch.setattr(pathplace, "placer", boom)
    before = sorted(p.name for p in (proj / "maps" / "lvl" / "actors").iterdir())
    assert _run(proj) == 2
    assert "scout fell out of the world" in capsys.readouterr().err
    assert sorted(p.name for p in (proj / "maps" / "lvl" / "actors").iterdir()) == before
