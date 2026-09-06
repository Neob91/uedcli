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


def _ns(proj, candidates, relative_to, **overrides):
    defaults = dict(
        cmd="brush", sub="relation", relationsub="find",
        project=str(proj), tree=None, candidates=candidates, relative_to=relative_to,
        max_gap=None, min_gap=None, footprint=None, plane=None, top=1, allow_self=False, json=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_find_prints_matching_candidates(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Near:" in out


def test_find_max_gap_filters(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall", max_gap=1.0))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Near:" in out
    assert "Far:" not in out


def test_find_omitted_candidates_defaults_to_every_other_brush(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, [], "Wall"))
    assert rc == 0
    assert "Near:" in capsys.readouterr().out


def test_find_named_self_rejected_by_default(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(64, 64, 8))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Wall"], "Wall:0"))
    assert rc == 2
    assert "allow-self" in capsys.readouterr().err


def test_find_empty_stdin_dash_is_clean_noop(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(64, 64, 8))]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"], "Wall"))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_find_json_emits_structured_array(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near"], "Wall", json=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip().startswith("[")
    assert "footprint_2d" in out
