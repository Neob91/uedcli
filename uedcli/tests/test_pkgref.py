"""`pkgref.build_texture_group_index` — the `.utx`/`.u` group scan `Resolver.object_ref` needs to
re-attach a texture's group chain.

Offline: synthetic packages written directly with `pkg_write` primitives (no real game assets).
Real content stores a texture's group as an EXPORT in the SAME file (`outer` a positive export
ref, e.g. `DeusExItems.u`'s `BlackMaskTex` -> Outer export `Skins`) — verified by parsing the real
`DeusExItems.u` shipped with the game. `pkgfixture.texture_package(group=...)` instead encodes the
group as an IMPORT, a shape `build_texture_group_index`'s outer-chain walk does not follow (by
design — an import can't be walked further), so it is unusable for these tests; the packages below
are hand-built to match the real, export-based shape.
"""
from __future__ import annotations

from uedcli.native import pkgref
from uedcli.native.pkg_write import NameTable, ImportRec, ExportRec, build_package

FIXTURE_GUID = bytes(range(16))


def _texture_package(*, texname: str, group: str | None = None) -> bytes:
    """One `Engine.Texture` export named `texname`, optionally nested under a group export named
    `group` (outer = that export's ref) -- the real `.u`/`.utx` shape."""
    names = NameTable()
    for n in ("Core", "Package", "Class", "Engine", "Texture", texname,
              *([group] if group else [])):
        names.index(n)
    imports = [ImportRec(names.index("Core"), names.index("Package"), 0, names.index("Engine"))]
    engine_ref = -len(imports)
    imports.append(ImportRec(names.index("Core"), names.index("Class"), engine_ref,
                             names.index("Texture")))
    tex_class = -len(imports)

    exports = []
    outer = 0
    if group:
        exports.append(ExportRec(0, 0, 0, names.index(group), 0, b""))
        outer = len(exports)
    exports.append(ExportRec(tex_class, 0, outer, names.index(texname), 0, b""))

    return build_package(version=69, licensee=0, package_flags=0, names=names,
                         imports=imports, exports=exports, guid=FIXTURE_GUID)


def _write(tmp_path, filename: str, data: bytes) -> None:
    (tmp_path / filename).write_bytes(data)


def test_it_finds_a_texture_group_inside_a_u_code_package(tmp_path):
    """UE1 stores some textures inside CODE packages (`DeusExItems.u`'s `BlackMaskTex`, group
    `Skins`) — the index must cover those, not just `.utx`."""
    _write(tmp_path, "DeusExItems.u",
           _texture_package(texname="BlackMaskTex", group="Skins"))
    index = pkgref.build_texture_group_index([tmp_path])
    assert index[("deusexitems", "blackmasktex")] == "Skins"


def test_a_utx_group_wins_over_a_same_stem_name_in_a_u_file(tmp_path):
    """The `.u` scan is purely additive: a name already resolved from `.utx` is never displaced,
    so widening the scan cannot change any EXISTING correct resolution."""
    _write(tmp_path, "Foo.utx", _texture_package(texname="Bar", group="FromUtx"))
    _write(tmp_path, "Foo.u", _texture_package(texname="Bar", group="FromU"))
    index = pkgref.build_texture_group_index([tmp_path])
    assert index[("foo", "bar")] == "FromUtx"


def test_a_bad_u_file_never_breaks_the_build(tmp_path):
    """Mirrors the pre-existing `.utx` guarantee: a corrupt/locked `.u` is skipped, not fatal."""
    _write(tmp_path, "Bad.u", b"not a package")
    _write(tmp_path, "Good.utx", _texture_package(texname="Tex", group="G"))
    index = pkgref.build_texture_group_index([tmp_path])
    assert index == {("good", "tex"): "G"}


def test_a_non_texture_export_in_a_u_file_is_ignored(tmp_path):
    """`kinds` filters `.u` exports exactly as it already filters `.utx` ones — the group export
    itself (class unset, not `Texture`) never leaks into the index as an object in its own right."""
    _write(tmp_path, "P.u", _texture_package(texname="Tex", group="G"))
    index = pkgref.build_texture_group_index([tmp_path])
    assert list(index) == [("p", "tex")]


def test_a_top_level_u_texture_gets_the_empty_group(tmp_path):
    """No group export (`outer=0`) -> `""`, same as a top-level `.utx` export."""
    _write(tmp_path, "Plain.u", _texture_package(texname="Tex"))
    index = pkgref.build_texture_group_index([tmp_path])
    assert index[("plain", "tex")] == ""
