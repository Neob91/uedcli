from pathlib import Path
from unittest import mock

import pytest

from uedcli.container_assets import paths_ini_lines, resource_mounts
from uedcli.packages import (ensure_load, ensure_load_message,
                             editor_search_dirs, missing_packages, obj_load_entries,
                             schema_resolver, schema_search_dirs, search_path_package_names,
                             unloadable_v68_packages, _remap_to_container)


def test_search_path_package_names_uses_pkg_stem_in_order():
    files = [("/proj/Textures/DXShared.utx", "project"),
             ("/opt/UED22/Engine.u", "base"),
             ("/opt/UED22/Core.u", "base")]
    assert search_path_package_names(files) == ["DXShared", "Engine", "Core"]


def test_search_path_package_names_skips_non_package_files_and_empty():
    assert search_path_package_names([]) == []
    assert search_path_package_names([("/x/readme.txt", "base")]) == []


def test_remap_bakes_ued22_to_opt():
    # UED22 is anchored PACKAGE-RELATIVE (tool_assets.uned_dir) — no repo_root arg anymore.
    from uedcli import tool_assets
    host = str(tool_assets.uned_dir() / "UED22" / "DeusEx.u")
    assert _remap_to_container(host, []) == "/opt/UED22/DeusEx.u"


def test_remap_content_file_to_a_resources_mount(tmp_path):
    # A config CONTENT dir → /resources/<n> via the THREADED mounts (no /deusex, no /content).
    tex = tmp_path / "Textures"; tex.mkdir()
    (tex / "X.utx").write_bytes(b"x")
    mounts = resource_mounts([str(tex)])
    assert _remap_to_container(str(tex / "X.utx"), mounts) == "/resources/r000/X.utx"


def test_remap_rejects_a_path_outside_the_known_roots():
    with pytest.raises(ValueError):
        _remap_to_container("/somewhere/else/X.utx", [])


def test_it_finds_all_manifest_packages_on_the_path(tmp_path):
    (tmp_path / "Core.u").write_bytes(b"x")
    (tmp_path / "engine.u").write_bytes(b"x")          # case-insensitive: Engine resolves
    assert missing_packages(["Core", "Engine"], [str(tmp_path)]) == []


def test_it_reports_the_complete_missing_set_not_just_the_first(tmp_path):
    (tmp_path / "Core.u").write_bytes(b"x")
    missing = missing_packages(["Core", "Effects", "NewYorkCity"], [str(tmp_path)])
    assert missing == ["Effects", "NewYorkCity"]       # sorted, complete


def test_ensure_load_message_names_every_missing_package():
    msg = ensure_load_message(["Effects", "NewYorkCity", "CoreTexMetal"])
    assert "Effects" in msg and "NewYorkCity" in msg and "CoreTexMetal" in msg
    assert "package path" in msg


def test_obj_load_entries_pairs_each_resolved_package_with_its_file(tmp_path):
    (tmp_path / "CoreTexMetal.utx").write_bytes(b"x")
    (tmp_path / "NewYorkCity.utx").write_bytes(b"x")
    entries = obj_load_entries(["CoreTexMetal", "NewYorkCity"], [str(tmp_path)])
    assert entries == [("CoreTexMetal", str(tmp_path / "CoreTexMetal.utx")),
                       ("NewYorkCity", str(tmp_path / "NewYorkCity.utx"))]


def test_obj_load_entries_skips_always_loaded_substrate_packages(tmp_path):
    (tmp_path / "Engine.u").write_bytes(b"x")
    (tmp_path / "Core.u").write_bytes(b"x")
    (tmp_path / "Editor.u").write_bytes(b"x")
    assert obj_load_entries(["Engine", "Core", "Editor"], [str(tmp_path)]) == []


def test_obj_load_entries_omits_an_unresolved_package_rather_than_erroring(tmp_path):
    assert obj_load_entries(["NoSuchPackage"], [str(tmp_path)]) == []


# --- ensure_load: the Paths ini-edit + explicit OBJ LOAD, shared by apply._materialize and
# qualify.export_and_qualify (moved here 2026-06-20 to avoid a circular import between them) --

