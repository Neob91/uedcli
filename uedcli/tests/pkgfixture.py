"""Build a synthetic UE1 `.utx` in memory, from scratch, for texture tests.

Test-only — nothing here ships. Promoted from the committed spike prototype
`dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py` (which stays put as
evidence, with its self-verification `main()`); this copy drops the `sys.path` shim and that
`main()`, and keeps `texture_package()`'s keyword surface unchanged.

Why it exists: the texture-decode tests need packages with a *chosen* mip chain — a `CompMips`
array, a zero-length mip, a dangling `Palette` ref, a hostile mip count, a stored `Format` byte
that exists nowhere in real content. None can be lifted from real content (which is gitignored
anyway), and `uedcli/native/pkg_write.py` already has a from-scratch container writer
(`build_package`), so the whole fixture is ~150 lines of body encoding on top of it.

The shapes it builds:

  * `texture_package(...)`               a v69 `.utx`: one `Engine.Palette` export +
                                         one `Engine.Texture` export.
  * `comp_mips=...`                      the two-array `bHasComp` / `CompFormat` /
                                         `CompMips` body (the live-bug shape).
  * `comp_mips=None`                     `bHasComp` absent => ZERO bytes after `Mips`,
                                         body still EOF-clean.
  * `mips=[(w, h, b"")]` + `trailing=`   the `FireTexture` shape: empty pixel data AND
                                         trailing bytes past the mip array.
  * `byte_props=` / `int_props=` /       the rest of a PROCEDURAL body, which carries its whole
    `object_props=` / `struct_array=`    appearance in properties: the `FX_*` bytes,
    / `source_mips=`                     `USize`/`VSize`, a `SourceTexture` ref and the export
                                         it points at, a `Drops[]` static array.
  * `palette_ref=<n>`                    a `Palette` object ref past the export table =>
                                         the missing-palette shape.
  * `palette_count=<n>`                  a Palette body whose declared entry count disagrees
                                         with its bytes => the won't-decode shape.
  * `declared_mip_count=`                a lying `Mips` count => the hostile-input shape.
  * `bmasked=True/False`                 a stored `bMasked` bool. The `False` arm is the one
                                         REAL CONTENT CANNOT SUPPLY: UE1 omits any property
                                         equal to its class default, so a stored `bMasked=False`
                                         occurs nowhere in the wild and only a synthesized
                                         package has one. (`True` is common — 317 of the 1,998
                                         tracked `uned/UED22` textures carry it.)

THE TRAP, learned the hard way: a property tag's **size code must match the encoded value's
real length**. An `ObjectProperty` whose ref encodes to a single compact-index byte needs
size code 0 (=1 byte), not 2 (=4 bytes), or every subsequent property mis-parses and the
`None` terminator is never found. `_prop_object()` derives the size code from the encoded
bytes for exactly this reason.

The one piece of genuine back-patching is each `FMipmap`'s `WidthOffset`: a TLazyArray skip
offset that is the **absolute file offset just past that mip's `Data`**. It is computable
before the bodies exist because `build_package` lays export bodies contiguously starting at
`dataoff = header_len + len(encoded name table)` — so every name must be interned BEFORE the
name table is encoded.
"""
from __future__ import annotations

import struct

from uedcli.native.codec import write_ci
from uedcli.native.pkg_write import NameTable, ImportRec, ExportRec, build_package

# UE1 property type nibbles (see `utexture._read_props`).
PT_BYTE, PT_INT, PT_BOOL, PT_OBJECT, PT_STRUCT = 1, 2, 3, 5, 10

# RF_Public | RF_LoadForClient | RF_LoadForServer | RF_LoadForEdit — the object flags a
# real texture export carries. Nothing in the decode path reads them; they are set so the
# fixture matches real content.
RF_TEXTURE = 0x00000004 | 0x00010000 | 0x00020000 | 0x00040000

# `build_package` defaults its package GUID to `os.urandom(16)`, which would make every
# fixture byte-different on every call. A test fixture must be deterministic — otherwise a
# committed one can never be checked against the script that built it. Nothing in the decode
# path reads the GUID.
FIXTURE_GUID = bytes(range(16))


# --- tagged-property encoding ------------------------------------------------

def _size_code(n: int) -> int:
    """The FPropertyTag size code that encodes exactly `n` value bytes."""
    return {1: 0, 2: 1, 4: 2, 12: 3, 16: 4}.get(n, 5)


