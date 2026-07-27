"""Regressions for the ambient-`$UEDCLI_LEVEL` model (decisions 2026-07-20; spec
board item `level-is-the-ambient-uedcli-level-target-tree` §8): the mutation visibility echo, `level list` never
crashing on a bad env, and the `--tree`+`--map` preview contradiction. The `--tree`/env precedence and
the malformed-value errors are covered in `test_tree_flag.py` / `test_level_select.py`."""
import argparse
from decimal import Decimal

import pytest

from uedcli import dispatch, trunk
from uedcli.model import Actor, Level


def _ns(**kw):
    kw.setdefault("tree", None)
    return argparse.Namespace(**kw)


def _project(tmp_path, monkeypatch, name="lvl", *, env=True):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"Wall": Actor(name="Wall", cls="Light", location=(0, 0, 0))}, order=["Wall"])
    trunk.write_level(proj / "maps" / name, lvl, {"Wall": "m"})
    if env:
        monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name


def _move(proj, **over):
    kw = dict(cmd="actor", sub="move", name="Wall", to=(Decimal(9), Decimal(0), Decimal(0)),
              by=None, project=str(proj))
    kw.update(over)
    return _ns(**kw)


# ── Mutation visibility echo (spec §6/§8h) ──────────────────────────────────────────────────

def test_mutation_from_env_echoes_the_level_to_stderr(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)              # $UEDCLI_LEVEL=lvl, no --tree
    assert dispatch.dispatch(_move(proj)) == 0
    assert "editing level 'lvl' (from $UEDCLI_LEVEL)" in capsys.readouterr().err


def test_mutation_with_explicit_tree_is_silent(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    assert dispatch.dispatch(_move(proj, tree="level/lvl")) == 0
    assert "from $UEDCLI_LEVEL" not in capsys.readouterr().err   # explicit target → no echo


def test_read_verb_from_env_does_not_echo(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="actor", sub="find", project=str(proj),
                               name=[], cls=[], group=[], prop=[], kind=None))
    assert rc == 0
    assert "from $UEDCLI_LEVEL" not in capsys.readouterr().err   # a read never announces


def test_echo_fires_once_per_command(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    assert dispatch.dispatch(_move(proj)) == 0
    assert capsys.readouterr().err.count("from $UEDCLI_LEVEL") == 1


# ── `level list` never crashes on a bad $UEDCLI_LEVEL (spec §4b/§8g) ─────────────────────────

@pytest.mark.parametrize("bad", ["ghost", "level/lvl", "..", ".locks"])
def test_level_list_survives_a_bad_env(tmp_path, monkeypatch, capsys, bad):
    # `level list` is exactly the command you'd run to NOTICE a bad export, so it must mark the
    # value "(not listed)" and exit 0 — never raise the resolver's LevelSelectionError.
    proj, _ = _project(tmp_path, monkeypatch, env=False)
    monkeypatch.setenv("UEDCLI_LEVEL", bad)               # set-but-bad (nonexistent / malformed)
    assert dispatch.dispatch(_ns(cmd="level", sub="list", project=str(proj), json=False)) == 0
    err = capsys.readouterr().err
    assert f"$UEDCLI_LEVEL={bad} (not listed)" in err


def test_level_list_marks_the_active_level(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)             # $UEDCLI_LEVEL=lvl (a real level)
    assert dispatch.dispatch(_ns(cmd="level", sub="list", project=str(proj), json=False)) == 0
    out, err = capsys.readouterr()
    assert out.splitlines() == ["lvl"]
    assert "$UEDCLI_LEVEL=lvl" in err and "(not listed)" not in err


def test_level_list_json_uses_active_key(tmp_path, monkeypatch, capsys):
    import json
    proj, _ = _project(tmp_path, monkeypatch)
    assert dispatch.dispatch(_ns(cmd="level", sub="list", project=str(proj), json=True)) == 0
    assert json.loads(capsys.readouterr().out) == [{"name": "lvl", "active": True}]


# ── an explicitly-empty --tree is an error, not a silent fallback (review nit) ─────────────

def test_empty_tree_string_is_an_error_not_a_silent_fallback(tmp_path, monkeypatch, capsys):
    # `--tree ""` (e.g. an unset shell var) must NOT silently read $UEDCLI_LEVEL — for a READ verb
    # that would be an invisible wrong-level read. It errors with the grammar message instead.
    proj, _ = _project(tmp_path, monkeypatch)             # $UEDCLI_LEVEL=lvl is set
    rc = dispatch.dispatch(_ns(cmd="actor", sub="find", project=str(proj), tree="",
                               name=[], cls=[], group=[], prop=[], kind=None))
    assert rc == 2
    assert "must be KIND/NAME" in capsys.readouterr().err


def test_empty_tree_string_errors_even_on_materialize(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj), tree="",
                               out=str(tmp_path / "x.dx"), overwrite=False,
                               no_verify=False, keep_build=False))
    assert rc == 2
    assert "must be KIND/NAME" in capsys.readouterr().err


# ── preview `--tree` + `--map` is a clean contradiction (spec §4b) ──────────────────────────

def test_preview_tree_with_map_is_rejected(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    args = _ns(cmd="level", sub="preview", project=str(proj), native=False, game=True, fov=None,
               map="/tmp/x.dx", rebuild=None, keep_alive=None, size="1280x960", list_actors=None,
               out_dir=str(tmp_path / "o"), sample=0, shots=["at:0,0,0;rot:0,0"], tree="level/lvl")
    assert dispatch.dispatch(args) == 2
    assert "cannot be combined with --map" in capsys.readouterr().err
