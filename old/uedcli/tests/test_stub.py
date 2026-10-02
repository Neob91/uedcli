import textwrap
from pathlib import Path

import pytest

from uedcli.stub import assemble_stub_source, inject_edit_package, inject_stub_cache_path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))


def test_assemble_munges_classes_moves_meshes_and_renames_pcx(tmp_path):
    # Arrange — a raw decompile (one All* class), a umodel per-mesh `.uc` + `.3d` pair, a
    # group-prefixed pcx.
    raw = tmp_path / "raw"
    _write(raw / "Classes" / "AllAmmo.uc", r"""
        class AllAmmo extends Ammo;

        #exec MESH IMPORT MESH=GEPAmmo ANIVFILE=Models\gep_ammo_a.3d DATAFILE=Models\gep_ammo_d.3d
        #exec MESHMAP SCALE MESHMAP=GEPAmmo X=1.0 Y=1.0 Z=1.0
        #exec TEXTURE IMPORT NAME=GEPAmmoTex1 FILE=Models\gep_ammo.PCX GROUP="Skins"

        defaultproperties
        {
        }
    """)
    _write(raw / "um" / "DeusExItems" / "VertMesh" / "GEPAmmo.uc",
           "class GEPAmmo extends Actor;\n#exec MESHMAP SCALE MESHMAP=GEPAmmo X=0.033 Y=0.033 Z=0.033\n")
    (raw / "um" / "DeusExItems" / "VertMesh" / "GEPAmmo_a.3d").write_bytes(b"A")
    (raw / "um" / "DeusExItems" / "VertMesh" / "GEPAmmo_d.3d").write_bytes(b"D")
    (raw / "Textures").mkdir()
    (raw / "Textures" / "Skins.GEPAmmoTex1.pcx").write_bytes(b"P")

    out = tmp_path / "DXIStub"

    # Act
    result = assemble_stub_source(
        classes_dir=raw / "Classes", umodel_dir=raw / "um", textures_dir=raw / "Textures",
        out_dir=out, package="DeusExItems",
    )

    # Assert — class munged (paths rekeyed, scale reconciled), mesh moved, pcx renamed bare.
    cls = (out / "Classes" / "AllAmmo.uc").read_text()
    assert r"ANIVFILE=Models\GEPAmmo_a.3d" in cls
    assert "MESHMAP=GEPAmmo X=0.033" in cls          # umodel scale won
    assert r"FILE=Textures\GEPAmmoTex1.pcx" in cls
    assert (out / "Models" / "GEPAmmo_a.3d").exists()
    assert (out / "Models" / "GEPAmmo_d.3d").exists()
    assert (out / "Textures" / "GEPAmmoTex1.pcx").exists()
    assert not (out / "Textures" / "Skins.GEPAmmoTex1.pcx").exists()
    assert result.source_dir == out


def test_inject_edit_package_inserts_after_the_last_editpackages_line():
    # Arrange — appending at EOF would land OUTSIDE the section and `make` would silently skip it
    # (learned live 2026-06-22).
    ini = "[Editor.EditorEngine]\nEditPackages=Core\nEditPackages=Engine\n\n[Other]\nFoo=1\n"

    # Act
    out = inject_edit_package(ini, "DXIStub").splitlines()

    # Assert — DXIStub sits right after the last EditPackages line, before the next section.
    assert out.index("EditPackages=DXIStub") == out.index("EditPackages=Engine") + 1
    assert out.index("EditPackages=DXIStub") < out.index("[Other]")


def test_inject_edit_package_is_idempotent():
    ini = "EditPackages=Core\nEditPackages=DXIStub\n"
    assert inject_edit_package(ini, "DXIStub") == ini


def test_ephemeral_build_container_wires_the_uniform_resource_mounts_and_crafted_paths_ini(
        tmp_path, monkeypatch):
    # ONE mount scheme: the caller passes `mounts` (resource_mounts over the FULL composed set —
    # content AND v68 code dirs), each bind-mounted at /resources/<n>, plus a crafted Paths ini.
    # No separate /install-system mount; no deleted static compose `/deusex`+`/content`.
    from unittest import mock
    from uedcli import container_assets
    import uedcli.stub as stub_mod

    root = tmp_path
    (root / "CLAUDE.md").write_text("x")
    (root / "Tools" / "uedcli").mkdir(parents=True)
    calls = {}

    def fake_run(cmd, **kw):
        if cmd[:2] == ["docker", "compose"] and "run" in cmd:
            calls["run"] = cmd
        return mock.Mock(returncode=0, stdout="wine-1.0")
    monkeypatch.setattr(stub_mod.subprocess, "run", fake_run)
    monkeypatch.setattr("uedcli.editor.engine_ini_mount",
                        lambda name, mounts, sd: (f"/host/{name}.ini",
                                              ["-v", f"/host/{name}.ini:/opt/UED22/unrealtournament.ini"]))
    monkeypatch.setattr("uedcli.editor._engine_ini_path", lambda name, sd: tmp_path / f"{name}.ini")

    # content dirs first, then the v68 code dir — the caller's composed order.
    mounts = container_assets.resource_mounts(["/host/Textures", "/host/Maps", "/host/DXSystem"])
    with stub_mod.ephemeral_build_container(mounts=mounts,
                                            state_dir=tmp_path / ".uedcli") as name:
        assert name.startswith("uned-stub-")
    flat = " ".join(calls["run"])
    assert "/host/Textures:/resources/r000:ro" in flat                    # content mount
    assert "/host/Maps:/resources/r001:ro" in flat                        # content mount
    assert "/host/DXSystem:/resources/r002:ro" in flat                    # v68 code SOURCE mount
    assert "/install-system" not in flat                                  # no separate code mount
    assert ":/opt/UED22/unrealtournament.ini" in flat                     # crafted Paths ini
    assert "/deusex" not in flat and "/content" not in flat               # static mounts are gone


