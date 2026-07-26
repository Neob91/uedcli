import argparse
from pathlib import Path

import pytest


def _ns(**kw):
    return argparse.Namespace(cmd="project", sub="show", **{"project": None, **kw})


def _base_packages(tmp_path):
    """A game's base package dir with two real package files. Returns its abspath."""
    base = tmp_path / "game" / "System"
    base.mkdir(parents=True)
    (base / "Core.u").write_bytes(b"\x00")
    (base / "Engine.u").write_bytes(b"\x00")
    return base


def _user_config(tmp_path, base, monkeypatch):
    """Point $UEDCLI_HOME at a per-user config declaring [games.deusex] over `base`."""
    home = tmp_path / "uedhome"
    home.mkdir()
    (home / "config.toml").write_text(f'[games.deusex]\npaths = "{base}"\n')
    monkeypatch.setenv("UEDCLI_HOME", str(home))


def _project(tmp_path, *, overlay=False):
    """A uedcli project ROOT (`<root>/uedcli.toml`). With overlay=True it declares a `paths` dir
    and one overlay package (an .utx under the root) so composition yields a 'project'-tagged
    entry."""
    root = tmp_path / "myrepo"
    (root / "maps").mkdir(parents=True)
    body = 'game = "deusex"\n'
    if overlay:
        body += 'paths = "assets"\n'
        (root / "assets").mkdir(parents=True)
        (root / "assets" / "MyTex.utx").write_bytes(b"\x00")
    (root / "uedcli.toml").write_text(body)
    return root


def test_project_show_prints_project_game_maps_and_composed_search_path(tmp_path, monkeypatch, capsys):
    from uedcli import dispatch

    base = _base_packages(tmp_path)
    _user_config(tmp_path, base, monkeypatch)
    proj = _project(tmp_path, overlay=True)

    assert dispatch.dispatch(_ns(project=str(proj))) == 0

    out = capsys.readouterr().out
    assert str(proj) in out                          # the root line
    assert "deusex" in out
    assert str(proj / "maps") in out
    # All THREE managed dirs print (spec §7): maps, prefabs, catalog — root-relative defaults.
    assert str(proj / "prefabs") in out
    assert str(proj / "texture-catalog") in out
    # Each package line carries its provenance tag (the load-bearing behavior — the old
    # --explain-paths). Assert the tag ON the line for the file, not a bare substring (the header
    # "project shadows base" contains both words and would satisfy a loose `in out` check).
    lines = {Path(ln.split()[-1]).name: ln for ln in out.splitlines() if ln.startswith("  [")}
    assert "[project]" in lines["MyTex.utx"]
    assert "[base]" in lines["Core.u"]
    assert "[base]" in lines["Engine.u"]


def test_project_show_json(tmp_path, monkeypatch, capsys):
    import json
    from uedcli import dispatch

    base = _base_packages(tmp_path)
    _user_config(tmp_path, base, monkeypatch)
    proj = _project(tmp_path, overlay=True)

    assert dispatch.dispatch(_ns(project=str(proj), json=True)) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["root"] == str(proj)
    assert doc["game"] == "deusex"
    assert doc["maps"] == str(proj / "maps")
    assert doc["prefabs"] == str(proj / "prefabs")
    assert doc["catalog"] == str(proj / "texture-catalog")
    provs = {Path(e["path"]).name: e["provenance"] for e in doc["search_path"]}
    assert provs["MyTex.utx"] == "project"
    assert provs["Core.u"] == "base"


def test_project_show_no_project_exits_2(tmp_path, monkeypatch):
    from uedcli import dispatch

    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert dispatch.dispatch(_ns()) == 2


def test_project_show_no_user_config_exits_2(tmp_path, monkeypatch, capsys):
    from uedcli import dispatch

    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "empty"))   # no config.toml there
    proj = _project(tmp_path)
    assert dispatch.dispatch(_ns(project=str(proj))) == 2
    assert "config.toml" in capsys.readouterr().err


def test_project_show_missing_game_exits_2(tmp_path, monkeypatch, capsys):
    from uedcli import dispatch

    base = _base_packages(tmp_path)
    home = tmp_path / "uedhome"
    home.mkdir()
    (home / "config.toml").write_text(f'[games.unreal]\npaths = "{base}"\n')   # not 'deusex'
    monkeypatch.setenv("UEDCLI_HOME", str(home))
    proj = _project(tmp_path)                                    # game = deusex, absent from config

    assert dispatch.dispatch(_ns(project=str(proj))) == 2
    assert "deusex" in capsys.readouterr().err
