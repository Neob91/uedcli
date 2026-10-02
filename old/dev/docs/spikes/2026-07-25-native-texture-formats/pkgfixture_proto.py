"""Prototype: build a synthetic UE1 `.utx` in memory, from scratch, for texture tests.

**This is the committed prototype the spec/plan's `pkgfixture.py` is lifted from.** It is
spike evidence, not shipped code — the build promotes it (cleaned up) to
`uedcli/tests/pkgfixture.py`. Run it directly to self-verify:

    cd Tools/uedcli && .venv/bin/python \
        dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py

It writes nothing to disk by default; `main()` builds every shape the build needs, parses
each one back through `uedcli.utexture.load_package`, and asserts the round trip.

Why it exists: every offline "Done when" in the native-texture-formats plan needs a package
containing a texture with a *chosen* mip chain (a `CompMips` array, a zero-length mip, a
dangling `Palette` ref, a hostile mip count). No such package can be lifted from real
content, and `uedcli/native/pkg_write.py` already contains a from-scratch container writer
(`build_package`) — so the whole fixture is ~150 lines of body encoding on top of it.

What it covers, and the shapes it proves buildable:

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

THE TRAP, learned the hard way: a property tag's **size code must match the encoded value's
real length**. An `ObjectProperty` whose ref encodes to a single compact-index byte needs
size code 0 (=1 byte), not 2 (=4 bytes), or every subsequent property mis-parses and the
`None` terminator is never found. `_prop_object()` below derives the size code from the
encoded bytes for exactly this reason.

The one piece of genuine back-patching is each `FMipmap`'s `WidthOffset`: a TLazyArray skip
offset that is the **absolute file offset just past that mip's `Data`**. It is computable
before the bodies exist because `build_package` lays export bodies contiguously starting at
`dataoff = header_len + len(encoded name table)` — so the name table must be fully populated
before any body is encoded. `_Layout` below does exactly that.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from uedcli.native.codec import write_ci                       # noqa: E402
from uedcli.native.pkg_write import (NameTable, ImportRec,     # noqa: E402
                                     ExportRec, build_package)

# UE1 property type nibbles (see `utexture._read_props`).
PT_BYTE, PT_BOOL, PT_OBJECT = 1, 3, 5

# RF_Public | RF_LoadForClient | RF_LoadForServer | RF_LoadForEdit — the object flags a
# real texture export carries. Nothing in the decode path reads them; they are set so the
# fixture matches real content.
RF_TEXTURE = 0x00000004 | 0x00010000 | 0x00020000 | 0x00040000


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
                    declared_mip_count: int | None = None,
                    version: int = 69, licensee: int = 0) -> bytes:
    """Build a whole synthetic `.utx` carrying one Palette export + one Texture export.

    `mips` / `comp_mips` are `[(w, h, data), ...]`; `comp_mips=None` means no `bHasComp`
    property at all (so ZERO bytes follow `Mips`). `fmt=None` omits the `Format` property
    entirely (the overwhelmingly common real case — it then defaults to 0 = P8).
    `palette_ref` overrides the emitted `Palette` object ref (pass an out-of-range export
    ref to reproduce the missing-palette shape). `trailing` is appended after the mip
    array(s) (the `FireTexture` `TArray<FSpark>` shape).
    """
    if mips is None:
        mips = [(2, 2, bytes([0, 1, 2, 3]))]
    if palette is None:
        palette = [(i, i, i, 255) for i in range(256)]

    names = NameTable()
    # Every name must exist BEFORE the table is encoded, because the mip skip offsets are
    # absolute and `dataoff` depends on the encoded table's length.
    for n in ("Core", "Package", "Class", "Engine", "Texture", "Palette", "None",
              "Format", "bHasComp", "CompFormat", name, name + "Pal"):
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
                         names=names, imports=imports, exports=exports)


# --- self-verification -------------------------------------------------------

def _p8_chain(w, h):
    out = []
    while True:
        out.append((w, h, bytes((x * 7) & 0xFF for x in range(w * h))))
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return out


def _bc1_chain(w, h):
    out, i = [], 0
    while True:
        n = ((w + 3) // 4) * ((h + 3) // 4) * 8
        out.append((w, h, bytes((i + x) & 0xFF for x in range(n))))
        i += 1
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return out


def main() -> int:
    import tempfile
    from uedcli import utexture

    def parse(buf, fname="Fixture.utx"):
        d = tempfile.mkdtemp()
        p = os.path.join(d, fname)
        with open(p, "wb") as f:
            f.write(buf)
        return utexture.load_package(p), p

    # 1. the two-array (live-bug) shape ---------------------------------------
    pkg, _ = parse(texture_package(mips=_p8_chain(64, 64), comp_mips=_bc1_chain(64, 64)))
    assert [pkg.class_of_export(i) for i in range(2)] == ["Palette", "Texture"], \
        [pkg.class_of_export(i) for i in range(2)]
    assert utexture.textures(pkg) == [1]
    # today's one-array decoder must FAIL here — that is exactly the bug S1 fixes
    try:
        utexture.decode_texture(pkg, 1)
        raise AssertionError("expected the one-array decoder to overrun on CompMips")
    except ValueError as exc:
        assert "not at EOF" in str(exc), exc
    print("two-array body: parses, classes resolve, one-array decode fails as expected")

    # ...and a hand two-array parse lands exactly on the declared end.
    e = pkg.exports[1]
    props, pos = utexture._read_props(pkg.buf, e["soff"], e["soff"] + e["ssize"], pkg.names)
    assert props["bHasComp"] == (3, True) and props["CompFormat"] == (1, 3), props
    for _ in range(2):
        cnt, pos = utexture._ci(pkg.buf, pos)
        for _m in range(cnt):
            skip = struct.unpack_from("<I", pkg.buf, pos)[0]; pos += 4
            dc, pos = utexture._ci(pkg.buf, pos)
            pos += dc
            assert pos == skip, (pos, skip)
            pos += 10
    assert pos == e["soff"] + e["ssize"], (pos, e["soff"] + e["ssize"])
    print("two-array parse: every skip offset validates, body is EOF-clean")

    # 2. bHasComp absent => zero bytes after Mips, still EOF-clean --------------
    pkg, _ = parse(texture_package(mips=_p8_chain(8, 8)))
    t = utexture.decode_texture(pkg, 1)
    assert t.fmt == 0 and len(t.mips) == 4 and t.mips[0].width == 8, t
    assert utexture.mip0_to_rgb(t.mips[0], utexture.decode_palette(pkg, 0))[:3] == b"\x00\x00\x00"
    print("single-array body: decodes today, EOF-clean, 0 bytes after Mips")

    # 3. the FireTexture shape: an empty mip + trailing bytes ------------------
    pkg, _ = parse(texture_package(mips=[(64, 64, b"")], trailing=b"\x01" * 24))
    try:
        utexture.decode_texture(pkg, 1)
        raise AssertionError("expected trailing bytes to trip the EOF guard")
    except ValueError as exc:
        assert "not at EOF" in str(exc) and "trailing 24" in str(exc), exc
    print("FireTexture shape: zero-length mip + trailing bytes reproduces the EOF failure")

    # 4. the missing-palette shape ---------------------------------------------
    pkg, _ = parse(texture_package(mips=_p8_chain(4, 4), palette_ref=99))
    t = utexture.decode_texture(pkg, 1)
    assert t.palette_ref == 99
    assert not (0 <= utexture.export_index_of_ref(pkg, 99) < len(pkg.exports))
    print("missing-palette shape: Palette ref points past the export table")

    # 5. the hostile-input shape ------------------------------------------------
    pkg, _ = parse(texture_package(mips=_p8_chain(4, 4), declared_mip_count=1 << 20))
    try:
        utexture.decode_texture(pkg, 1)
        raise AssertionError("expected a lying mip count to fail")
    except (ValueError, struct.error, IndexError) as exc:
        print(f"hostile mip count: today raises {type(exc).__name__} "
              f"(S2 must turn this into a typed corrupt-body)")

    # 6. a stored non-zero Format ------------------------------------------------
    pkg, _ = parse(texture_package(mips=_bc1_chain(16, 16), fmt=3))
    t = utexture.decode_texture(pkg, 1)
    assert t.fmt == 3 and [m.width for m in t.mips] == [16, 8, 4, 2, 1], t
    assert [len(m.data) for m in t.mips] == [128, 32, 8, 8, 8], \
        [len(m.data) for m in t.mips]
    print("stored Format=3 + a BC1 chain flooring at 8 B: parses")

    print("\nALL SHAPES BUILD AND ROUND-TRIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