def test_ensure_load_writes_full_paths_and_remaps_obj_loads_via_the_mounts(tmp_path):
    # asset-wiring cutover: Paths is the FULL container-visible set (paths_ini_lines(mounts)); a
    # content package resolved under a config CONTENT dir remaps to its /resources/<n> path.
    textures = tmp_path / "Textures"; textures.mkdir()
    (textures / "CoreTexMetal.utx").write_bytes(b"x")
    mounts = resource_mounts([str(textures)])
    driver = mock.Mock(container="c")
    with mock.patch("uedcli.packages.write_paths_and_reload", autospec=True) as wpr:
        ensure_load(driver, ["CoreTexMetal"], search_dirs=[str(textures)], mounts=mounts)
    wpr.assert_called_once_with("c", paths_ini_lines(mounts))     # /stubs + /opt/UED22 + /resources/r000
    driver.obj_load.assert_called_once_with("CoreTexMetal", "/resources/r000/CoreTexMetal.utx")


def test_ensure_load_skips_obj_load_for_a_package_not_on_the_search_path(tmp_path):
    driver = mock.Mock(container="c")
    with mock.patch("uedcli.packages.write_paths_and_reload", autospec=True):
        ensure_load(driver, ["NoSuchPackage"], search_dirs=[], mounts=[])
    driver.obj_load.assert_not_called()


def test_ensure_load_with_no_mounts_still_writes_the_stubs_and_ued22_paths(tmp_path):
    driver = mock.Mock(container="c")
    with mock.patch("uedcli.packages.write_paths_and_reload", autospec=True) as wpr:
        ensure_load(driver, [], search_dirs=[], mounts=[])       # must not raise
    # Per-ext Paths (dev/docs/direction/containers.md 2026-07-14 12:00 — bare `*` stalls boot; code roots are `*.u`).
    wpr.assert_called_once_with("c", ["Paths=/stubs/*.u", "Paths=/opt/UED22/*.u"])


def test_editor_search_dirs_puts_stub_cache_and_ued22_first(tmp_path, monkeypatch):
    # The config-driven editor load path: [stub cache, UED22, *content dirs], all HOST paths.
    # UED22 resolves package-relative (tool_assets), the stub cache per-user — from ANY cwd
    # (acceptance §10.4, offline: assert the resolved paths, no container needed).
    from uedcli import tool_assets
    home = tmp_path / "home"
    monkeypatch.setenv("UEDCLI_HOME", str(home))
    tex = tmp_path / "Textures"; tex.mkdir()
    monkeypatch.chdir(tmp_path)                     # a non-repo cwd must not matter
    dirs = editor_search_dirs([str(tex)])
    assert dirs == [str(home / "cache" / "stubs"),
                    str(tool_assets.uned_dir() / "UED22"),
                    str(tex)]


def test_unloadable_v68_flags_only_a_dot_u_under_a_config_mount():
    # A `.u` under a /resources mount is the game's OWN v68 code (no stub) → must be refused. A `.u`
    # under /stubs or /opt/UED22 (NOT a mount) is a v69 stub/substrate → safe. Content is safe.
    mounts = resource_mounts(["/g/System", "/g/Textures"])   # r000=System, r001=Textures
    entries = [
        ("DeusExDeco", "/g/System/DeusExDeco.u"),            # v68 code under a mount → FLAG
        ("LUM_CoreTex", "/g/Textures/LUM_CoreTex.utx"),      # content under a mount → safe
        ("DeusExItems", "/home/u/.uedcli/cache/stubs/DeusExItems.u"),  # v69 stub, not a mount → safe
        ("Engine", "/opt/UED22/Engine.u"),                   # substrate, not a mount → safe
    ]
    assert unloadable_v68_packages(entries, mounts) == ["DeusExDeco"]


def test_unloadable_v68_empty_when_nothing_is_a_mounted_dot_u():
    mounts = resource_mounts(["/g/Textures"])
    entries = [("LUM_CoreTex", "/g/Textures/LUM_CoreTex.utx")]
    assert unloadable_v68_packages(entries, mounts) == []


def test_ensure_load_refuses_an_unstubbed_v68_package_before_touching_the_editor():
    # The gate must raise (clean, named) BEFORE any driver command — never a v69-loads-v68 wedge.
    driver = mock.Mock()
    mounts = resource_mounts(["/g/System"])
    with mock.patch("uedcli.packages.obj_load_entries",
                    return_value=[("DeusExDeco", "/g/System/DeusExDeco.u")]):
        with pytest.raises(RuntimeError, match="DeusExDeco"):
            ensure_load(driver, ["DeusExDeco"], search_dirs=["/g/System"], mounts=mounts)
    driver.obj_load.assert_not_called()             # refused before any OBJ LOAD
    driver.dismiss_blocking_dialog.assert_not_called()


