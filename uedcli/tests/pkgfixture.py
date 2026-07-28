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
  * `palette_ref=<n>`                    a `Palette` object ref past the export table =>
                                         the missing-palette shape.
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
PT_BYTE, PT_BOOL, PT_OBJECT = 1, 3, 5

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


def _prop_object(names: NameTable, name: str, ref: int) -> bytes:
    """An ObjectProperty (`Palette`). Its value is a compact index, so the size code must
    be derived from the ENCODED length — this is the trap named in the module docstring."""
    enc = write_ci(ref)
    return _prop_head(names, name, PT_OBJECT, len(enc)) + enc


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
                    version: int = 69, licensee: int = 0) -> bytes:
    """Build a whole synthetic `.utx` carrying one Palette export + one Texture export.

    `mips` / `comp_mips` are `[(w, h, data), ...]`; `comp_mips=None` means no `bHasComp`
    property at all (so ZERO bytes follow `Mips`). `fmt=None` omits the `Format` property
    entirely (the overwhelmingly common real case — it then defaults to 0 = P8).
    `bmasked=None` likewise omits `bMasked`; `True`/`False` writes the tag. `palette_ref`
    overrides the emitted `Palette` object ref (pass an out-of-range export ref
    to reproduce the missing-palette shape). `trailing` is appended after the mip array(s)
    (the `FireTexture` `TArray<FSpark>` shape).
    """
    if mips is None:
        mips = [(2, 2, bytes([0, 1, 2, 3]))]
    if palette is None:
        palette = [(i, i, i, 255) for i in range(256)]

    names = NameTable()
    # Every name must exist BEFORE the table is encoded, because the mip skip offsets are
    # absolute and `dataoff` depends on the encoded table's length.
    for n in ("Core", "Package", "Class", "Engine", "Texture", "Palette", "None",
              "Format", "bHasComp", "CompFormat", "bMasked", name, name + "Pal"):
        names.index(n)

    imports = [
        ImportRec(names.index("Core"), names.index("Package"), 0, names.index("Engine")),
        ImportRec(names.index("Core"), names.index("Class"), -1, names.index("Texture")),
        ImportRec(names.index("Core"), names.index("Class"), -1, names.index("Palette")),
    ]
    tex_class, pal_class = -2, -3                    # import i (0-based) => -(i + 1)

    # export 0 => object ref 1 (the palette), export 1 => ref 2 (the texture)
    pal_body = bytearray(_props_end(names))
    pal_body += write_ci(len(palette))
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
    tex_props += _props_end(names)

    tex_body = bytearray(tex_props)
    tex_body += _mip_array(mips, tex_off + len(tex_body), version=version,
                           declared_count=declared_mip_count)
    if comp_mips is not None:
        tex_body += _mip_array(comp_mips, tex_off + len(tex_body), version=version)
    tex_body += trailing

    exports = [
        ExportRec(pal_class, 0, 0, names.index(name + "Pal"), RF_TEXTURE, bytes(pal_body)),
        ExportRec(tex_class, 0, 0, names.index(name), RF_TEXTURE, bytes(tex_body)),
    ]
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
