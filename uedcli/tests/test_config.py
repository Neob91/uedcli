"""Tests for the global-CLI config + path-resolution module (`uedcli/config.py`).

Covers the reconciled design (dev/docs/direction/projects-and-config.md 2026-06-29 → 2026-07-01; directory model 2026-07-14
03:30; project layout 2026-07-17 20:58): per-user `[games.*]` config, per-project `<root>/
uedcli.toml` (the dir containing the file IS the project root), required `game`, root-relative
managed-dir defaults (`maps/`, `prefabs/`, `texture-catalog/`), dropped `id`/`name` keys, schema
classification, the colon-separated DIRECTORY resolution (`resolve_dirs`) + the scan-and-compose
search path (`composed_search_dirs` directory-dedup / `composed_search_files` stem-dedup; identity
= bare stem), project resolution by `uedcli.toml` walk-up (nearest wins), and the self-ignoring
`.uedcli/` state dir.
"""
from __future__ import annotations

import os

import pytest

from uedcli import config
from uedcli import packages


# --------------------------------------------------------------------------- helpers

def _write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def _touch_pkg(dir_path: str, name: str) -> str:
    os.makedirs(dir_path, exist_ok=True)
    p = os.path.join(dir_path, name)
    with open(p, "wb") as f:
        f.write(b"\x00")
    return p


# --------------------------------------------------------------------------- value objects + classify

def test_it_builds_the_value_objects():
    sub = config.Substrate(name="deusex", paths="/g/System")
    user = config.UserConfig(games={"deusex": sub}, source="/home/me/.uedcli/config.toml")
    proj = config.Project(root="/p", game="deusex", paths="Maps", source="/p/uedcli.toml")
    assert user.games["deusex"].paths == "/g/System"
    assert proj.root == "/p" and proj.game == "deusex"


def test_it_classifies_a_games_table_as_user_config():
    assert config._classify({"games": {"deusex": {"paths": "/x/System"}}}) == "user"


def test_it_classifies_a_top_level_project_key_as_project_config():
    assert config._classify({"game": "deusex", "paths": "Maps"}) == "project"


def test_it_rejects_a_hybrid_config_naming_both_schemas():
    with pytest.raises(config.ConfigError) as e:
        config._classify({"games": {"deusex": {"paths": "/x/System"}}, "game": "deusex"})
    assert "games" in str(e.value) and "game" in str(e.value)


def test_it_rejects_an_unclassifiable_empty_config():
    with pytest.raises(config.ConfigError):
        config._classify({})


# --------------------------------------------------------------------------- load_user_config

def test_it_loads_a_multi_game_user_config(tmp_path):
    p = _write(str(tmp_path / "config.toml"),
               '[games.deusex]\npaths = "/g/DeusEx/System:/g/DeusEx/Textures"\n'
               '[games.unreal]\npaths = "/g/Unreal/System"\n')
    cfg = config.load_user_config(p)
    assert set(cfg.games) == {"deusex", "unreal"}
    assert cfg.games["deusex"].paths == "/g/DeusEx/System:/g/DeusEx/Textures"
    assert cfg.source == p


def test_it_returns_none_when_the_user_config_is_absent(tmp_path):
    assert config.load_user_config(str(tmp_path / "nope.toml")) is None


