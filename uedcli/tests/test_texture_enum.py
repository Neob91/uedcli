"""Texture-catalog library core (asset-catalog TEXTURE arm T0/T0b/T1): the widened
`textures()` seam, the search-path enumerator, the FROZEN Layer-1 identity, and the Layer-2 facts.

Offline: synthetic `.utx` written by `pkgfixture` on a tmp search path, plus a REAL `ClassIndex`
over the committed `uned/UED22` corpus (it defines `Engine.Texture` and its `fire.*` descendants),
so `descends_from` has a real hierarchy to answer against.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

from uedcli import utexture
from uedcli.classindex import ClassIndex
from uedcli.tests import pkgfixture

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def _write(tmp_path, filename: str, data: bytes) -> str:
    p = tmp_path / filename
    p.write_bytes(data)
    return str(p)


# ── T0b: the widened seam ────────────────────────────────────────────────────────────────────────

def test_it_keeps_exact_texture_match_with_no_class_index(tmp_path, index):
    """`textures(pkg)` (no index) matches ONLY the exact `Texture` class — a `fire.FireTexture`
    export is invisible to it, so every existing caller and its tests are unchanged."""
    pkg = utexture.load_package(_write(
        tmp_path, "Fx.utx",
        pkgfixture.texture_package(name="Flame", mips=[(4, 4, b"")],
                                   class_package="fire", class_name="FireTexture")))
    assert utexture.textures(pkg) == []                       # exact match: subclass unseen
    assert utexture.textures(pkg, index) == [1]               # widened: the subclass export


def test_it_skips_a_none_fqcn_export_without_crashing(tmp_path, index):
    """A locally-defined class (`class_fqcn_of_export` → None) is not a texture and is skipped,
    never fed to `descends_from` (whose `None.casefold()` would crash)."""
    pkg = utexture.load_package(_write(tmp_path, "P.utx", pkgfixture.texture_package(name="T")))
    # export 0 is the Palette (an Engine class, not a texture); export 1 the Texture.
    assert utexture.textures(pkg, index) == [1]


def test_it_resolves_a_subclass_procedural_to_no_mip_data_only_when_widened(tmp_path, index):
    """A `fire.FireTexture` export with empty mips resolves to `no-mip-data` through the WIDENED
    resolver; the exact-match resolver never finds it (`unknown-texture`). This is the procedural
    name-key path the shipped seam kept closed (plan T0b)."""
    path = _write(tmp_path, "Fx.utx",
                  pkgfixture.texture_package(name="Flame", mips=[(4, 4, b"")], trailing=b"\x00\x00",
                                             class_package="fire", class_name="FireTexture"))
    exact = utexture.TextureResolver([path])
    assert exact.resolve("Fx.Flame").case == "unknown-texture"
    widened = utexture.TextureResolver([path], class_index=index)
    assert widened.resolve("Fx.Flame").case == "no-mip-data"


# ── same-package class fqcn (`Engine.DefaultTexture`'s shape) ──────────────────────────────────────

def _same_package_texture_pkg(*, stem: str | None) -> utexture.Package:
    """A minimal package: export 0 is the `Texture` class itself; export 1 is `DefaultTexture`, an
    INSTANCE of it classed by a same-package export ref (`cls=1`, not an import) — the real
    `Engine.DefaultTexture` shape: a `Texture` living directly in `Engine.u` alongside the `Texture`
    class itself."""
    names = ["Texture", "DefaultTexture", "None"]
    exports = [
        {"cls": 0, "sup": 0, "outer": 0, "nm": 0, "flags": 0, "ssize": 0, "soff": 0},
        {"cls": 1, "sup": 0, "outer": 0, "nm": 1, "flags": 0, "ssize": 0, "soff": 0},
    ]
    return utexture.Package(version=68, names=names, imports=[], exports=exports, buf=b"", stem=stem)


def test_class_fqcn_of_export_resolves_a_same_package_class():
    """The bug: a class defined IN this same package (not an IMPORT) must still resolve an FQCN,
    not just the cross-package import case."""
    pkg = _same_package_texture_pkg(stem="Engine")
    assert utexture.class_fqcn_of_export(pkg, 1) == "Engine.Texture"


def test_class_fqcn_of_export_same_package_class_needs_a_known_stem():
    """Without the package's own stem there is nothing to qualify a same-package class with —
    stays None (the known-cost case, not a crash or a guess)."""
    pkg = _same_package_texture_pkg(stem=None)
    assert utexture.class_fqcn_of_export(pkg, 1) is None


def test_textures_widened_match_sees_a_same_package_texture(index):
    """The reported bug end to end: `Engine.DefaultTexture` must register under the widened
    `Engine.Texture`-descendant match instead of being silently skipped."""
    pkg = _same_package_texture_pkg(stem="Engine")
    assert utexture.textures(pkg, index) == [1]


# ── T0: enumeration over the search path ───────────────────────────────────────────────────────────

def test_it_enumerates_texture_and_subclass_but_not_nontexture(tmp_path, index):
    """Both a plain `Texture` and a `fire.FireTexture` DESCENDANT enumerate; the Palette export
    (a non-texture Engine class) never does. Refs are sorted."""
    tex = _write(tmp_path, "Deco.utx", pkgfixture.texture_package(name="Wood"))
    fire = _write(tmp_path, "Fx.utx",
                  pkgfixture.texture_package(name="Flame", mips=[(4, 4, b"")],
                                             class_package="fire", class_name="FireTexture"))
    r = utexture.TextureResolver([tex, fire], class_index=index)
    got = r.texture_refs()
    assert [t.ref for t in got] == ["Deco.Wood", "Fx.Flame"]     # sorted; no Palette export
    assert all(t.group is None for t in got)


def test_it_reports_the_group_fact_and_a_two_part_ref(tmp_path, index):
    """A grouped texture keeps a 2-part ref but reports its Outer as the `group` fact
    (`direction/asset-catalog.md`: the group vanishes from the ref for the common case)."""
    path = _write(tmp_path, "CoreTexMetal.utx",
                  pkgfixture.texture_package(name="LadrBrwnMetal", group="Ladder"))
    r = utexture.TextureResolver([path], class_index=index)
    (t,) = r.texture_refs()
    assert t.ref == "CoreTexMetal.LadrBrwnMetal" and t.group == "Ladder"


def test_an_undecodable_texture_still_enumerates(tmp_path, index):
    """Enumeration reads only the header tables, so a texture whose pixels will not decode still
    lists — its identity is simply unavailable later."""
    path = _write(tmp_path, "Bad.utx",
                  pkgfixture.texture_package(name="Broken", palette_ref=999))    # dangling palette
    r = utexture.TextureResolver([path], class_index=index)
    assert [t.ref for t in r.texture_refs()] == ["Bad.Broken"]
    assert r.resolve("Bad.Broken").case == "missing-palette"


def test_no_class_index_enumerates_nothing(tmp_path):
    """Without a class index there is nothing to widen the match against, so the enumerator is a
    no-op (the seam a non-catalog resolver takes)."""
    path = _write(tmp_path, "P.utx", pkgfixture.texture_package(name="T"))
    assert utexture.TextureResolver([path]).texture_refs() == []


# ── ref assignment (the collision → 3-part rule) ───────────────────────────────────────────────────

def test_ref_assignment_uses_two_parts_until_an_intra_package_name_collision():
    refs = utexture.package_texture_refs(
        "Pkg", [("Wall", None), ("Wall", "GroupA"), ("Wall", "GroupB"), ("Floor", "Trim")])
    # `Wall` collides three ways → the two with a group get the 3-part form; the group-less one
    # stays 2-part; the unique `Floor` stays 2-part despite having a group.
    assert refs == ["Pkg.Wall", "Pkg.GroupA.Wall", "Pkg.GroupB.Wall", "Pkg.Floor"]


# ── T1: the FROZEN identity + Layer-2 facts ────────────────────────────────────────────────────────

def _decoded(w, h, rgb, mask) -> utexture.DecodedTexture:
    return utexture.DecodedTexture(ref="X.Y", width=w, height=h, rgb=rgb, mask=mask,
                                   layout="linear1", layout_source="data", format_code=0,
                                   array="mips")


def test_identity_is_the_frozen_sha256_over_w_h_rgb_golden():
    """The identity function is FROZEN and pinned by a committed golden — it is every shard's
    filename, so a decode change that shifts it silently re-keys the store. A fixed 2x1 RGB image
    hashes to exactly this hex."""
    rgb = bytes([10, 20, 30, 200, 100, 50])                   # two pixels, chosen non-default
    ident = utexture.texture_identity(_decoded(2, 1, rgb, b"\x01\x01"))
    # The GOLDEN — a hardcoded hex, not a recomputation. `sha256(uint32_le(2) ‖ uint32_le(1) ‖ rgb)`.
    assert ident == "2eb4f6c49bea0c52c9a1b62f5debee05571345e78ddb92cb3cdbfa21cc7c92f2"


def test_a_mask_change_does_not_change_identity():
    rgb = bytes([7, 7, 7, 9, 9, 9])
    a = utexture.texture_identity(_decoded(2, 1, rgb, b"\x01\x01"))
    b = utexture.texture_identity(_decoded(2, 1, rgb, b"\x00\x01"))   # a masked twin, same pixels
    assert a == b


def test_identical_pixels_in_two_named_packages_share_one_identity(tmp_path, index):
    """Two differently-named refs with identical pixels resolve to one identity (cross-package
    dedup)."""
    mips = pkgfixture.linear_chain(4, 4)
    pal = [(i, (i * 3) & 255, (i * 5) & 255, 255) for i in range(256)]
    a = _write(tmp_path, "PkgA.utx", pkgfixture.texture_package(name="Alpha", mips=mips, palette=pal))
    b = _write(tmp_path, "PkgB.utx", pkgfixture.texture_package(name="Beta", mips=mips, palette=pal))
    r = utexture.TextureResolver([a, b], class_index=index)
    ida = utexture.texture_identity(r.resolve("PkgA.Alpha"))
    idb = utexture.texture_identity(r.resolve("PkgB.Beta"))
    assert ida == idb


def test_procedural_identity_is_the_casefolded_package_name():
    assert utexture.procedural_identity("Fire", "Flame") == "fire.flame"


def test_group_fact_is_the_outer_or_null(tmp_path, index):
    grouped = _write(tmp_path, "G.utx", pkgfixture.texture_package(name="Wood", group="Skins"))
    plain = _write(tmp_path, "P.utx", pkgfixture.texture_package(name="Wood"))
    pg = utexture.load_package(grouped)
    pp = utexture.load_package(plain)
    assert utexture.group_of_export(pg, 1) == "Skins"
    assert utexture.group_of_export(pp, 1) is None


def test_masked_fact_is_tag_else_default_else_null(tmp_path, index):
    """`b_masked` is the export's own tag when present. On a lone `.utx` with no code package to
    resolve the class default it is None (not False) — the 'read any texture from any engine' case."""
    masked = _write(tmp_path, "M.utx",
                    pkgfixture.texture_package(name="Grille", bmasked=True))
    r = utexture.TextureResolver([masked])                    # no code package on the path
    assert r.resolve("M.Grille").b_masked is True
    unmarked = _write(tmp_path, "U.utx", pkgfixture.texture_package(name="Wall"))
    assert utexture.TextureResolver([unmarked]).resolve("U.Wall").b_masked is None
