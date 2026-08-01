import argparse
import subprocess
from pathlib import Path

import pytest

from uedcli import trunk
from uedcli.cli import errors, level_sources
from uedcli.cli import dispatch
from uedcli.cli import resources
from uedcli.model import Actor, Brush, Level


def _project(tmp_path, name="20_AireGardens"):
    """A minimal uedcli project ROOT with one (empty) level trunk. Returns (root, level name)."""
    proj = tmp_path / "myrepo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    return proj, name


def _ns(**kw):
    return argparse.Namespace(**kw)


# --- Task A: --project + _resolve_project ---

def test_resolve_project_from_the_project_flag(tmp_path):
    proj, _ = _project(tmp_path)
    got = resources.resolve_project(_ns(project=str(proj)))
    assert got.root == str(proj)


def test_resolve_project_errors_when_none_found(tmp_path, monkeypatch):
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(dispatch.ProjectError):
        resources.resolve_project(_ns(project=None))


def test_resolve_project_accepts_a_uedcli_toml_file(tmp_path):
    proj, _ = _project(tmp_path)
    got = resources.resolve_project(_ns(project=str(proj / "uedcli.toml")))
    assert got.root == str(proj)


def test_bad_project_config_exits_2_not_a_traceback(tmp_path):
    # A user-schema uedcli.toml (has [games.*]) is not a valid PROJECT config → config.ConfigError,
    # which must be caught to a clean exit 2, never a bare traceback.
    bad = tmp_path / "bad"
    bad.mkdir(parents=True)
    (bad / "uedcli.toml").write_text("[games.deusex]\npaths = \"x\"\n")
    assert dispatch.dispatch(_ns(cmd="level", sub="status", project=str(bad))) == 2


def test_resolve_project_names_the_old_layout_in_the_error(tmp_path, monkeypatch, capsys):
    # Regression (spec §8 / acceptance §10.5): a pre-migration checkout — an old-layout
    # `<child>/config.toml` project but no `uedcli.toml` — gets the explicit migration hint.
    (tmp_path / "uedcli").mkdir()
    (tmp_path / "uedcli" / "config.toml").write_text('game = "deusex"\n')
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(dispatch.ProjectError) as e:
        resources.resolve_project(_ns(project=None))
    msg = str(e.value)
    assert "old-layout" in msg and "retired" in msg
    assert str(tmp_path / "uedcli.toml") in msg            # names the migration target


# --- Task B: the ambient level ($UEDCLI_LEVEL), resolved by resolve_level ---
# `level select` was removed (decisions 2026-07-20): the current level is now an ambient
# environment variable, resolved by `level_sources.resolve_level(env_level=…, maps_dir=…)`.

def test_resolve_level_returns_the_env_level(tmp_path):
    proj, name = _project(tmp_path)
    got = level_sources.resolve_level(env_level=name, maps_dir=proj / "maps")
    assert got == name


def test_resolve_level_unset_env_errors(tmp_path):
    proj, _ = _project(tmp_path)
    with pytest.raises(errors.LevelSelectionError):
        level_sources.resolve_level(env_level=None, maps_dir=proj / "maps")


def test_resolve_level_nonexistent_errors(tmp_path):
    proj, _ = _project(tmp_path)
    with pytest.raises(errors.LevelSelectionError):
        level_sources.resolve_level(env_level="ghost", maps_dir=proj / "maps")


# --- level create (scaffold a LevelInfo so materialize/verify works) ---

def test_level_create_scaffolds_a_levelinfo_and_refuses_reclobber(tmp_path):
    proj, _ = _project(tmp_path)
    rc = dispatch.dispatch(_ns(cmd="level", sub="create", name="MyLevel", project=str(proj)))
    assert rc == 0
    li = proj / "maps" / "MyLevel" / "actors" / "LevelInfo"
    assert (li / "actor.t3d").exists() and (li / "order_value").exists()
    assert "Engine.LevelInfo" in (li / "actor.t3d").read_text()
    # re-create over the existing non-empty level is refused (exit 2), never clobbers
    assert dispatch.dispatch(_ns(cmd="level", sub="create", name="MyLevel",
                                 project=str(proj))) == 2


def test_level_create_prints_the_export_hint(tmp_path, capsys):
    # `level create` can't set the parent shell's env (a child process can't), so instead of the
    # removed `--select` it prints the `export UEDCLI_LEVEL=<name>` hint to stderr (decisions
    # 2026-07-20).
    proj, _ = _project(tmp_path)
    assert dispatch.dispatch(_ns(cmd="level", sub="create", name="Fresh", project=str(proj))) == 0
    assert "export UEDCLI_LEVEL=Fresh" in capsys.readouterr().err


def test_level_create_rejects_a_bad_name(tmp_path):
    proj, _ = _project(tmp_path)
    assert dispatch.dispatch(_ns(cmd="level", sub="create", name="a/b",
                                 project=str(proj))) == 2