def test_it_errors_when_a_game_has_no_paths(tmp_path):
    p = _write(str(tmp_path / "config.toml"), '[games.deusex]\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_user_config(p)
    assert "paths" in str(e.value)


def test_it_errors_on_a_relative_dir_in_the_user_config(tmp_path):
    p = _write(str(tmp_path / "config.toml"), '[games.deusex]\npaths = "System"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_user_config(p)
    assert "absolute" in str(e.value).lower()


def test_it_errors_on_an_unknown_game_key(tmp_path):
    p = _write(str(tmp_path / "config.toml"),
               '[games.deusex]\npaths = "/g/System"\nimage = "x"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_user_config(p)
    assert "image" in str(e.value)


def test_it_errors_on_a_dropped_defaults_table_as_unknown_top_key(tmp_path):
    p = _write(str(tmp_path / "config.toml"),
               '[games.deusex]\npaths = "/g/System"\n[defaults]\ngame = "deusex"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_user_config(p)
    assert "defaults" in str(e.value)


def test_it_errors_when_the_user_config_is_actually_a_project_config(tmp_path):
    p = _write(str(tmp_path / "uc" / "config.toml"), 'game = "deusex"\npaths = "Maps"\n')
    with pytest.raises(config.ConfigError):
        config.load_user_config(p)


def test_it_errors_when_the_user_config_has_no_games(tmp_path):
    p = _write(str(tmp_path / "config.toml"), '[other]\nx = 1\n')
    with pytest.raises(config.ConfigError):
        config.load_user_config(p)


# --------------------------------------------------------------------------- load_project

def test_it_loads_a_project_with_the_marker_dir_as_the_root(tmp_path):
    root = tmp_path / "my_cool_project"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\npaths = "Maps:LUM"\n')
    proj = config.load_project(str(root))
    assert proj.root == str(root)                       # the dir holding uedcli.toml IS the root
    assert proj.game == "deusex"
    assert proj.paths == "Maps:LUM"


def test_it_loads_a_project_given_its_uedcli_toml_path(tmp_path):
    toml = tmp_path / "proj" / "uedcli.toml"
    _write(str(toml), 'game = "deusex"\n')
    proj = config.load_project(str(toml))
    assert proj.root == str(tmp_path / "proj")


def test_it_errors_when_a_project_omits_the_required_game(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'paths = "Maps"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_project(str(root))
    assert "game" in str(e.value)


def test_it_errors_when_a_project_config_carries_a_games_table(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\n[games.deusex]\npaths = "/x/System"\n')
    with pytest.raises(config.ConfigError):
        config.load_project(str(root))


def test_it_errors_on_an_unknown_project_key(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\nsubstrate = "deusex"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_project(str(root))
    assert "substrate" in str(e.value)


def test_it_rejects_the_dropped_id_and_name_keys(tmp_path):
    # `id`/`name` were dropped with the registry (dev/docs/direction/projects-and-config.md 2026-07-17 20:58 §2) — a file
    # still carrying them gets the standard unknown-key error naming them.
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\nname = "lum"\nid = "x"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load_project(str(root))
    assert "name" in str(e.value) and "id" in str(e.value)


def test_it_errors_when_the_project_config_is_missing(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        config.load_project(str(tmp_path / "p"))
    assert "uedcli.toml" in str(e.value)


def test_it_resolves_catalog_prefabs_maps_defaults_under_the_root(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\n')
    proj = config.load_project(str(root))
    assert config.project_catalog_dir(proj) == str(root / "texture-catalog")
    assert config.project_prefabs_dir(proj) == str(root / "prefabs")
    assert config.project_maps_dir(proj) == str(root / "maps")


def test_it_resolves_an_overridden_catalog_relative_to_the_root(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\ncatalog = "cat"\n')
    proj = config.load_project(str(root))
    assert config.project_catalog_dir(proj) == str(root / "cat")


def test_it_points_managed_dirs_at_existing_repo_dirs(tmp_path):
    # The spec's headline case: a repo's EXISTING `Prefabs/`/`uedcli/maps` dirs are used in
    # place — no parallel tree (acceptance §10.2).
    root = tmp_path / "repo"
    _write(str(root / "uedcli.toml"),
           'game = "deusex"\nmaps = "uedcli/maps"\nprefabs = "Prefabs"\n')
    proj = config.load_project(str(root))
    assert config.project_maps_dir(proj) == str(root / "uedcli" / "maps")
    assert config.project_prefabs_dir(proj) == str(root / "Prefabs")


# --------------------------------------------------------------------------- resolve_dirs (dirs, not globs)

def test_it_resolves_dirs_in_order(tmp_path):
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    out = config.resolve_dirs(f"{tmp_path}/A:{tmp_path}/B", "/")
    assert out == [str(tmp_path / "A"), str(tmp_path / "B")]


def test_it_skips_a_nonexistent_dir_rather_than_erroring(tmp_path):
    (tmp_path / "A").mkdir()
    # B does not exist → skipped (offline-safe), not an error; A still resolves.
    out = config.resolve_dirs(f"{tmp_path}/A:{tmp_path}/B", "/")
    assert out == [str(tmp_path / "A")]


def test_it_resolves_a_relative_dir_against_the_base(tmp_path):
    (tmp_path / "Maps").mkdir()
    out = config.resolve_dirs("Maps", str(tmp_path))
    assert out == [str(tmp_path / "Maps")]


def test_it_rejects_a_leftover_glob_as_the_dirs_not_globs_migration_error(tmp_path):
    (tmp_path / "Textures").mkdir()
    with pytest.raises(config.ConfigError) as e:
        config.resolve_dirs(f"{tmp_path}/Textures/*.utx", "/")
    assert "directories now" in str(e.value) and "*.ext" in str(e.value)


def test_it_rejects_a_recursive_glob_dir(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        config.resolve_dirs(f"{tmp_path}/**/Textures", "/")
    assert "directories now" in str(e.value)          # ** is a glob char → same migration error


def test_it_rejects_a_relative_dir_when_absolute_required(tmp_path):
    with pytest.raises(config.ConfigError):
        config.resolve_dirs("System", str(tmp_path), require_absolute=True)


def test_it_rejects_a_colon_inside_a_dir_element(tmp_path):
    with pytest.raises(config.ConfigError):
        config.resolve_dirs(r"Z:\Textures", str(tmp_path))


def test_it_skips_empty_dir_elements(tmp_path):
    (tmp_path / "A").mkdir()
    out = config.resolve_dirs(f"::{tmp_path}/A: :", "/")
    assert out == [str(tmp_path / "A")]


def test_it_returns_empty_for_an_empty_paths_string():
    assert config.resolve_dirs("", "/") == []


# --------------------------------------------------------------------------- composition + game selection

def _user_cfg(tmp_path, **games) -> config.UserConfig:
    body = "".join(f'[games.{n}]\npaths = "{p}"\n' for n, p in games.items())
    return config.load_user_config(_write(str(tmp_path / "config.toml"), body))


def test_it_selects_the_projects_game_substrate(tmp_path):
    user = _user_cfg(tmp_path, deusex=f"{tmp_path}/base")
    proj = config.Project(root="/p", game="deusex")
    assert config.select_substrate(proj, user).name == "deusex"


def test_it_errors_when_the_projects_game_is_unknown(tmp_path):
    user = _user_cfg(tmp_path, deusex=f"{tmp_path}/base")
    proj = config.Project(root="/p", game="unreal")
    with pytest.raises(config.ConfigError) as e:
        config.select_substrate(proj, user)
    assert "unreal" in str(e.value) and "deusex" in str(e.value)


def test_it_has_no_sole_game_fallback(tmp_path):
    user = _user_cfg(tmp_path, deusex=f"{tmp_path}/base")
    proj = config.Project(root="/p", game="other")
    with pytest.raises(config.ConfigError):
        config.select_substrate(proj, user)


def test_it_composes_search_dirs_project_first_then_base_deduped_by_dir(tmp_path):
    base = tmp_path / "base"; base.mkdir()
    shared = tmp_path / "shared"; shared.mkdir()          # a dir listed by BOTH project and base
    user = _user_cfg(tmp_path, deusex=f"{shared}:{base}")
    root = tmp_path / "proj"
    (root / "Textures").mkdir(parents=True)
    _write(str(root / "uedcli.toml"), f'game = "deusex"\npaths = "Textures:{shared}"\n')
    proj = config.load_project(str(root))
    # project (Textures, shared) first; base (shared already seen, base) — shared kept once, first.
    assert config.composed_search_dirs(proj, user) == [
        str(root / "Textures"), str(shared), str(base)]


def test_it_composes_files_scanning_by_extension_project_shadowing_base(tmp_path):
    base = tmp_path / "base"
    _touch_pkg(str(base), "CoreTexMetal.utx")
    _touch_pkg(str(base), "Skins.utx")
    _touch_pkg(str(base), "readme.txt")                     # non-package → not scanned in
    user = _user_cfg(tmp_path, deusex=str(base))
    root = tmp_path / "proj"
    _touch_pkg(str(root / "Textures"), "CoreTexMetal.utx")  # project override, same stem
    _write(str(root / "uedcli.toml"), 'game = "deusex"\npaths = "Textures"\n')
    proj = config.load_project(str(root))
    composed = config.composed_search_files(proj, user)
    by_stem = {config.pkg_stem(p): (p, prov) for p, prov in composed}
    assert by_stem["CoreTexMetal"] == (str(root / "Textures" / "CoreTexMetal.utx"), "project")
    assert by_stem["Skins"] == (str(base / "Skins.utx"), "base")
    assert "readme" not in {os.path.basename(p).split(".")[0] for p, _ in composed}


def test_it_composes_files_stem_dedups_across_extensions_keep_first(tmp_path):
    base = tmp_path / "base"
    _touch_pkg(str(base), "Foo.u")
    _touch_pkg(str(base), "Foo.utx")                        # same stem, different ext → one identity
    user = _user_cfg(tmp_path, deusex=str(base))
    _write(str(tmp_path / "proj" / "uedcli.toml"), 'game = "deusex"\n')
    proj = config.load_project(str(tmp_path / "proj"))
    composed = config.composed_search_files(proj, user)
    # case-folded name order within the dir → "Foo.u" precedes "Foo.utx", kept first.
    assert composed == [(str(base / "Foo.u"), "base")]


def test_it_scans_extensions_case_insensitively(tmp_path):
    base = tmp_path / "base"
    _touch_pkg(str(base), "Loud.UTX")                       # uppercase ext must still match
    user = _user_cfg(tmp_path, deusex=str(base))
    _write(str(tmp_path / "proj" / "uedcli.toml"), 'game = "deusex"\n')
    proj = config.load_project(str(tmp_path / "proj"))
    composed = config.composed_search_files(proj, user)
    assert composed == [(str(base / "Loud.UTX"), "base")]


def test_it_ignores_a_package_named_subdirectory(tmp_path):
    base = tmp_path / "base"
    (base / "NotReal.utx").mkdir(parents=True)              # a DIR named like a package → not a file
    _touch_pkg(str(base), "Real.utx")
    user = _user_cfg(tmp_path, deusex=str(base))
    _write(str(tmp_path / "proj" / "uedcli.toml"), 'game = "deusex"\n')
    proj = config.load_project(str(tmp_path / "proj"))
    picked = {config.pkg_stem(p) for p, _ in config.composed_search_files(proj, user)}
    assert picked == {"Real"}                               # the subdir is not emitted as a package


def test_it_composes_base_only_when_the_project_has_no_paths(tmp_path):
    base = tmp_path / "base"
    _touch_pkg(str(base), "Engine.u")
    user = _user_cfg(tmp_path, deusex=str(base))
    _write(str(tmp_path / "proj" / "uedcli.toml"), 'game = "deusex"\n')
    proj = config.load_project(str(tmp_path / "proj"))
    composed = config.composed_search_files(proj, user)
    assert composed == [(str(base / "Engine.u"), "base")]


# --------------------------------------------------------------------------- project resolution + walk-up

def _project_at(root, *, game="deusex"):
    """Write `<root>/uedcli.toml`; returns the root."""
    _write(os.path.join(root, "uedcli.toml"), f'game = "{game}"\n')
    return root


def test_it_walks_up_to_the_nearest_uedcli_toml(tmp_path):
    root = _project_at(str(tmp_path / "proj"))
    deep = tmp_path / "proj" / "a" / "b"
    os.makedirs(deep, exist_ok=True)
    assert config.walk_up_root(str(deep)) == root


def test_it_walks_up_nearest_wins_for_nested_projects(tmp_path):
    # A nested project shadows the outer one, `.git`-style (spec §4.3 / acceptance §10.7).
    _project_at(str(tmp_path / "outer"))
    inner = _project_at(str(tmp_path / "outer" / "inner"))
    deep = tmp_path / "outer" / "inner" / "sub"
    os.makedirs(deep, exist_ok=True)
    assert config.walk_up_root(str(deep)) == inner
    assert config.walk_up_root(str(tmp_path / "outer")) == str(tmp_path / "outer")


def test_it_returns_none_when_no_marker_is_found(tmp_path):
    deep = tmp_path / "nothing" / "here"
    os.makedirs(deep, exist_ok=True)
    assert config.walk_up_root(str(deep)) is None


def test_it_does_not_discover_an_old_layout_child_config_toml(tmp_path):
    # The old `<child>/config.toml` layout is retired: walk-up keys on the `uedcli.toml`
    # FILENAME only (no child-dir scan, no schema sniffing).
    _write(str(tmp_path / "proj" / "uedcli" / "config.toml"), 'game = "deusex"\n')
    assert config.walk_up_root(str(tmp_path / "proj")) is None


def test_a_malformed_marker_found_by_walk_up_is_a_hard_error(tmp_path):
    root = tmp_path / "proj"
    _write(str(root / "uedcli.toml"), 'game = "deusex\n')     # unterminated string
    with pytest.raises(config.ConfigError) as e:
        config.resolve_project(cwd=str(root))
    assert "invalid TOML" in str(e.value)


def test_an_unreadable_marker_found_by_walk_up_is_a_hard_error(tmp_path):
    # A permission-denied uedcli.toml IS the project marker — never silently climbed past
    # (binding to an outer project would be worse than erroring; spec §4).
    if os.geteuid() == 0:
        pytest.skip("running as root — file modes don't deny reads")
    root = tmp_path / "proj"
    marker = _write(str(root / "uedcli.toml"), 'game = "deusex"\n')
    os.chmod(marker, 0)
    try:
        with pytest.raises(config.ConfigError) as e:
            config.resolve_project(cwd=str(root))
        assert "cannot read" in str(e.value)
    finally:
        os.chmod(marker, 0o644)


def test_it_finds_an_old_layout_project_dir_for_the_error_hint(tmp_path):
    # The failure-path-only detector behind the migration hint (spec §8).
    _write(str(tmp_path / "repo" / "uedcli" / "config.toml"), 'game = "deusex"\n')
    deep = tmp_path / "repo" / "sub"
    os.makedirs(deep, exist_ok=True)
    assert config.find_old_layout_project_dir(str(deep)) == str(tmp_path / "repo" / "uedcli")
    assert config.find_old_layout_project_dir(str(tmp_path / "elsewhere")) is None


def test_it_resolves_a_project_from_a_path_flag(tmp_path):
    root = _project_at(str(tmp_path / "proj"))
    proj = config.resolve_project(project_flag=root, cwd="/tmp")
    assert proj is not None and proj.root == root


def test_it_resolves_a_project_from_the_env_when_no_flag(tmp_path):
    root = _project_at(str(tmp_path / "proj"))
    proj = config.resolve_project(env_project=root, cwd="/tmp")
    assert proj is not None and proj.root == root


def test_it_errors_on_a_bare_name_without_a_registry_hook(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        config.resolve_project(project_flag="lum", cwd="/tmp")
    assert "lum" in str(e.value) and "registry" in str(e.value).lower()


def test_it_falls_through_to_walk_up_when_no_flag_or_env(tmp_path):
    root = _project_at(str(tmp_path / "proj"))
    proj = config.resolve_project(cwd=str(tmp_path / "proj"))
    assert proj is not None and proj.root == root


def test_it_returns_none_when_nothing_resolves(tmp_path):
    assert config.resolve_project(cwd=str(tmp_path)) is None


# --------------------------------------------------------------------------- state dir

def test_state_dir_create_writes_the_self_ignore_once(tmp_path):
    d = config.state_dir(tmp_path, create=True)
    assert d == tmp_path / ".uedcli"
    assert (d / ".gitignore").read_text() == "*\n"
    # An existing dir is left alone: a deliberately-deleted ignore file is NOT rewritten.
    (d / ".gitignore").unlink()
    config.state_dir(tmp_path, create=True)
    assert not (d / ".gitignore").exists()


def test_state_dir_without_create_is_a_pure_path(tmp_path):
    d = config.state_dir(tmp_path)
    assert d == tmp_path / ".uedcli" and not d.exists()


def test_state_subdir_creates_the_nested_dir_and_the_self_ignore(tmp_path):
    d = config.state_subdir(tmp_path, "stash", create=True)
    assert d == tmp_path / ".uedcli" / "stash" and d.is_dir()
    assert (tmp_path / ".uedcli" / ".gitignore").read_text() == "*\n"


# --------------------------------------------------------------------------- review-driven coverage

def test_it_prefers_the_project_flag_over_the_env(tmp_path):
    flag_root = _project_at(str(tmp_path / "flagproj"))
    _project_at(str(tmp_path / "envproj"))
    proj = config.resolve_project(project_flag=flag_root,
                                  env_project=str(tmp_path / "envproj"), cwd="/tmp")
    assert proj.root == flag_root   # tier 1 beats tier 2


def test_it_routes_a_bare_name_through_the_resolve_name_hook(tmp_path):
    seen = []
    sentinel = config.Project(root="/p", game="deusex")

    def hook(name):
        seen.append(name)
        return sentinel

    proj = config.resolve_project(project_flag="lum", cwd="/tmp", resolve_name=hook)
    assert proj is sentinel and seen == ["lum"]


def test_it_routes_a_bare_env_name_through_the_resolve_name_hook(tmp_path):
    sentinel = config.Project(root="/p", game="deusex")
    proj = config.resolve_project(env_project="lum", cwd="/tmp", resolve_name=lambda n: sentinel)
    assert proj is sentinel


def test_it_resolves_a_mixed_absolute_and_relative_dir_list(tmp_path):
    (tmp_path / "abs").mkdir()
    (tmp_path / "root" / "Textures").mkdir(parents=True)
    out = config.resolve_dirs(f"Textures:{tmp_path}/abs", str(tmp_path / "root"))
    assert out == [str(tmp_path / "root" / "Textures"),   # relative, vs base
                   str(tmp_path / "abs")]                  # absolute, verbatim


def test_it_honors_an_absolute_catalog_override(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), f'game = "deusex"\ncatalog = "{tmp_path}/shared-cat"\n')
    proj = config.load_project(str(root))
    assert config.project_catalog_dir(proj) == str(tmp_path / "shared-cat")   # verbatim, not joined


def test_it_resolves_overridden_prefabs_and_maps_relative_to_the_root(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\nprefabs = "pf"\nmaps = "levels"\n')
    proj = config.load_project(str(root))
    assert config.project_prefabs_dir(proj) == str(root / "pf")
    assert config.project_maps_dir(proj) == str(root / "levels")


def test_it_errors_on_malformed_toml_in_a_project_config(tmp_path):
    root = tmp_path / "p"
    _write(str(root / "uedcli.toml"), 'game = "deusex\n')   # unterminated string
    with pytest.raises(config.ConfigError) as e:
        config.load_project(str(root))
    assert "invalid TOML" in str(e.value)


def test_it_errors_on_malformed_toml_in_the_user_config(tmp_path):
    p = _write(str(tmp_path / "config.toml"), '[games.deusex]\npaths = /g/*.u\n')  # unquoted value
    with pytest.raises(config.ConfigError) as e:
        config.load_user_config(p)
    assert "invalid TOML" in str(e.value)


def test_it_anchors_project_paths_on_the_root(tmp_path):
    # `paths` elements resolve against the project root (the uedcli.toml dir).
    base = tmp_path / "base"
    _touch_pkg(str(base), "Engine.u")
    user = _user_cfg(tmp_path, deusex=str(base))
    root = tmp_path / "proj"
    _write(str(root / "uedcli.toml"), 'game = "deusex"\npaths = "Assets"\n')
    _touch_pkg(str(root / "Assets"), "Real.u")                 # under root → picked up
    proj = config.load_project(str(root))
    picked = {config.pkg_stem(p) for p, _ in config.composed_search_files(proj, user)}
    assert "Real" in picked


# --------------------------------------------------------------------------- regression guards

def test_it_keeps_pkg_exts_in_sync_with_packages():
    assert set(config.PKG_EXTS) == set(packages._PKG_EXTS)


def test_it_expands_home_for_the_user_config_path(monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", "/custom/home")
    assert config.user_config_path() == "/custom/home/config.toml"
    monkeypatch.delenv("UEDCLI_HOME", raising=False)
    assert config.user_config_path().endswith("/.uedcli/config.toml")


def test_user_cache_home_honors_uedcli_home(monkeypatch, tmp_path):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "myhome"))
    assert config.user_cache_home() == tmp_path / "myhome" / "cache"


def test_stub_cache_root_is_under_the_user_cache_home_and_creates_only_when_asked(monkeypatch, tmp_path):
    # Folded in from the deleted repo_paths.py (layout reorg slice 3): per-user, no `start` arg.
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    root = config.stub_cache_root()
    assert root == tmp_path / "cache" / "stubs" and not root.exists()   # pure path by default
    assert config.stub_cache_root(create=True).is_dir()


def test_texture_images_root_is_under_the_user_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    assert config.texture_images_root() == tmp_path / "cache" / "textures"


def test_user_cache_home_defaults_under_dot_uedcli(monkeypatch, tmp_path):
    # No $UEDCLI_HOME → `~/.uedcli/cache`; monkeypatch `Path.home` so the real home is never touched.
    monkeypatch.delenv("UEDCLI_HOME", raising=False)
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path / "fakehome"))
    assert config.user_cache_home() == tmp_path / "fakehome" / ".uedcli" / "cache"


def test_project_non_string_or_empty_keys_are_named_errors(tmp_path):
    """A hand-written `uedcli.toml` with a wrong-typed or empty value must be a named `ConfigError`
    at LOAD time — a `maps = 3` used to surface downstream as a raw `TypeError` from
    `_project_subdir`, and a `prefabs = ""` silently aliased the project root (review round 2,
    2026-07-18)."""
    for body, key in (('game = "dx"\nmaps = 3\n', "maps"),
                      ('game = "dx"\npaths = ["Textures"]\n', "paths"),
                      ('game = "dx"\nprefabs = ""\n', "prefabs"),
                      ('game = "dx"\ncatalog = "  "\n', "catalog"),
                      ('game = ""\n', "game")):
        (tmp_path / "uedcli.toml").write_text(body)
        with pytest.raises(config.ConfigError, match=key):
            config.load_project(str(tmp_path))


def test_state_dir_path_occupied_by_a_file_is_a_named_error(tmp_path):
    """`.uedcli` existing as a plain FILE must be a named ConfigError at creation — not a
    swallowed FileExistsError followed by a NotADirectoryError traceback downstream (round-3
    adversarial review, 2026-07-18)."""
    (tmp_path / ".uedcli").write_text("not a dir")
    with pytest.raises(config.ConfigError, match="not a directory"):
        config.state_dir(tmp_path, create=True)


def test_state_dir_on_unwritable_root_is_a_named_error(tmp_path):
    """A read-only project root must yield a clean ConfigError from state-dir creation, never a
    raw PermissionError traceback (round-3 adversarial review, 2026-07-18)."""
    if os.geteuid() == 0:
        pytest.skip("permission checks are void as root")
    ro = tmp_path / "ro-root"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        with pytest.raises(config.ConfigError, match="cannot create state dir"):
            config.state_dir(ro, create=True)
    finally:
        ro.chmod(0o755)


def test_walk_up_hard_errors_on_a_non_regular_file_marker(tmp_path):
    """A dangling-symlink (or directory) `uedcli.toml` must hard-error, not be climbed past —
    climbing past would bind a nested repo to an OUTER project, the exact hazard the
    unreadable-marker rule forbids (round-3 review, 2026-07-18)."""
    outer = tmp_path / "outer"
    inner = outer / "inner" / "sub"
    inner.mkdir(parents=True)
    (outer / "uedcli.toml").write_text('game = "dx"\n')
    (outer / "inner" / "uedcli.toml").symlink_to(tmp_path / "gone")
    with pytest.raises(config.ConfigError, match="not a regular file"):
        config.walk_up_root(str(inner))


def test_walk_up_hard_errors_on_an_unstatable_marker_instead_of_climbing_past(tmp_path):
    """An ancestor whose `uedcli.toml` cannot be stat'ed (permission-denied directory) is a STOP,
    not a skip. `except OSError: continue` used to climb straight past it and bind the caller to
    the OUTER project — silently editing the wrong tree, the exact hazard this function's own
    docstring rule forbids."""
    if os.geteuid() == 0:
        pytest.skip("permission checks are void as root")
    outer = tmp_path / "outer"
    blocked = outer / "blocked"
    deep = blocked / "sub"
    deep.mkdir(parents=True)
    (outer / "uedcli.toml").write_text('game = "dx"\n')
    (blocked / "uedcli.toml").write_text('game = "dx"\n')
    blocked.chmod(0o000)                      # stat of blocked/uedcli.toml → PermissionError
    try:
        with pytest.raises(config.ConfigError, match="cannot check for a project marker"):
            config.walk_up_root(str(deep))
    finally:
        blocked.chmod(0o755)


def test_a_windows_drive_in_the_user_config_paths_is_named_at_LOAD_time(tmp_path, monkeypatch):
    """A pasted `C:\\DX\\System` used to split on the `:` list separator and be reported as
    `dir must be absolute: 'C'` — a message about a path the user never typed. `load_user_config`
    runs long before `resolve_dirs`, so the dedicated drive-letter error has to fire there too."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('[games.deusex]\npaths = "C:\\\\DX\\\\System"\n')
    with pytest.raises(config.ConfigError, match="Windows-style drive") as ei:
        config.load_user_config(str(cfg))
    assert "games.deusex" in str(ei.value)          # names the offending table
    assert "must be absolute: 'C'" not in str(ei.value)   # NOT the old confusing message


def test_the_windows_drive_check_is_one_shared_helper(tmp_path):
    """Both readers of a colon-separated dir list go through `reject_windows_drive`, so the two
    can never drift into different messages (or one of them losing the check)."""
    for bad in ("C:\\DX\\System", "/ok:Z:/work"):
        with pytest.raises(config.ConfigError, match="Windows-style drive"):
            config.reject_windows_drive(bad)
        with pytest.raises(config.ConfigError, match="Windows-style drive"):
            config.resolve_dirs(bad, str(tmp_path))
    config.reject_windows_drive("/a:/b")            # ordinary separator colons are fine


def test_project_file_marker_must_be_named_uedcli_toml(tmp_path):
    """--project/UEDCLI_PROJECT pointing at a FILE accepts only an actual `uedcli.toml` — any
    other existing file is a named error, not a silently blessed marker (round-3 review)."""
    other = tmp_path / "notatoml.txt"
    other.write_text('game = "dx"\n')
    with pytest.raises(config.ConfigError, match="not a project marker"):
        config.load_project(str(other))
