import os

import pytest

from uedcli import container_assets as ca
from uedcli.container_assets import Mount


def _mkfiles(d, names):
    for n in names:
        open(os.path.join(d, n), "w").close()


# --- resource_mounts / container_search_dirs / paths_ini_lines ---

def test_resource_mounts_index_is_stable_unique_and_ordered():
    ms = ca.resource_mounts(["/host/Textures", "/host/Maps", "/host/Sounds"])
    assert [m.container_dir for m in ms] == ["/resources/r000", "/resources/r001", "/resources/r002"]
    assert [m.host_dir for m in ms] == ["/host/Textures", "/host/Maps", "/host/Sounds"]


def test_container_search_dirs_puts_stubs_first_then_ued22_then_content():
    ms = ca.resource_mounts(["/host/Textures"])
    assert ca.container_search_dirs(ms) == ["/stubs", "/opt/UED22", "/resources/r000"]


def test_paths_ini_lines_per_ext_code_roots_are_dot_u_content_scans_present_exts(tmp_path):
    # UE1 Paths need an EXTENSION (`*.<ext>`, `*`=package name); a bare `*` stalls the editor at
    # boot (live-verified 2026-07-14). Code roots (/stubs, /opt/UED22) -> *.u; each content mount
    # emits only the content exts actually present in it.
    tex = tmp_path / "Textures"; tex.mkdir(); _mkfiles(tex, ["a.utx", "b.UTX", "readme.txt"])
    maps = tmp_path / "Maps"; maps.mkdir(); _mkfiles(maps, ["m.dx"])
    ms = ca.resource_mounts([str(tex), str(maps)])
    assert ca.paths_ini_lines(ms) == [
        "Paths=/stubs/*.u",
        "Paths=/opt/UED22/*.u",          # UED22's own Paths REGENERATED with an extension, not bare
        "Paths=/resources/r000/*.utx",   # Textures: only .utx present (case-insensitive)
        "Paths=/resources/r001/*.dx",    # Maps: only .dx
    ]


def test_paths_ini_lines_multi_ext_content_dir_emits_each_present_ext(tmp_path):
    d = tmp_path / "Mixed"; d.mkdir(); _mkfiles(d, ["t.utx", "s.uax", "mu.umx"])
    ms = ca.resource_mounts([str(d)])
    assert ca.paths_ini_lines(ms) == [
        "Paths=/stubs/*.u", "Paths=/opt/UED22/*.u",
        "Paths=/resources/r000/*.utx", "Paths=/resources/r000/*.uax", "Paths=/resources/r000/*.umx",
    ]


def test_paths_ini_lines_with_no_content_still_covers_stubs_and_ued22():
    assert ca.paths_ini_lines([]) == ["Paths=/stubs/*.u", "Paths=/opt/UED22/*.u"]


def test_paths_ini_lines_code_dir_mount_emits_dot_u_after_the_v69_roots(tmp_path):
    # The stub-build container mounts the full composed set, INCLUDING v68 code dirs. A code dir
    # emits `*.u` — harmless, because /stubs (v69) is first, so `UCC make` still binds the v69 stub;
    # the v68 source itself is read by batchexport via its explicit /resources path.
    sysd = tmp_path / "System"; sysd.mkdir(); _mkfiles(sysd, ["DeusEx.u", "DeusExItems.U"])
    tex = tmp_path / "Textures"; tex.mkdir(); _mkfiles(tex, ["a.utx"])
    ms = ca.resource_mounts([str(tex), str(sysd)])
    assert ca.paths_ini_lines(ms) == [
        "Paths=/stubs/*.u",              # v69 stubs FIRST — win over any v68 code mount below
        "Paths=/opt/UED22/*.u",
        "Paths=/resources/r000/*.utx",   # content dir
        "Paths=/resources/r001/*.u",     # v68 code dir (case-insensitive), after the v69 roots
    ]


def test_docker_mount_args_flattens_read_only():
    ms = ca.resource_mounts(["/host/Textures", "/host/Maps"])
    assert ca.docker_mount_args(ms) == [
        "-v", "/host/Textures:/resources/r000:ro",
        "-v", "/host/Maps:/resources/r001:ro",
    ]


def test_docker_mount_args_empty():
    assert ca.docker_mount_args([]) == []


# --- remap ---

def test_remap_host_file_under_a_mount(tmp_path):
    tex = tmp_path / "Textures"; tex.mkdir(); _mkfiles(tex, ["LUM_CoreTex.utx"])
    ms = ca.resource_mounts([str(tex)])
    got = ca.remap(str(tex / "LUM_CoreTex.utx"), ms)
    assert got == "/resources/r000/LUM_CoreTex.utx"


def test_remap_the_mount_root_itself(tmp_path):
    tex = tmp_path / "Textures"; tex.mkdir()
    ms = ca.resource_mounts([str(tex)])
    assert ca.remap(str(tex), ms) == "/resources/r000"


def test_remap_returns_none_when_not_under_any_mount(tmp_path):
    tex = tmp_path / "Textures"; tex.mkdir()
    ms = ca.resource_mounts([str(tex)])
    assert ca.remap("/somewhere/else/x.utx", ms) is None
    assert ca.remap("x.utx", []) is None


def test_remap_longest_match_wins_for_nested_mounts(tmp_path):
    parent = tmp_path / "content"; parent.mkdir()
    child = parent / "Textures"; child.mkdir()
    _mkfiles(child, ["a.utx"])
    # both parent and child are mounted; a file under child must map to the CHILD mount
    ms = [Mount(host_dir=str(parent), container_dir="/resources/r000"),
          Mount(host_dir=str(child), container_dir="/resources/r001")]
    assert ca.remap(str(child / "a.utx"), ms) == "/resources/r001/a.utx"