def _prop_head(names: NameTable, name: str, ptype: int, nbytes: int,
               extra_bits: int = 0) -> bytes:
    code = _size_code(nbytes)
    head = write_ci(names.index(name)) + bytes([ptype | (code << 4) | extra_bits])
    if code == 5:                                   # size code 5 => a following u8 length
        head += bytes([nbytes])
    return head


def _prop_byte(names: NameTable, name: str, value: int) -> bytes:
    """A ByteProperty (`Format`, `CompFormat`)."""
    return _prop_head(names, name, PT_BYTE, 1) + bytes([value & 0xFF])


def _prop_bool(names: NameTable, name: str, value: bool) -> bytes:
    """A BoolProperty (`bHasComp`, `bMasked`). Its VALUE is bit 7 of the info byte; it
    carries no value bytes at all — the size code is still written and still ignored."""
    return _prop_head(names, name, PT_BOOL, 1, extra_bits=0x80 if value else 0)


def _prop_int(names: NameTable, name: str, value: int) -> bytes:
    """An IntProperty (`USize`, `VSize`, `NumSparks`, `NumDrops`)."""
    return _prop_head(names, name, PT_INT, 4) + struct.pack("<i", value)


def _prop_object(names: NameTable, name: str, ref: int) -> bytes:
    """An ObjectProperty (`Palette`). Its value is a compact index, so the size code must
    be derived from the ENCODED length — this is the trap named in the module docstring."""
    enc = write_ci(ref)
    return _prop_head(names, name, PT_OBJECT, len(enc)) + enc


def _packed_array_index(index: int) -> bytes:
    """A static-array element index in UE1's packed form: one byte below 0x80, else two with the
    top bits `10`, else four with `11`."""
    if index < 0x80:
        return bytes([index])
    if index < (1 << 14):
        return bytes([0x80 | (index >> 8), index & 0xFF])
    return bytes([0xC0 | (index >> 24)]) + index.to_bytes(3, "big")


def _prop_struct_element(names: NameTable, name: str, struct_name: str,
                         raw: bytes, index: int) -> bytes:
    """One element of a STATIC ARRAY of StructProperty (a `WaterTexture`'s `Drops[]`).

    Written out longhand rather than through `_prop_head`, because a StructProperty tag has an
    extra field nothing else does: `name, info byte, STRUCT NAME, size, [array index], value`.
    Element 0 serializes as a plain non-array tag (bit 7 clear, no index byte) — exactly what
    real content does — so only elements past it carry an index.

    The index itself is UE1's packed form: one byte below 0x80, else two with the top bits `10`,
    else four with `11`. Real content reaches the two-byte form (`Effects.drtywater_a` stores
    `Drops` indices up to 178), so the fixture has to be able to write it."""
    assert 0 <= index < (1 << 30), f"array index {index} is outside the packed form"
    code = _size_code(len(raw))
    out = write_ci(names.index(name))
    out += bytes([PT_STRUCT | (code << 4) | (0x80 if index else 0)])
    out += write_ci(names.index(struct_name))
    if code == 5:
        out += bytes([len(raw)])
    if index:
        out += _packed_array_index(index)
    return out + raw


def _props_end(names: NameTable) -> bytes:
    return write_ci(names.index("None"))


# --- mip arrays --------------------------------------------------------------

def _bits(n: int) -> int:
    return max(0, n.bit_length() - 1)


def _mip_array(mips, base_off: int, *, version: int, declared_count: int | None = None):
    """Encode a `TArray<FMipmap>` whose first byte sits at absolute file offset `base_off`.

    `mips` is a list of `(width, height, data_bytes)`. Each FMipmap is
    `[u32 WidthOffset if version >= 63] ci(DataCount) Data u32 USize u32 VSize u8 UBits
    u8 VBits`, and `WidthOffset` is the ABSOLUTE file offset just past `Data`.

    `declared_count` overrides the count written to disk (to build a lying header).
    """
    count = len(mips) if declared_count is None else declared_count
    out = bytearray(write_ci(count))
    for (w, h, data) in mips:
        head_len = 4 if version >= 63 else 0
        dcount = write_ci(len(data))
        # absolute offset just past Data, for THIS mip
        past = base_off + len(out) + head_len + len(dcount) + len(data)
        if version >= 63:
            out += struct.pack("<I", past)
        out += dcount + data
        out += struct.pack("<II", w, h)
        out += bytes([_bits(w), _bits(h)])
    return bytes(out)


