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
    assert '"ref"' in out and '"ref_poly"' in out and '"candidate"' in out and '"poly"' in out


def test_find_json_names_the_matched_ref_poly(tmp_path, monkeypatch, capsys):
    # `--relative-to Wall` (a bare name) ranks against EVERY one of Wall's 6 faces; the winner
    # here is its +Z top face (cube()'s face order puts +Z at index 4), touching Near's -Z
    # bottom face (index 5). Before this fix, no output said WHICH of Wall's faces matched --
    # only the candidate's poly index was ever printed.
    import json
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near"], "Wall", json=True))
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["ref"] == "Wall"
    assert rows[0]["ref_poly"] == 4
    assert rows[0]["candidate"] == "Near"
    assert rows[0]["poly"] == 5


def test_find_stderr_is_one_aggregate_line_not_per_match(tmp_path, monkeypatch, capsys):
    # stderr is a terse count, matching every other query verb's convention (poly.py's
    # `_print_poly_selectors`/`_find`) -- geometric/identity detail per match lives in --json only,
    # or in `relation measure` for full geometry. No per-match "ref:idx <-> cand:idx" echo here.
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall"))
    assert rc == 0
    err = capsys.readouterr().err
    assert err.strip() == "2 face(s) matched across 2 candidate(s)"


def test_find_stderr_count_reflects_matched_not_searched_candidates(tmp_path, monkeypatch, capsys):
    # 2 candidates searched, only 1 (Near) survives --max-gap -- the count must say 1, not 2.
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall", max_gap=1.0))
    assert rc == 0
    err = capsys.readouterr().err
    assert err.strip() == "1 face(s) matched across 1 candidate(s)"
