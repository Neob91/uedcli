"""Offline tests for `uedcli.utexture` — the promoted native texture decoder + the
`Package[.Group].Name` ref resolver.

The pixel expectations are FROZEN sha256 digests of the decoded RGB buffers, banked from
the spike-validated decoder (spike `2026-06-27-decontainerize-uedcli/01-native-texture-
decode.md` proved the decode byte-identical to `UCC batchexport` across the whole Deus Ex
corpus; these fixtures pin that behavior as a regression). Two committed fixture packages
cover BOTH FMipmap layout branches:
  - `LUM_InfoPortraits.utx` — file-version 69 (>= 63: mips carry the lazy-array skip
    offset), one ungrouped 64×64 texture.
  - `CoreTexWater.utx` — file-version 61 (< 63: NO skip offset), two textures in group
    `water` (also exercises group-qualified refs).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from uedcli.utexture import (TextureResolver, decode_palette, decode_texture,
                             export_index_of_ref, load_package, mip0_to_rgb, textures)

FIXTURES = Path(__file__).parent / "fixtures"
PORTRAITS = str(FIXTURES / "LUM_InfoPortraits.utx")
WATER = str(FIXTURES / "CoreTexWater.utx")


def _decode_named(path: str, name: str):
    pkg = load_package(path)
    for i in textures(pkg):
        t = decode_texture(pkg, i)
        if t.name == name:
            pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
            return t, mip0_to_rgb(t.mips[0], pal)
    raise AssertionError(f"texture {name} not in {path}")


def test_decode_v69_pixel_exact():
    """v69 fixture (mips WITH skip-offset): frozen size + RGB digest + probe pixels."""
    t, rgb = _decode_named(PORTRAITS, "ArthurCallaway")
    assert (t.mips[0].width, t.mips[0].height) == (64, 64)
    assert len(rgb) == 64 * 64 * 3
    assert hashlib.sha256(rgb).hexdigest() == (
        "6d42e496e6636b838775b6ee9373e7357f1ebd84057baf8b0eae856c1f0a8e16")


def test_decode_v61_pixel_exact():
    """v61 fixture (mips WITHOUT skip-offset — the WidthOffset-era layout branch)."""
    t, rgb = _decode_named(WATER, "dirtywater")
    assert (t.mips[0].width, t.mips[0].height) == (256, 256)
    assert rgb[:3] == bytes.fromhex("2f2a27")            # probe: first pixel
    assert hashlib.sha256(rgb).hexdigest() == (
        "10a7519cd5fd4f7fdca54771defdd364eac01d758cdd268701fcc271bac83a42")


def test_decode_all_mips_reach_eof():
    """Every texture in both fixtures decodes to EOF (the layout self-check raises else)."""
    for path in (PORTRAITS, WATER):
        pkg = load_package(path)
        assert textures(pkg), path
        for i in textures(pkg):
            t = decode_texture(pkg, i)
            assert t.mips, t.name


def test_load_package_rejects_non_package(tmp_path):
    bad = tmp_path / "NotAPackage.utx"
    bad.write_bytes(b"\x00" * 64)
    with pytest.raises(ValueError, match="bad magic"):
        load_package(str(bad))


# --- TextureResolver -----------------------------------------------------------


def _resolver():
    # Accepts either plain paths or (path, provenance) tuples — exercise both forms.
    return TextureResolver([(PORTRAITS, "project"), WATER])


def test_resolve_two_part_hit():
    got = _resolver().resolve("LUM_InfoPortraits.ArthurCallaway")
    assert got is not None
    w, h, rgb = got
    assert (w, h) == (64, 64) and len(rgb) == 64 * 64 * 3


def test_resolve_group_qualified_hit():
    got = _resolver().resolve("CoreTexWater.water.dirtywater")
    assert got is not None
    assert (got[0], got[1]) == (256, 256)


def test_resolve_group_mismatch_is_miss():
    assert _resolver().resolve("CoreTexWater.wood.dirtywater") is None


def test_resolve_bare_ref_is_miss():
    """A bare (unqualified) ref never resolves — dotted qualification is required,
    consistent with assemble._patch_surf_refs (cross-package stem scan is ambiguous)."""
    assert _resolver().resolve("dirtywater") is None


def test_resolve_unknown_package_and_texture_are_misses():
    r = _resolver()
    assert r.resolve("NoSuchPackage.foo") is None
    assert r.resolve("CoreTexWater.nosuchtexture") is None


def test_resolve_case_insensitive():
    assert _resolver().resolve("coretexwater.WATER.DirtyWater") is not None


def test_resolve_caches_per_instance():
    r = _resolver()
    first = r.resolve("CoreTexWater.dirtywater")
    assert r.resolve("CoreTexWater.dirtywater") is first    # cached object, not re-decoded


def test_resolve_project_shadows_base(tmp_path):
    """First entry per stem wins (the composed list is stem-deduped project-first; the
    resolver must keep that order even when handed duplicate stems)."""
    r = TextureResolver([PORTRAITS, str(tmp_path / "LUM_InfoPortraits.utx")])
    assert r.resolve("LUM_InfoPortraits.ArthurCallaway") is not None


def test_resolve_corrupt_package_is_miss(tmp_path):
    bad = tmp_path / "Corrupt.utx"
    bad.write_bytes(b"\x12\x34" * 40)
    r = TextureResolver([str(bad)])
    assert r.resolve("Corrupt.anything") is None
