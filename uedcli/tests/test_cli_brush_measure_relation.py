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


def _ns(proj, names, top=1):
    return argparse.Namespace(
        cmd="brush", sub="measure", measuresub="relation",
        project=str(proj), tree=None, names=names, top=top,
    )


def test_relation_prints_report_and_exits_zero(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "FloorPad"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "LegFoot <-> FloorPad" in out
    assert "checked: 2 brushes, 1 pairs, every face" in out


def test_relation_unknown_name_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "NoSuchBrush"]))
    assert rc == 2
    assert "NoSuchBrush" in capsys.readouterr().err


def test_relation_stdin_dash_reads_names(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("LegFoot\nFloorPad\n"))
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert "LegFoot <-> FloorPad" in capsys.readouterr().out


def test_relation_empty_stdin_is_clean_noop(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_relation_fewer_than_two_names_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot"]))
    assert rc == 2
    assert "at least 2" in capsys.readouterr().err


def test_relation_duplicate_name_deduped_not_self_compared(tmp_path, monkeypatch, capsys):
    # Naming the same brush twice (e.g. piped in from an upstream query that emitted a dup) must
    # not self-compare it -- that would report a nonsensical "coincident with itself" block and
    # an inflated brush/pair count from a tool whose whole premise is exact, trustworthy counts.
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "LegFoot", "FloorPad"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "LegFoot:0 <-> LegFoot:0" not in out
    assert "checked: 2 brushes, 1 pairs, every face" in out


def test_relation_all_duplicate_names_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "LegFoot"]))
    assert rc == 2
    assert "at least 2" in capsys.readouterr().err


def test_relation_top_all_shows_every_candidate(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(32, 32, 32), loc=(0, 0, 0)),
        _brush("B", cube(32, 32, 32), loc=(0, 0, 32)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["A", "B"], top="all"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "candidates shown)" not in out  # --top all never caps, so no "N of M" note at all


def test_relation_invalid_top_exits_2(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(16, 16, 16)),
        _brush("B", cube(16, 16, 16), loc=(0, 0, 16)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["A", "B"], top=0))
    assert rc == 2