def test_remap_stub_cache_to_stubs_mount(tmp_path, monkeypatch):
    # The stub cache is the per-user `$UEDCLI_HOME/cache/stubs`, OUTSIDE repo_root; its fixed
    # root maps it to /stubs (checked when no /resources mount matches).
    home = tmp_path / "home"
    monkeypatch.setenv("UEDCLI_HOME", str(home))
    host = str(home / "cache" / "stubs" / "DeusExItems.u")
    assert _remap_to_container(host, []) == "/stubs/DeusExItems.u"


def test_remap_rejects_a_non_container_visible_path(tmp_path):
    # A path under no /resources mount, not the stub cache, not UED22 must fail loud (a resolution
    # bug), not silently map anywhere.
    host = str(tmp_path / ".uedcli" / "store" / "main" / "x.t3d")
    with pytest.raises(ValueError):
        _remap_to_container(host, [])




# ── schema_search_dirs / schema_resolver (actor-prop schema source) ─────────────
# Config-driven (dev/docs/direction/containers.md 2026-07-14): the schema path = the WHOLE composed config search path.
# `schema_resolver` resolves `<pkg>.u` by EXTENSION within it, so it finds the game's real v68 `.u`
# (a content dir simply has no `.u` for the name); never UED22 or the stub cache.


def _schema_project_and_user(tmp_path):
    from uedcli import config
    game_sys = tmp_path / "game" / "System"; game_sys.mkdir(parents=True)
    (game_sys / "DeusEx.u").write_text("x")                 # a v68 game CODE dir
    game_tex = tmp_path / "game" / "Textures"; game_tex.mkdir(parents=True)
    (game_tex / "Core.utx").write_text("x")                 # a CONTENT dir → must be excluded
    proj_sys = tmp_path / "proj" / "System"; proj_sys.mkdir(parents=True)
    (proj_sys / "Mod.u").write_text("x")                    # the mod's OWN code dir (project overlay)
    user = config.UserConfig(games={"deusex": config.Substrate(
        name="deusex", paths=f"{game_sys}:{game_tex}")})
    proj = config.Project(root=str(tmp_path / "proj"), game="deusex", paths="System")
    return proj, user, proj_sys, game_sys, game_tex


def test_schema_search_dirs_are_the_whole_composed_path_never_stubs_or_ued22(tmp_path):
    proj, user, proj_sys, game_sys, game_tex = _schema_project_and_user(tmp_path)
    dirs = schema_search_dirs(proj, user)
    # The whole composed set (project overlay first, then base) — content Textures INCLUDED (the
    # resolver picks the `.u` by extension; a content dir just has no `.u` for a name).
    assert dirs == [str(proj_sys), str(game_sys), str(game_tex)]
    assert not any("UED22" in d for d in dirs)
    assert not any("stubs" in d.lower() for d in dirs)
    assert not any("DeusExAssets" in d for d in dirs)       # hardcoded path is gone


def test_schema_resolver_picks_the_real_v68_dot_u_not_a_same_named_content_file(tmp_path):
    # A `.u` and a same-named `.utx` on the composed path: the resolver must return the `.u` (schema
    # lives in code), proving extension — not dir-role — discrimination.
    proj, user, proj_sys, game_sys, game_tex = _schema_project_and_user(tmp_path)
    (Path(game_tex) / "DeusEx.utx").write_text("x")         # same stem as game_sys/DeusEx.u
    resolve = schema_resolver(proj, user)
    assert resolve("DeusEx") == str(Path(game_sys) / "DeusEx.u")


def test_schema_search_dirs_empty_without_project_or_games_config(tmp_path):
    assert schema_search_dirs(None, None) == []
    _proj, user, *_ = _schema_project_and_user(tmp_path)
    assert schema_search_dirs(None, user) == []


def test_schema_resolver_finds_a_dot_u_and_misses_cleanly(tmp_path):
    proj, user, _proj_sys, game_sys, _game_tex = _schema_project_and_user(tmp_path)
    resolve = schema_resolver(proj, user)
    assert resolve("deusex") == str(game_sys / "DeusEx.u")   # case-insensitive match
    assert resolve("Nonexistent") is None                    # no-fallback miss -> caller SchemaErrors