# --- Task C: level status ---

def test_level_status_reports_counts_and_dup_order(tmp_path, capsys, monkeypatch):
    proj, name = _project(tmp_path)
    lvl = Level(actors={
        "Wall_a1": Actor(name="Wall_a1", cls="Brush"),
        "Light_b2": Actor(name="Light_b2", cls="Light"),
        "Light_c3": Actor(name="Light_c3", cls="Light"),
    })
    lvl.actors["Wall_a1"].brush = Brush(model_name="Model_Wall_a1", polys=[])
    trunk.write_level(proj / "maps" / name, lvl,
                      {"Wall_a1": "m", "Light_b2": "p", "Light_c3": "p"})   # dup order_value 'p'
    monkeypatch.setenv("UEDCLI_LEVEL", name)

    assert dispatch.dispatch(_ns(cmd="level", sub="status", project=str(proj))) == 0
    out = capsys.readouterr().out
    assert f"level: {name}" in out
    assert "actors: 3  (1 brush, 2 point)" in out
    assert "shared by 2+ actors" in out             # the dup-order_value warning surfaces


def test_level_status_json_shape(tmp_path, capsys, monkeypatch):
    import json
    proj, name = _project(tmp_path)
    lvl = Level(actors={
        "Wall_a1": Actor(name="Wall_a1", cls="Brush"),
        "Light_b2": Actor(name="Light_b2", cls="Light"),
    })
    lvl.actors["Wall_a1"].brush = Brush(model_name="Model_Wall_a1", polys=[])
    trunk.write_level(proj / "maps" / name, lvl, {"Wall_a1": "m", "Light_b2": "p"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    assert dispatch.dispatch(_ns(cmd="level", sub="status", json=True, project=str(proj))) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["kind"] == "level" and data["name"] == name
    assert data["actors"] == {"total": 2, "brush": 1, "point": 1}
    assert data["duplicate_order_values"] == 0
    assert "git" in data and isinstance(data["texture_packages"], list)


def test_level_status_json_no_selection_is_explicit_null(tmp_path, capsys, monkeypatch):
    import json
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    proj, _ = _project(tmp_path)
    assert dispatch.dispatch(_ns(cmd="level", sub="status", json=True, tree=None,
                                 project=str(proj))) == 0
    assert json.loads(capsys.readouterr().out) == {"selected": None}


def test_level_status_prints_hint_when_nothing_selected(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    proj, _ = _project(tmp_path)
    assert dispatch.dispatch(_ns(cmd="level", sub="status", tree=None, project=str(proj))) == 0
    # the "no level" hint now names the env var (NO_LEVEL_MSG), not the removed pointer
    assert level_sources.NO_LEVEL_MSG in capsys.readouterr().out


def test_level_status_git_hint_appears_in_a_repo(tmp_path, capsys, monkeypatch):
    proj, name = _project(tmp_path)
    root = proj.parent                              # the content-tree root
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"],
                   check=True, env={**__import__("os").environ, **env})
    trunk.write_level(proj / "maps" / name,
                      Level(actors={"L_1": Actor(name="L_1", cls="Light")}), {"L_1": "m"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    dispatch.dispatch(_ns(cmd="level", sub="status", project=str(proj)))
    assert "on branch" in capsys.readouterr().out


# --- level list ---

def test_list_levels_helper_skips_non_levels_and_sorts(tmp_path):
    maps = tmp_path / "maps"
    for n in ("Zeta", "alpha", "Beta"):
        (maps / n / "actors").mkdir(parents=True)     # real trunks (have an actors/ tree)
    (maps / ".locks").mkdir()                          # the lock home — dotted, skipped
    (maps / ".hidden" / "actors").mkdir(parents=True)  # dotted BUT has actors/ → the dot rule excludes it
    (maps / "stray").mkdir()                           # a bare dir, no actors/ — not a level
    (maps / "afile.txt").write_text("x")               # a file — skipped
    # case-insensitive sort, ties by exact name; non-levels (incl. the dotted-with-actors/) excluded
    assert level_sources.list_levels(maps) == ["alpha", "Beta", "Zeta"]


def test_list_levels_helper_empty_when_maps_is_a_file(tmp_path):
    f = tmp_path / "maps"
    f.write_text("not a dir")
    assert level_sources.list_levels(f) == []


def test_list_levels_helper_empty_when_maps_absent(tmp_path):
    assert level_sources.list_levels(tmp_path / "nope") == []


def test_level_list_prints_names_to_stdout_count_to_stderr(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    proj, _ = _project(tmp_path)
    for n in ("castle", "hangar"):
        dispatch.dispatch(_ns(cmd="level", sub="create", name=n, project=str(proj)))
    capsys.readouterr()
    assert dispatch.dispatch(_ns(cmd="level", sub="list", json=False, project=str(proj))) == 0
    cap = capsys.readouterr()
    # the fixture's own bare maps/<name>/ (no actors/) is NOT a level, so only the two created ones
    assert cap.out.splitlines() == ["castle", "hangar"]
    assert "2 level(s)" in cap.err and "no level set ($UEDCLI_LEVEL unset)" in cap.err


def test_level_list_notes_the_active_level_on_stderr(tmp_path, capsys, monkeypatch):
    proj, _ = _project(tmp_path)
    dispatch.dispatch(_ns(cmd="level", sub="create", name="castle", project=str(proj)))
    monkeypatch.setenv("UEDCLI_LEVEL", "castle")
    capsys.readouterr()
    dispatch.dispatch(_ns(cmd="level", sub="list", json=False, project=str(proj)))
    assert "$UEDCLI_LEVEL=castle" in capsys.readouterr().err


def test_level_list_json_marks_active(tmp_path, capsys, monkeypatch):
    import json
    proj, _ = _project(tmp_path)
    dispatch.dispatch(_ns(cmd="level", sub="create", name="castle", project=str(proj)))
    dispatch.dispatch(_ns(cmd="level", sub="create", name="hangar", project=str(proj)))
    monkeypatch.setenv("UEDCLI_LEVEL", "castle")
    capsys.readouterr()
    assert dispatch.dispatch(_ns(cmd="level", sub="list", json=True, project=str(proj))) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == [{"name": "castle", "active": True},
                    {"name": "hangar", "active": False}]


def test_level_list_empty_stdout_when_no_levels(tmp_path, capsys):
    proj, _ = _project(tmp_path)
    (proj / "maps" / "20_AireGardens").rmdir()          # drop the fixture's bare dir → truly empty
    capsys.readouterr()
    assert dispatch.dispatch(_ns(cmd="level", sub="list", json=False, project=str(proj))) == 0
    cap = capsys.readouterr()
    assert cap.out == "" and "0 level(s)" in cap.err


def test_level_list_json_empty_is_empty_array(tmp_path, capsys):
    proj, _ = _project(tmp_path)
    (proj / "maps" / "20_AireGardens").rmdir()
    capsys.readouterr()
    assert dispatch.dispatch(_ns(cmd="level", sub="list", json=True, project=str(proj))) == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_level_list_flags_a_stale_active_level(tmp_path, capsys, monkeypatch):
    """A `$UEDCLI_LEVEL` whose level no longer lists (its actors/ tree removed) must be flagged
    not-listed on stderr, not reported as if present — keeping stderr consistent with stdout/--json
    (which mark nothing active). Reviewer gate, 2026-07-19; env model, 2026-07-20."""
    import json
    import shutil
    proj, _ = _project(tmp_path)
    dispatch.dispatch(_ns(cmd="level", sub="create", name="castle", project=str(proj)))
    monkeypatch.setenv("UEDCLI_LEVEL", "castle")
    shutil.rmtree(proj / "maps" / "castle" / "actors")   # env still says castle; no longer a trunk
    capsys.readouterr()
    assert dispatch.dispatch(_ns(cmd="level", sub="list", json=False, project=str(proj))) == 0
    cap = capsys.readouterr()
    assert cap.out == "" and "$UEDCLI_LEVEL=castle (not listed)" in cap.err
    # --json agrees: no row is marked active (the stale level isn't listed)
    dispatch.dispatch(_ns(cmd="level", sub="list", json=True, project=str(proj)))
    assert json.loads(capsys.readouterr().out) == []


# --- Task D: the self-ignoring state dir ---
# The removed `.uedcli/current-level` pointer is gone (the level is now the ambient
# $UEDCLI_LEVEL — decisions 2026-07-20). The self-ignore guarantee it used to carry now
# lives on `config.state_dir(create=True)`, so the intent is re-asserted there.

def test_state_dir_writes_the_self_ignore(tmp_path):
    from uedcli import config
    root = tmp_path / "proj"
    root.mkdir()
    d = config.state_dir(root, create=True)
    assert d == root / ".uedcli"
    assert (root / ".uedcli" / ".gitignore").read_text() == "*\n"   # bare `*` is canonical


def test_level_create_and_resolve_reject_dotted_names(tmp_path):
    """`.locks` is the maps-dir lock home — a dotted level name would nest a level inside the
    self-ignored dir, silently invisible to git (review fix, 2026-07-18). Both the `create` verb
    and `resolve_level` (the ambient-$UEDCLI_LEVEL reader) must reject it."""
    proj, _ = _project(tmp_path)
    assert dispatch.dispatch(_ns(cmd="level", sub="create", name=".locks",
                                 project=str(proj))) == 2
    with pytest.raises(errors.LevelSelectionError):
        level_sources.resolve_level(env_level=".locks", maps_dir=proj / "maps")
