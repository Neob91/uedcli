import argparse
from decimal import Decimal

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.model import Level


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, ref, target, top=1, allow_self=False):
    return argparse.Namespace(
        cmd="brush", sub="relation", relationsub="measure",
        project=str(proj), tree=None, ref=ref, target=target, top=top, allow_self=allow_self,
    )


def test_relation_prints_report_and_exits_zero(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "LegFoot", "FloorPad"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "LegFoot <-> FloorPad" in out
    assert "checked: 2 brushes, 1 pairs, every face" in out


def test_relation_unknown_name_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "LegFoot", "NoSuchBrush"))
    assert rc == 2
    assert "NoSuchBrush" in capsys.readouterr().err


def test_relation_top_all_shows_every_candidate(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(32, 32, 32), loc=(0, 0, 0)),
        _brush("B", cube(32, 32, 32), loc=(0, 0, 32)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "B", top="all"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "candidates shown)" not in out  # --top all never caps, so no "N of M" note at all


def test_relation_invalid_top_exits_2(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(16, 16, 16)),
        _brush("B", cube(16, 16, 16), loc=(0, 0, 16)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "B", top=0))
    assert rc == 2


def test_relation_same_brush_rejected_by_default(tmp_path, monkeypatch, capsys):
    actors = [_brush("A", cube(16, 16, 16))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "A"))
    assert rc == 2
    assert "allow-self" in capsys.readouterr().err


def test_relation_allow_self_permits_same_brush(tmp_path, monkeypatch, capsys):
    actors = [_brush("A", cube(16, 16, 16))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "A", allow_self=True))
    assert rc == 0