@pytest.mark.integration
def test_build_stub_produces_a_loadable_v69_package(tmp_path):
    # The build container mounts the composed dir set uniformly at /resources/<n> (content + the v68
    # code dir) + a crafted Paths ini; build_stub reads the v68 `.u` SOURCE from the code dir's
    # remapped container path. Needs a COMPLETE v68 install (DeusExItems pulls `Effects` — absent in
    # a partial checkout). Validated live 2026-06-22 against DeusExItems.
    from uedcli import container_assets
    from uedcli.stub import build_stub, ephemeral_build_container
    from uedcli.dxpkg import parse_header
    from uedcli.tests.conftest import install_root

    assets = install_root()
    code_dir = str(assets / "System")
    content_dirs = [str(assets / "Textures"), str(assets / "Sounds"), str(assets / "Music")]
    mounts = container_assets.resource_mounts(content_dirs + [code_dir])
    source_u_dir = container_assets.remap(code_dir, mounts)      # the /resources/<n> for System/

    out = tmp_path / "DeusExItems.u"
    with ephemeral_build_container(mounts=mounts,
                                   state_dir=tmp_path / ".uedcli") as container:
        built = build_stub(container=container, name="DeusExItems", source_u_dir=source_u_dir,
                           out_u_path=out)

    assert parse_header(str(built)).version == 69
    assert b"WineBottle" in built.read_bytes()


def test_ensure_stub_returns_the_cache_without_rebuilding_on_a_hit(tmp_path, monkeypatch):
    # Arrange — a fake repo with a v68 input + committed substrate, and a primed cache.
    from unittest import mock
    import uedcli.stub as stub_mod

    # The substrate/toolchain ids are PACKAGE-RELATIVE now (tool_assets) — mock them so the test
    # neither hashes the real ~80 MB UED22 nor depends on its presence.
    root = tmp_path
    sysdir = root / "System"
    sysdir.mkdir(parents=True)
    (sysdir / "Foo.u").write_bytes(b"V68FOO")
    monkeypatch.setenv("UEDCLI_HOME", str(root / "home"))     # stub cache under tmp, not real ~/.uedcli
    monkeypatch.setattr(stub_mod, "_substrate_id", lambda: "subid")
    monkeypatch.setattr(stub_mod, "_toolchain_id", lambda: "toolid")

    # First call builds (mock build_stub to write a fake .u), second must hit the cache.
    from uedcli import container_assets
    search_dirs = [str(sysdir)]                                # the composed dir set (holds Foo.u)
    mounts = container_assets.resource_mounts(search_dirs)
    calls = []
    def fake_build(*, container, name, source_u_dir, out_u_path, **kw):
        calls.append((name, source_u_dir))
        Path(out_u_path).write_bytes(b"V69FOO")
        return Path(out_u_path)

    with mock.patch.object(stub_mod, "build_stub", side_effect=fake_build), \
         mock.patch("uedcli.stub_closure.direct_packages", return_value=set()):
        first = stub_mod.ensure_stub("Foo", container="c", search_dirs=search_dirs,
                                     mounts=mounts)
        second = stub_mod.ensure_stub("Foo", container="c", search_dirs=search_dirs,
                                      mounts=mounts)

    # Assert — built once (from the code dir's remapped /resources path), reused once.
    assert calls == [("Foo", "/resources/r000")]
    assert first == second
    assert first.read_bytes() == b"V69FOO"