# --- the package -------------------------------------------------------------

def texture_package(*, name: str = "Fixture", mips=None, palette=None,
                    fmt: int | None = None, comp_mips=None, comp_format: int = 3,
                    palette_ref: int | None = None, trailing: bytes = b"",
                    declared_mip_count: int | None = None, bmasked: bool | None = None,
                    class_package: str = "Engine", class_name: str = "Texture",
                    group: str | None = None, version: int = 69, licensee: int = 0,
                    byte_props: dict[str, int] | None = None,
                    int_props: dict[str, int] | None = None,
                    object_props: dict[str, int] | None = None,
                    struct_array: tuple[str, str, list[bytes]] | None = None,
                    source_mips=None, palette_count: int | None = None) -> bytes:
    """Build a whole synthetic `.utx` carrying one Palette export + one Texture export.

    `mips` / `comp_mips` are `[(w, h, data), ...]`; `comp_mips=None` means no `bHasComp`
    property at all (so ZERO bytes follow `Mips`). `fmt=None` omits the `Format` property
    entirely (the overwhelmingly common real case — it then defaults to 0 = P8).
    `bmasked=None` likewise omits `bMasked`; `True`/`False` writes the tag. `palette_ref`
    overrides the emitted `Palette` object ref (pass an out-of-range export ref
    to reproduce the missing-palette shape). `trailing` is appended after the mip array(s)
    (the `FireTexture` `TArray<FSpark>` shape).

    `class_package`/`class_name` set the texture export's class import — the default
    `Engine.Texture`, or e.g. `fire`/`FireTexture` for a DESCENDANT the catalog's widened
    enumerator must still see. `group` gives the texture an Outer named that (the Layer-2
    group fact); None leaves it a group-less top-level export.

    `palette_count` overrides the Palette body's declared entry count, so the palette itself will
    not decode. The rest build the PROCEDURAL shapes (`FireTexture` and friends, whose bodies
    carry their whole appearance in properties because their mips are empty):

      * `byte_props` / `int_props` / `object_props`   extra tagged properties of that type —
        `{"RenderHeat": 200}`, `{"USize": 16, "VSize": 16}`, `{"SourceTexture": 3}`.
      * `struct_array=(name, struct, [raw, ...])`     a STATIC ARRAY of StructProperty, one tag
        per element (`("Drops", "ADrop", [...])`).
      * `source_mips=[(w, h, data), ...]`             appends a THIRD export: an ordinary
        `Engine.Texture` carrying that mip chain and sharing the palette, so a
        `WetTexture`/`IceTexture` fixture has something real to point `SourceTexture` at. It is
        **object ref 3** (export index 2).
    """
    if mips is None:
        mips = [(2, 2, bytes([0, 1, 2, 3]))]
    if palette is None:
        palette = [(i, i, i, 255) for i in range(256)]

    names = NameTable()
    # Every name must exist BEFORE the table is encoded, because the mip skip offsets are
    # absolute and `dataoff` depends on the encoded table's length.
    for n in ("Core", "Package", "Class", "Engine", "Texture", "Palette", "None",
              "Format", "bHasComp", "CompFormat", "bMasked", class_package, class_name,
              name, name + "Pal", *([group] if group is not None else []),
              *(byte_props or {}), *(int_props or {}), *(object_props or {}),
              *(struct_array[:2] if struct_array else ()),
              *([name + "Src"] if source_mips is not None else [])):
        names.index(n)

    imports = [ImportRec(names.index("Core"), names.index("Package"), 0, names.index("Engine"))]
    engine_ref = -1                                  # import 0 (0-based) => ref -1
    if class_package.casefold() == "engine":         # default: the class lives in Engine
        cls_pkg_ref = engine_ref
    else:                                            # a subclass package (e.g. fire.FireTexture)
        imports.append(ImportRec(names.index("Core"), names.index("Package"), 0,
                                 names.index(class_package)))
        cls_pkg_ref = -len(imports)
    imports.append(ImportRec(names.index("Core"), names.index("Class"), cls_pkg_ref,
                             names.index(class_name)))
    tex_class = -len(imports)
    imports.append(ImportRec(names.index("Core"), names.index("Class"), engine_ref,
                             names.index("Palette")))
    pal_class = -len(imports)
    src_class = tex_class                             # the appended source is a plain Texture
    if source_mips is not None and class_name != "Texture":
        imports.append(ImportRec(names.index("Core"), names.index("Class"), engine_ref,
                                 names.index("Texture")))
        src_class = -len(imports)
    tex_outer = 0
    if group is not None:                            # the Outer object supplies the group fact
        imports.append(ImportRec(names.index("Core"), names.index("Package"), 0,
                                 names.index(group)))
        tex_outer = -len(imports)

    # export 0 => object ref 1 (the palette), export 1 => ref 2 (the texture)
    pal_body = bytearray(_props_end(names))
    pal_body += write_ci(len(palette) if palette_count is None else palette_count)
    for (r, g, b, a) in palette:
        pal_body += bytes([r, g, b, a])

    header_len = 36 + (16 + 4 + 8 if version >= 68 else 8)
    dataoff = header_len + len(names.encode())
    tex_off = dataoff + len(pal_body)                # the texture body starts here

    tex_props = bytearray()
    if fmt is not None:
        tex_props += _prop_byte(names, "Format", fmt)
    if bmasked is not None:
        tex_props += _prop_bool(names, "bMasked", bmasked)
    tex_props += _prop_object(names, "Palette", 1 if palette_ref is None else palette_ref)
    if comp_mips is not None:
        tex_props += _prop_bool(names, "bHasComp", True)
        tex_props += _prop_byte(names, "CompFormat", comp_format)
    for pname, pval in (byte_props or {}).items():
        tex_props += _prop_byte(names, pname, pval)
    for pname, pval in (int_props or {}).items():
        tex_props += _prop_int(names, pname, pval)
    for pname, pval in (object_props or {}).items():
        tex_props += _prop_object(names, pname, pval)
    if struct_array is not None:
        aname, sname, raws = struct_array
        for k, raw in enumerate(raws):
            tex_props += _prop_struct_element(names, aname, sname, raw, k)
    tex_props += _props_end(names)

    tex_body = bytearray(tex_props)
    tex_body += _mip_array(mips, tex_off + len(tex_body), version=version,
                           declared_count=declared_mip_count)
    if comp_mips is not None:
        tex_body += _mip_array(comp_mips, tex_off + len(tex_body), version=version)
    tex_body += trailing

    exports = [
        ExportRec(pal_class, 0, 0, names.index(name + "Pal"), RF_TEXTURE, bytes(pal_body)),
        ExportRec(tex_class, 0, tex_outer, names.index(name), RF_TEXTURE, bytes(tex_body)),
    ]
    if source_mips is not None:
        src_off = tex_off + len(tex_body)
        src_body = bytearray(_prop_object(names, "Palette", 1) + _props_end(names))
        src_body += _mip_array(source_mips, src_off + len(src_body), version=version)
        exports.append(ExportRec(src_class, 0, 0, names.index(name + "Src"),
                                 RF_TEXTURE, bytes(src_body)))
    return build_package(version=version, licensee=licensee, package_flags=0,
                         names=names, imports=imports, exports=exports, guid=FIXTURE_GUID)


# --- convenience chains used by several test modules --------------------------

def linear_chain(w: int, h: int, bpp: int = 1) -> list[tuple[int, int, bytes]]:
    """A full LINEAR mip pyramid `w×h → 1×1`, each level `w·h·bpp` deterministic bytes.

    `bpp=1` is P8, the ordinary UE1 texture. A linear chain keeps scaling all the way down —
    that is what distinguishes it from a block chain, which floors at one block."""
    out = []
    while True:
        out.append((w, h, bytes((x * 7) & 0xFF for x in range(w * h * bpp))))
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return out


def bc_chain(w: int, h: int, block_bytes: int = 8) -> list[tuple[int, int, bytes]]:
    """A full block-compressed mip pyramid `w×h → 1×1`. Each level is
    `ceil(w/4)·ceil(h/4)·block_bytes` bytes, so it FLOORS at one block — the shape that
    separates a block layout from a linear one. `block_bytes=8` is BC1, `16` is BC2/BC3."""
    out, i = [], 0
    while True:
        n = ((w + 3) // 4) * ((h + 3) // 4) * block_bytes
        out.append((w, h, bytes((i + x) & 0xFF for x in range(n))))
        i += 1
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return out
