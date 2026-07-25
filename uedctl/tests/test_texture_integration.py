import os

import pytest

from uedctl import container_assets, texture, texture_catalog as tc
from uedctl.tests.conftest import install_content_dirs, install_root


@pytest.mark.integration
def test_sync_a_real_texture_package_writes_manifest_and_pngs(tmp_path):
    # A texture-bearing package resolved via the build container's crafted `[Core.System] Paths`.
    # The container is a per-command ephemeral build container that bind-mounts the CONTENT dirs at
    # `/resources/<n>` via the uniform `resource_mounts` scheme; skip if the gitignored install is
    # absent. (Discovery here uses `install_content_dirs` as an install pointer — the production
    # discovery path is `config.composed_search_files`, exercised by the offline dispatch tests.)
    from uedctl.stub import ephemeral_build_container
    install_tex = install_root() / "Textures"
    utx = sorted(install_tex.glob("*.utx")) if install_tex.is_dir() else []
    if not utx:
        pytest.skip("no Deus Ex install textures present (DeusExAssets/Textures/*.utx)")
    package = utx[0].stem
    file_path = str(utx[0])
    content_dirs = [str(d) for d in install_content_dirs()]
    mounts = container_assets.resource_mounts(content_dirs)
    with ephemeral_build_container(mounts=mounts,
                                   state_dir=tmp_path / ".uedctl") as container:
        m = tc.sync_package(package=package, package_file=file_path, container=container,
                            catalog_dir=tmp_path / "cat", images_root=tmp_path / "img", force=True,
                            batchexport=texture.batchexport_textures,
                            lock_dir=str(tmp_path / ".uedctl" / "locks"))
    assert m is not None and m.textures                            # a real .utx has textures
    some = next(iter(m.textures.values()))
    assert some.image_hash.startswith("sha256:")
    assert some.colors                                            # colors auto-derived
    assert (tmp_path / "img" / package).is_dir()                  # viewable PNGs written