def test_stub_missing_builds_only_v68_code_candidates(tmp_path):
    # Arrange — Foo.u is a v68 `.u` on the composed search path (candidate); Bar has no `.u` there
    # (not a candidate).
    import contextlib
    from unittest import mock
    import uedcli.stub as stub_mod

    root = tmp_path
    (root / "CLAUDE.md").write_text("x")
    sysdir = root / "System"
    sysdir.mkdir(parents=True)
    (sysdir / "Foo.u").write_bytes(b"v68")
    search_dirs = [str(sysdir)]

    built = []
    with mock.patch.object(stub_mod, "ensure_stub", side_effect=lambda name, **kw: built.append(name)), \
         mock.patch.object(stub_mod, "ephemeral_build_container",
                           return_value=contextlib.nullcontext("fakec")):
        resolved = stub_mod.stub_missing_packages(["Foo", "Bar"], search_dirs=search_dirs,
                                                  state_dir=root / ".uedcli")

    # Assert — only the `.u`-resolvable package is stubbed; `Bar` (no `.u`) is left missing.
    assert resolved == {"Foo"}
    assert built == ["Foo"]


def test_stub_missing_spins_no_container_when_there_are_no_candidates(tmp_path):
    from unittest import mock
    import uedcli.stub as stub_mod
    (tmp_path / "CLAUDE.md").write_text("x")

    with mock.patch.object(stub_mod, "ephemeral_build_container") as spin:
        resolved = stub_mod.stub_missing_packages(["OnlyContent"], search_dirs=[],
                                                  state_dir=tmp_path / ".uedcli")

    assert resolved == set()
    spin.assert_not_called()


def test_stub_errors_are_runtimeerrors_so_callers_catch_them_cleanly():
    # House rule: a build/closure failure must ride the resolution sites' existing RuntimeError
    # guard to a clean exit, not escape as a bare traceback.
    from uedcli.stub import StubBuildError
    from uedcli.stub_closure import StubClosureError
    assert issubclass(StubBuildError, RuntimeError)
    assert issubclass(StubClosureError, RuntimeError)


def test_ensure_stub_raises_a_clean_error_for_an_unknown_package(tmp_path):
    from uedcli import container_assets
    import uedcli.stub as stub_mod
    (tmp_path / "CLAUDE.md").write_text("x")
    sysdir = tmp_path / "System"
    sysdir.mkdir(parents=True)                            # a dir, but WITHOUT NoSuchPackage.u
    search_dirs = [str(sysdir)]
    mounts = container_assets.resource_mounts(search_dirs)

    # A name with no v68 `.u` on the composed search path must raise the typed (RuntimeError) error,
    # not FileNotFoundError.
    with pytest.raises(stub_mod.StubBuildError, match="NoSuchPackage"):
        stub_mod.ensure_stub("NoSuchPackage", container="c",
                             search_dirs=search_dirs, mounts=mounts)


def test_inject_stub_cache_path_adds_stubs_to_paths_idempotently():
    ini = "[Core.System]\nPaths=/opt/UED22/System/*.u\nPaths=/deusex/Textures/*.utx\n"
    out = inject_stub_cache_path(ini)
    assert "Paths=/stubs/*.u" in out
    assert inject_stub_cache_path(out) == out          # idempotent
    # no Paths section -> no-op
    assert inject_stub_cache_path("[Other]\nFoo=1\n") == "[Other]\nFoo=1\n"


def test_ephemeral_build_container_passes_stub_cache_env_for_the_compose_mount(
        tmp_path, monkeypatch):
    """The BUILD container shares the compose `/stubs` volume (`${UEDCLI_STUB_CACHE:-…}`), and
    /stubs is FIRST on its Paths so previously-built stubs shadow v68 deps during `UCC make` — so
    it must pass the resolved `config.stub_cache_root()` (honoring $UEDCLI_HOME) in the compose
    env exactly like `editor.ensure_editor`, never inherit-and-fall-back to the `${HOME}` default
    (review fix, 2026-07-18: the editor half landed first; this pins the build-container half)."""
    import os as _os
    from unittest import mock
    from uedcli import config
    import uedcli.stub as stub_mod

    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "custom-home"))
    seen = {}

    def fake_run(cmd, **kw):
        if cmd[:2] == ["docker", "compose"] and "run" in cmd:
            seen["env"] = kw.get("env")
        return mock.Mock(returncode=0, stdout="wine-1.0")
    monkeypatch.setattr(stub_mod.subprocess, "run", fake_run)
    monkeypatch.setattr("uedcli.editor.engine_ini_mount",
                        lambda name, mounts, sd: (f"/host/{name}.ini", []))
    monkeypatch.setattr("uedcli.editor._engine_ini_path", lambda name, sd: tmp_path / f"{name}.ini")

    with stub_mod.ephemeral_build_container(mounts=None, state_dir=tmp_path / ".uedcli"):
        pass
    assert seen["env"]["UEDCLI_STUB_CACHE"] == str(config.stub_cache_root())
    assert (tmp_path / "custom-home" / "cache" / "stubs").is_dir()   # mount source created
    assert seen["env"]["PATH"] == _os.environ["PATH"]                # superset of os.environ
