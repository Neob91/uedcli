"""Native (pure-Python, no wine/UCC) decoder for UnrealEngine-1 textures: UTexture +
UPalette exports out of a package file (`.utx`/`.u`) → RGB pixel bytes.

Promoted from `dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness/utexture_decode.py`
(the spike file stays put as evidence). The decoder was validated byte-identical to
`UCC batchexport`'s own PCX output across the whole Deus Ex texture corpus (spike
`2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`, ✅ RESOLVED). API is the
spike's, unchanged: `load_package` / `decode_texture` / `decode_palette` / `mip0_to_rgb`
(the spike's stdlib PNG writer is dropped — Pillow owns image encode in uedcli).

On top of the decoder sits the preview-facing ref resolver (`TextureResolver`): a
`Package[.Group].Name` texture ref → a **typed result**, searching the composed config
package list (`config.composed_search_files` — project overlay shadows game base, same
stem-dedup contract as materialize). Per-invocation caching only; no on-disk cache.

`resolve(ref)` returns a `DecodedTexture` or a `TextureError` naming one of twelve cases —
it never returns None, and it never raises for a content problem: a bare (unqualified) ref,
an unknown or unreadable package, an unknown texture and an undecodable layout all come back
as named cases. The caller chooses the disposition.

UE1 object serial body = a tagged-property list terminated by the name "None", then
class-specific trailing data. For UTexture that is `Mips`, a TArray<FMipmap> (each FMipmap =
a lazy-array skip-offset [absent below file-version 63 — e.g. v61 packages], the pixel bytes,
then USize/VSize/UBits/VBits) and then, IF the body's `bHasComp` property is true, a second
identically-encoded array `CompMips` holding a block-compressed copy of the same image. For
UPalette it is a TArray of 256 RGBA.
"""
from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from functools import cached_property

# The pixel half lives in `utexture_decode.py` (one job per file). Re-exported here because the
# names are read as `utexture.X` — by the corpus/layout/block tests among others — and this module
# is the one every caller already has.
from .utexture_decode import (                        # noqa: F401  (re-exported public API)
    DetectionFailure,
    Layout,
    _bc2_alpha,
    _bc3_alpha,
    _bc_colours,
    _BLOCK_BYTES,
    _CLASS_TO_LAYOUT,
    _CODE_TO_CLASS,
    _CODE_TO_LAYOUT,
    _decode_bc1,
    _decode_bc2,
    _decode_bc3,
    _decode_block,
    _decode_linear1,
    _fitting_classes,
    _LINEAR_BPP,
    _rgb565,
    detect_layout,
    mip0_to_rgb,
)

_MAGIC = 0x9E2A83C1


def _ci(buf: bytes, pos: int) -> tuple[int, int]:
    """FCompactIndex: signed variable-length int (UE1)."""
    b = buf[pos]; pos += 1
    neg = b & 0x80
    val = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
    return (-val if neg else val), pos


@dataclass
class Package:
    """A minimally-parsed UE1 package: header tables + the raw bytes (bodies decode lazily)."""
    version: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]
    exports: list[dict]
    buf: bytes

    def name(self, idx: int) -> str | None:
        """Name-table entry `idx`, or None if the index is out of range.

        A package is untrusted input and its tables are not range-checked at load, so every
        index read out of one may be garbage. Returning None rather than raising keeps a
        corrupt file a *reportable* condition instead of an `IndexError` out of the CLI.
        """
        return self.names[idx] if 0 <= idx < len(self.names) else None

    def name_of_ref(self, idx: int) -> str | None:
        """Object-ref → bare object name (export>0, import<0, 0=None), or None if the ref does
        not point at anything this package holds. Total by design — see `name`."""
        if idx > 0:
            j = idx - 1
            return self.name(self.exports[j]["nm"]) if j < len(self.exports) else None
        if idx < 0:
            j = -idx - 1
            return self.name(self.imports[j][3]) if j < len(self.imports) else None
        return None                                  # 0 == the None object

    def class_of_export(self, i0: int) -> str | None:
        """Class name of export at 0-based index i0 (None == a UClass itself, or an
        unresolvable ref)."""
        return self.name_of_ref(self.exports[i0]["cls"]) if 0 <= i0 < len(self.exports) else None


def load_package(path: str) -> Package:
    """Parse a package file's header + name/import/export tables. Raises ValueError on a
    non-package / truncated / structurally impossible file (the resolver catches this and
    reports `package-unreadable`)."""
    with open(path, "rb") as f:
        buf = f.read()
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != _MAGIC:
        raise ValueError(f"{path}: bad magic {tag:#010x}")
    version = ver_l & 0xFFFF

    # EVERY DECLARED COUNT IS BOUNDED BY THE FILE ITSELF, before a single entry is read.
    # These are raw u32s out of an untrusted header. No table entry can occupy fewer than one
    # byte, so a file of N bytes cannot hold more than N of anything — and without this check a
    # header declaring 4 billion names sends the loops below into a walk that allocates until
    # the process is killed. It does NOT fail fast on its own: a name length is a SIGNED compact
    # index, so a negative one moves the cursor backwards, and negative indices into a `bytes`
    # are legal in Python, so the walk cycles inside the buffer instead of running off the end.
    # Measured before this check: a header count of 0xFFFFFFFF ran for over 200 s inside a
    # 2.5 GB cap without returning.
    for what, count in (("name", namecnt), ("import", impcnt), ("export", expcnt)):
        if count > len(buf):
            raise ValueError(f"{path}: header declares {count} {what} table entries in a "
                             f"{len(buf)}-byte file")

    def read_name(pos):
        if version < 64:
            end = buf.index(b"\x00", pos)
            return buf[pos:end].decode("latin-1"), end + 1 + 4
        length, pos = _ci(buf, pos)
        if length < 0:
            raise ValueError(f"{path}: name table entry declares a negative length {length}")
        s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
        return s, pos + length + 4

    names, pos = [], nameoff
    for _ in range(namecnt):
        if not 0 <= pos < len(buf):
            raise ValueError(f"{path}: name table runs past the end of the file at {pos}")
        s, pos = read_name(pos); names.append(s)
    imports, pos = [], impoff
    for _ in range(impcnt):
        cp, pos = _ci(buf, pos); cn, pos = _ci(buf, pos)
        pkgi = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        on, pos = _ci(buf, pos)
        imports.append((cp, cn, pkgi, on))
    exports, pos = [], expoff
    for _ in range(expcnt):
        cls, pos = _ci(buf, pos); sup, pos = _ci(buf, pos)
        outer = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        nm, pos = _ci(buf, pos)
        flv = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        ssize, pos = _ci(buf, pos)
        soff = 0
        if ssize > 0:
            soff, pos = _ci(buf, pos)
        exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm,
                            flags=flv, ssize=ssize, soff=soff))
    return Package(version, names, imports, exports, buf)


# --- tagged property list (UE1 FPropertyTag) ----------------------------------

_PT_BYTE, _PT_INT, _PT_BOOL, _PT_FLOAT, _PT_OBJECT, _PT_NAME = 1, 2, 3, 4, 5, 6
_PT_OBJECT_LEGACY = 8
_PT_STRUCT = 10
_SIZE_FIXED = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}


def _read_props(buf, pos, end, names):
    """Return (props_dict, pos_after_None). props maps name -> (ptype, value)."""
    props = {}
    while pos < end:
        nidx, pos = _ci(buf, pos)
        name = names[nidx] if 0 <= nidx < len(names) else f"<{nidx}>"
        if name == "None":
            break
        info = buf[pos]; pos += 1
        ptype = info & 0x0F
        size_code = (info >> 4) & 0x07
        array_flag = info & 0x80
        if ptype == _PT_STRUCT:
            sidx, pos = _ci(buf, pos)      # struct name (unused here)
        if size_code in _SIZE_FIXED:
            size = _SIZE_FIXED[size_code]
        elif size_code == 5:
            size = buf[pos]; pos += 1
        elif size_code == 6:
            size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == _PT_BOOL:
            props[name] = (ptype, bool(array_flag)); continue
        if array_flag:  # non-bool array element: skip the array index
            b = buf[pos]; pos += 1
            if b >= 0x80:
                pos += 1 if (b & 0xC0) == 0x80 else 3
        raw = buf[pos:pos + size]; pos += size
        if ptype == _PT_BYTE:
            val = raw[0]
        elif ptype == _PT_INT:
            val = int.from_bytes(raw, "little", signed=True)
        elif ptype == _PT_FLOAT:
            val = struct.unpack("<f", raw)[0]
        elif ptype in (_PT_OBJECT, _PT_NAME, _PT_OBJECT_LEGACY):
            val = _ci(raw, 0)[0]
        else:
            val = raw
        props[name] = (ptype, val)
    return props, pos


# --- texture + palette decode --------------------------------------------------

@dataclass
class Mip:
    width: int
    height: int
    data: bytes


@dataclass
class TextureObj:
    """A parsed `UTexture` body.

    `mips` is the `Mips` array (the original image). `comp_mips` is the `CompMips` array — a
    SECOND, block-compressed copy of the same image that `UTexture` serializes immediately
    after `Mips` when its `bHasComp` property is true; it is empty when the flag is absent or
    false. `comp_format` is the `CompFormat` byte that names the compressed copy's layout
    (`fmt` names the `Mips` array's — the two are different codes for different arrays, and
    reading one against the other is a wrong image).

    `trailing_bytes` and `no_mip_data` REPORT the body's integrity rather than judging it:

    * `trailing_bytes` = declared body end minus the parse cursor, `0` for a clean body. On
      file-version 61 there are no per-mip skip offsets, so this is the only integrity signal
      the format offers, which is why it is recorded for every body and not just for the
      shapes a caller expects.
    * `no_mip_data` is true iff no mip in EITHER array carries bytes. Procedural textures
      (`FireTexture` and friends) serialize mips whose `DataCount` is 0, so this is detectable
      from the data and never from a class name.

    Neither field is an error by itself; the caller classifies. `decode_texture` still raises
    where it cannot continue at all — a skip-offset mismatch, a structurally impossible count.
    """
    name: str
    fmt: int
    palette_ref: int
    mips: list[Mip] = field(default_factory=list)
    props: dict = field(default_factory=dict)
    comp_mips: list[Mip] = field(default_factory=list)
    comp_format: int = 0
    trailing_bytes: int = 0
    no_mip_data: bool = False


def _read_mip_array(pkg: Package, pos: int) -> tuple[list[Mip], int]:
    """Read one `TArray<FMipmap>` starting at `pos`; return (mips, pos_after).

    FMipmap = a TLazyArray skip-offset (the ABSOLUTE file position just past this mip's data —
    present only in file-version >= 63, ABSENT in v61), then the byte data (compact count +
    bytes), then USize/VSize/UBits/VBits.
    """
    buf = pkg.buf
    mipcount, pos = _ci(buf, pos)
    # A package is UNTRUSTED INPUT. A corrupt or hostile header can declare a million mips or
    # a two-billion-byte one; without these caps the decoder answers with an IndexError, a
    # MemoryError, or minutes of work. The limits are far above anything real (the biggest
    # texture measured anywhere is 2048x2048, 12 mips), so nothing legitimate is refused.
    if not 0 <= mipcount <= MAX_MIPS:
        raise ValueError(f"mip count {mipcount} is outside 0..{MAX_MIPS}")
    mips = []
    for _ in range(mipcount):
        if pkg.version >= 63:
            skip = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        else:
            skip = None
        dcount, pos = _ci(buf, pos)
        if not 0 <= dcount <= MAX_MIP_BYTES:
            raise ValueError(f"mip byte count {dcount} is outside 0..{MAX_MIP_BYTES}")
        if pos + dcount > len(buf):
            raise ValueError(f"mip declares {dcount} bytes at {pos}, past the {len(buf)}-byte file")
        data = buf[pos:pos + dcount]; pos += dcount
        if skip is not None and pos != skip:
            raise ValueError(f"mip skip-offset mismatch: pos={pos} skip={skip} "
                             f"(FMipmap layout wrong)")
        usize, vsize = struct.unpack_from("<II", buf, pos); pos += 8
        pos += 2  # UBits, VBits
        if not (0 <= usize <= MAX_MIP_DIM and 0 <= vsize <= MAX_MIP_DIM):
            raise ValueError(f"mip dimensions {usize}x{vsize} exceed {MAX_MIP_DIM}")
        mips.append(Mip(usize, vsize, data))
    return mips, pos


def decode_texture(pkg: Package, i0: int) -> TextureObj:
    """Decode the UTexture export at 0-based index `i0` — props, `Mips`, and `CompMips` when
    the body's `bHasComp` property says it is there.

    The body is `props … "None"; Mips; if bHasComp: CompMips`. `bHasComp` and `CompFormat` are
    TAGGED PROPERTIES, not raw bytes after `Mips` — reading them as raw bytes fails on every
    real sample. Measured over the whole Deus Ex tree: the property reading lands exactly on
    the declared body end for 207 / 207 previously-failing `Texture` exports, and consumes
    zero bytes when the flag is absent or false.
    (`dev/docs/unrealed/package-format.md`, "UTexture body".)

    A body that does not end where the export table says is REPORTED (`trailing_bytes`), not
    raised on — see `TextureObj`. Raises `ValueError` only where the parse cannot continue.
    """
    e = pkg.exports[i0]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    end = so + sz
    props, pos = _read_props(buf, so, end, pkg.names)
    fmt = props.get("Format", (_PT_BYTE, 0))[1]
    pal = props.get("Palette", (_PT_OBJECT, 0))[1]
    has_comp = bool(props.get("bHasComp", (_PT_BOOL, False))[1])
    comp_format = props.get("CompFormat", (_PT_BYTE, 0))[1]
    mips, pos = _read_mip_array(pkg, pos)
    comp_mips: list[Mip] = []
    if has_comp:
        comp_mips, pos = _read_mip_array(pkg, pos)
    no_data = not any(m.data for m in mips) and not any(m.data for m in comp_mips)
    return TextureObj(pkg.name(e["nm"]) or "", fmt, pal, mips, props,
                      comp_mips=comp_mips, comp_format=comp_format,
                      trailing_bytes=end - pos, no_mip_data=no_data)


def decode_palette(pkg: Package, i0: int) -> list[tuple[int, int, int]]:
    """Decode the UPalette export at 0-based index `i0` → 256 (r, g, b) tuples."""
    e = pkg.exports[i0]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    _props, pos = _read_props(buf, so, so + sz, pkg.names)
    count, pos = _ci(buf, pos)
    cols = []
    for _ in range(count):
        r, g, b = buf[pos], buf[pos + 1], buf[pos + 2]
        pos += 4                             # skip alpha
        cols.append((r, g, b))
    if pos != so + sz:
        raise ValueError(f"palette body not at EOF: {pos} != {so + sz} (count={count})")
    return cols


def export_index_of_ref(pkg: Package, ref: int) -> int | None:
    """A local export object ref (>0) -> 0-based export index."""
    return ref - 1 if ref > 0 else None


ENGINE_TEXTURE = "Engine.Texture"        # the descendant-match base (mirrors classindex.ENGINE_TEXTURE)


def textures(pkg: Package, class_index=None) -> list[int]:
    """0-based export indices of the package's texture exports.

    `class_index=None` (the low-level default) matches the EXACT `Texture` class by
    unqualified name — every existing caller and the tests that assert it stay unchanged.
    A `ClassIndex` WIDENS the match to every `Engine.Texture` DESCENDANT (`FireTexture`,
    `ScriptedTexture`, …) via `descends_from(class_fqcn_of_export(pkg, i), "Engine.Texture")`.
    A `None` fqcn (a class defined locally in this package, `class_fqcn_of_export` returns
    None) is not a texture and is skipped — never fed to `descends_from`, whose
    `None.casefold()` would crash."""
    if class_index is None:
        return [i for i, e in enumerate(pkg.exports) if pkg.class_of_export(i) == "Texture"]
    out = []
    for i in range(len(pkg.exports)):
        fqcn = class_fqcn_of_export(pkg, i)
        if fqcn is not None and class_index.descends_from(fqcn, ENGINE_TEXTURE):
            out.append(i)
    return out


def class_fqcn_of_export(pkg: Package, i0: int) -> str | None:
    """`Package.Class` for the export at 0-based index `i0`, or None when the class is not an
    IMPORT (a class defined in this same package, or an export that is itself a class).

    Needed because resolving a class's property defaults requires the fully qualified name:
    a texture's class is `Texture`, but `Engine.Texture` is what names it across packages. The
    qualifier comes from the class import's own package ref, not from the file it appears in.
    """
    cls_ref = pkg.exports[i0]["cls"]
    if cls_ref >= 0:                             # 0 = None; >0 = a class export in THIS package
        return None
    j = -cls_ref - 1
    if not 0 <= j < len(pkg.imports):
        return None
    _cp, _cn, pkg_ref, name_idx = pkg.imports[j]
    outer = pkg.name_of_ref(pkg_ref)
    inner = pkg.name(name_idx)
    return f"{outer}.{inner}" if outer and inner else None




# layout name → `(mip, palette) -> (rgb, mask)`. A layout DETECTION can succeed for a layout
# that is not in here — that is the "no verified decoder for it" case, and keeping the two
# apart is what lets the error name what the file actually is.
_DECODERS = {"linear1": _decode_linear1, "bc1": _decode_bc1,
             "bc2": _decode_bc2, "bc3": _decode_bc3}

# The layouts whose pixels are palette indices. Everything else carries its own colours.
_NEEDS_PALETTE = {"linear1"}




# --- the typed decode result ---------------------------------------------------

# Hostile-input caps. A package is untrusted input: a corrupt or malicious header can declare
# a million mips or a 2-billion-pixel mip, and the decoder must answer with a named case in
# bounded time and memory rather than an IndexError, a MemoryError, or a hang. The limits are
# far above anything real — the largest texture measured anywhere on this machine is 2048x2048
# with 12 mips — so nothing legitimate is refused.
MAX_MIPS = 32                                  # 2**31 would need 32 halvings
MAX_MIP_DIM = 1 << 16                          # 65536 px on a side
MAX_MIP_BYTES = 1 << 28                        # 256 MB of pixel data in one mip


@dataclass(frozen=True)
class DecodedTexture:
    """A texture ref that decoded. Returned by `TextureResolver.resolve`.

    `mask` is `width*height` bytes, 1 = opaque and 0 = transparent, derived **only from the
    pixel data**: for P8 that is the palette-index-0 convention. `b_masked` / `b_alpha_texture`
    are the engine's own render-policy flags, REPORTED as facts and never applied here — the
    caller decides what they mean. Folding them in would make identical bytes decode to two
    different images depending on a flag the pixel layer does not own.

    `layout` names the pixel layout the decode used and `layout_source` says how it was
    settled — `"data"` when the mip sizes named it on their own with the format code
    unconsulted, `"format-code"` when the code broke a tie between layouts the data had
    already fitted. `format_code` is the texture's
    EFFECTIVE `Format` byte: the stored value if the property is present, else `0`. UE1 omits
    any property equal to its class default, so an absent `Format` is not a missing code — it
    IS the byte 0, which is `TEXF_P8`. There is deliberately no "was it stored?" field.

    `array` says which of the body's two mip arrays the pixels came from — `"mips"` (the
    original) or `"comp-mips"` (the lossy block-compressed copy), so a caller can see that it
    was handed the second-best image.

    `width`/`height`/`rgb`/`mask` are **mip 0**. `mips` is the WHOLE pyramid of the selected
    array, `(w, h, rgb, mask)` per level with mip 0 first — a caller that picks a level from
    screen density (`actor preview --faces textured`) needs all of them. It is a lazy property,
    not a field: a full pyramid costs about a third more work and memory than mip 0 alone, and
    the callers that only ever want level 0 (`level preview --native`, sprite billboards) must
    not pay for one. There is no second `resolve_*` entry point for it — one question, one way
    to ask it.
    """
    ref: str
    width: int
    height: int
    rgb: bytes
    mask: bytes
    layout: str
    layout_source: str
    format_code: int
    array: str
    b_masked: bool | None = None
    b_alpha_texture: bool | None = None
    # The undecoded remainder, kept so `mips` can decode on demand. Excluded from equality and
    # repr: they are the same pixels the public fields already describe.
    _levels: tuple = field(default=(), repr=False, compare=False)
    _palette: tuple = field(default=(), repr=False, compare=False)

    @cached_property
    def mips(self) -> tuple[tuple[int, int, bytes, bytes], ...]:
        """Every mip level as `(width, height, rgb, mask)`, mip 0 first. Decoded on first
        access and cached on the instance (`cached_property` writes straight into `__dict__`,
        which a frozen dataclass still has)."""
        pal = list(self._palette)
        decode = _DECODERS[self.layout]
        out = [(self.width, self.height, self.rgb, self.mask)]
        for m in self._levels[1:]:
            rgb, mask = decode(m, pal)
            out.append((m.width, m.height, rgb, mask))
        return tuple(out)


@dataclass(frozen=True)
class TextureError:
    """A texture ref that did NOT decode, and why. Returned by `TextureResolver.resolve`.

    **This object is TRUTHY**, deliberately. Callers that used to write `if resolver.resolve(r):`
    against a `None`-on-miss contract must be migrated to check the type, and a truthy error is
    what makes that migration a visible failure instead of a silently rendered error object.

    `case` is one of the names below and is the caller's whole decision surface; `detail` is
    human text naming the offending value. The two layers are kept apart on purpose — a REF
    problem is fixed by writing a different ref, a DECODE problem by getting a different file.

    Ref layer:
      `unqualified-ref`     a bare or over-dotted ref; `Package[.Group].Name` is required
      `unknown-package`     no package of that stem on the composed search path
      `package-unreadable`  the package IS on the path but will not open or parse
      `unknown-texture`     no `Texture`-classed export of that name (a group mismatch is this)

    Decode layer:
      `corrupt-body`        the body does not parse, or does not end where it should
      `missing-palette`     the `Palette` object ref dangles, or the palette will not decode
      `no-mip-data`         no mip in either array carries bytes (procedural textures)
      `unverified-format`   a layout we will not guess at: no decoder for it, or its `Format`
                            code names something outside the four slots we have verified
      `unrecognised-layout` nothing explains mip 0's byte count at all
      `size-mismatch`       the chain contradicts itself — a later mip fits a different layout
      `ambiguous-alpha`     a 16-byte-block chain with no code to say BC2 or BC3. THE stated
                            limit on universality: nothing in the data separates them
      `ambiguous-layout`    two or more layouts fit and no code names one of them

    Twelve in all. The last four arrive with layout detection, so a caller written against an
    earlier build will not have seen them; `ambiguous-alpha` in particular is the one a caller
    most needs to handle, because it is a permanent refusal rather than a gap.
    """
    ref: str
    case: str
    detail: str


TextureResult = DecodedTexture | TextureError


# --- catalog-facing identity, Layer-2 facts, enumeration -----------------------

def texture_identity(decoded: DecodedTexture) -> str:
    """The FROZEN Layer-1 content identity: `sha256(uint32_le(w) ‖ uint32_le(h) ‖ rgb)` over mip 0's
    pixels. The mask is deliberately NOT hashed — identical pixels behind different masks are ONE
    classifiable thing. This hex is every tracked shard's filename, so a decode change silently
    re-keys the whole store; it is pinned by a committed golden (never change it without a ruling)."""
    h = hashlib.sha256()
    h.update(struct.pack("<II", decoded.width, decoded.height))
    h.update(decoded.rgb)
    return h.hexdigest()


def procedural_identity(package: str, name: str) -> str:
    """The name identity for a texture with no stored pixels (a procedural: `FireTexture` and
    friends, whose decode returns `no-mip-data`): casefolded `Package.Name`
    (`direction/asset-catalog.md` — name where content does not exist)."""
    return f"{package}.{name}".casefold()


def group_of_export(pkg: Package, i0: int) -> str | None:
    """A texture export's GROUP (Layer-2 fact): its Outer object's name — `Ladder` for a ladder
    texture — or None for a group-less top-level export (Outer ref 0). Never part of identity."""
    if not 0 <= i0 < len(pkg.exports):
        return None
    return pkg.name_of_ref(pkg.exports[i0]["outer"])


def package_texture_refs(package: str, entries: list[tuple[str, str | None]]) -> list[str]:
    """Assign each `(name, group)` its catalog ref within `package`: the 2-part `Package.Name`
    normally, or the 3-part `Package.Group.Name` when the Name COLLIDES with another entry in the
    same package (and this one has a group). A 2-part ref binds regardless of group, so the group
    stays a Layer-2 fact for the common case and only surfaces in the ref to disambiguate a
    collision (`direction/asset-catalog.md`: `CoreTexMetal.LadrBrwnMetal`)."""
    counts: dict[str, int] = {}
    for nm, _g in entries:
        counts[nm.casefold()] = counts.get(nm.casefold(), 0) + 1
    out = []
    for nm, group in entries:
        if counts[nm.casefold()] > 1 and group is not None:
            out.append(f"{package}.{group}.{nm}")
        else:
            out.append(f"{package}.{nm}")
    return out


@dataclass(frozen=True, kw_only=True)
class TextureRef:
    """One enumerated texture on the search path. `ref` is the collision-aware address
    (`Package.Name`, or the 3-part `Package.Group.Name` on an intra-package Name collision) that
    `texture list` prints and that decodes; `group` is the Outer fact (Layer 2), null when the
    export is group-less. `export_index` lets `show`/`list --json` recover Layer-2 facts without
    re-searching."""
    ref: str
    package: str
    export_index: int
    group: str | None


# --- ref resolution over the composed search path ------------------------------

class TextureResolver:
    """Resolve `Package[.Group].Name` texture refs to decoded RGB over a composed package
    file list (the `(host_path, provenance)` tuples of `config.composed_search_files`, or
    plain path strings). Stem lookup is case-insensitive (FName semantics); the list is
    already stem-deduped project-shadows-base, so first-match IS the effective package.

    `resolve(ref)` returns a **typed result**: a `DecodedTexture`, or a `TextureError` naming
    the case and the offending value. It never returns `None` and it never raises for a content
    problem — a corrupt package, a hostile mip count and an unknown name all come back as cases.
    The caller chooses the disposition: `level preview --native` degrades to a checkerboard and
    warns, a per-ref request exits 2 naming the ref.

    A bare (unqualified) ref is refused (`unqualified-ref`) rather than scanned for across
    packages — a cross-package stem scan is ambiguous, and `assemble._patch_surf_refs` requires
    the qualifier too. `exists()` is the deliberate exception: existence tolerates ambiguity.

    Results — errors included — are cached per resolver instance and returned by IDENTITY, so
    asking twice hands back the same object. Per-invocation caching only; no on-disk cache."""

    def __init__(self, search_files, class_index=None) -> None:
        self._by_stem: dict[str, str] = {}
        self._stem_spelling: dict[str, str] = {}     # casefold(stem) -> the ref's Package casing
        for entry in search_files:
            path = entry[0] if isinstance(entry, tuple) else entry
            spelling = os.path.splitext(os.path.basename(path))[0]
            stem = spelling.casefold()
            self._by_stem.setdefault(stem, path)
            self._stem_spelling.setdefault(stem, spelling)
        # A ClassIndex widens which exports count as textures from the exact `Texture` class to
        # every `Engine.Texture` DESCENDANT (`textures(pkg, class_index)`). None (the seam's
        # default) keeps the exact match, so author-time `exists()` and every non-catalog caller
        # are unchanged; only the asset-catalog builds a resolver carrying the index.
        self._class_index = class_index
        self._pkg_cache: dict[str, Package | None] = {}
        self._pkg_unreadable: set[str] = set()
        self._ref_cache: dict[str, TextureResult] = {}
        self._exists_cache: dict[str, bool] = {}
        self._defaults_cache: dict[str, dict | None] = {}
        self._defaults_pkgs: dict = {}           # uprops' own package cache, shared across classes

    def _package(self, stem: str) -> Package | None:
        key = stem.casefold()
        if key not in self._pkg_cache:
            path = self._by_stem.get(key)
            if path is None:
                self._pkg_cache[key] = None
            else:
                try:
                    self._pkg_cache[key] = load_package(path)
                except (OSError, ValueError, struct.error, IndexError):
                    # The package IS on the path but will not open or parse. Recorded
                    # separately from "no such stem": the two need different fixes, and until
                    # now they were the same `None`.
                    self._pkg_cache[key] = None
                    self._pkg_unreadable.add(key)
        return self._pkg_cache[key]

    def resolve(self, ref: str) -> TextureResult:
        """`Package[.Group].Name` → a `DecodedTexture` or a `TextureError`. See the class
        docstring; cached by identity per resolver instance."""
        key = ref.casefold()
        if key not in self._ref_cache:
            try:
                self._ref_cache[key] = self._decode_ref(ref)
            except (ValueError, struct.error, IndexError, KeyError, MemoryError,
                    OverflowError, UnicodeDecodeError) as exc:
                # THE BACKSTOP. A package's header tables are read at load time and never
                # range-checked, so a corrupt file can carry a name index, an object ref or an
                # export index that points nowhere, and the walk below reads several of them.
                # The accessors are individually total, but one unguarded index anywhere under
                # here would otherwise surface as a Python traceback out of `level preview` or
                # author-time validation. Measured before this guard: 12 distinct single-byte
                # corruptions of a 1,459-byte package raised IndexError out of `resolve()`.
                self._ref_cache[key] = TextureError(
                    ref, "package-unreadable",
                    f"{ref}: the package is on the search path but its structure will not "
                    f"read ({type(exc).__name__}: {exc})")
        return self._ref_cache[key]

    def package_for_ref(self, ref: str) -> tuple[Package, int] | None:
        """`(package, export_index)` for a `Package[.Group].Name` ref, or None if it does not
        resolve to a texture export — the seam `show`/`list --json` use to read Layer-2 facts
        (group needs the export, which `DecodedTexture` does not carry). Uses the SAME widened
        matcher and package cache as `resolve`."""
        parts = ref.split(".")
        if len(parts) == 2:
            pkg_stem, group, name = parts[0], None, parts[1]
        elif len(parts) == 3:
            pkg_stem, group, name = parts
        else:
            return None
        pkg = self._package(pkg_stem)
        if pkg is None:
            return None
        want = name.casefold()
        want_group = group.casefold() if group else None
        for i in textures(pkg, self._class_index):
            e = pkg.exports[i]
            if (pkg.name(e["nm"]) or "").casefold() != want:
                continue
            if want_group is not None:
                outer = pkg.name_of_ref(e["outer"])
                if outer is None or outer.casefold() != want_group:
                    continue
            return pkg, i
        return None

    def texture_refs(self) -> list[TextureRef]:
        """Every `Engine.Texture`-DESCENDANT export across the whole search path, as `TextureRef`s
        sorted by ref (case-insensitively). Requires the class index the catalog builds the resolver
        with; without one there is nothing to widen the match, so it returns []. Reads only the
        header tables — an undecodable-but-real texture still enumerates, and no pixels are decoded
        here."""
        if self._class_index is None:
            return []
        out: list[TextureRef] = []
        for stem_cf in self._by_stem:
            pkg = self._package(stem_cf)
            if pkg is None:
                continue
            spelling = self._stem_spelling.get(stem_cf, stem_cf)
            idxs = textures(pkg, self._class_index)
            names_groups = [(pkg.name(pkg.exports[i]["nm"]) or "",
                             pkg.name_of_ref(pkg.exports[i]["outer"])) for i in idxs]
            refs = package_texture_refs(spelling, names_groups)
            for i, ref, (_name, group) in zip(idxs, refs, names_groups):
                out.append(TextureRef(ref=ref, package=spelling, export_index=i, group=group))
        out.sort(key=lambda t: t.ref.casefold())
        return out

    def _texture_named(self, pkg: Package, name: str, group: str | None) -> bool:
        want = name.casefold()
        want_group = group.casefold() if group else None
        for i in textures(pkg, self._class_index):
            e = pkg.exports[i]
            if (pkg.name(e["nm"]) or "").casefold() != want:
                continue
            if want_group is not None:
                outer = pkg.name_of_ref(e["outer"])
                if outer is None or outer.casefold() != want_group:
                    continue
            return True
        return False

    def exists(self, ref: str) -> bool:
        """Author-time EXISTENCE check — does a `Texture`-classed export of this name exist on the
        path? Unlike `resolve()` this returns True for a real texture even when it is non-P8 /
        imported-palette / otherwise undecodable, so validation never false-rejects a materializable
        ref (the codebase's "no false reject" principle). A bare (unqualified) name is "exists in ANY
        package on the path" (existence tolerates ambiguity — we don't qualify for storage). An
        over-dotted ref (>3 parts) can never match → False. Result-cached per resolver instance (a
        brush with many same-textured polys asks once)."""
        key = ref.casefold()
        if key not in self._exists_cache:
            try:
                self._exists_cache[key] = self._exists_uncached(ref)
            except (ValueError, struct.error, IndexError, KeyError, MemoryError,
                    OverflowError, UnicodeDecodeError):
                # Same backstop as `resolve`, and the bare-name form makes it likelier: it
                # scans EVERY package on the path, so one damaged file poisons every lookup.
                # A predicate cannot report a case, and "we could not tell" must not
                # false-reject a ref the engine would accept, so an unreadable package
                # contributes nothing rather than answering False for the whole query.
                self._exists_cache[key] = False
        return self._exists_cache[key]

    def _exists_uncached(self, ref: str) -> bool:
        parts = ref.split(".")
        if len(parts) == 1:                              # bare name → any package on the path
            for stem in self._by_stem:
                pkg = self._package(stem)
                if pkg is None:
                    continue
                try:
                    if self._texture_named(pkg, parts[0], None):
                        return True
                except (ValueError, struct.error, IndexError, KeyError):
                    continue                         # one damaged package, not a failed query
            return False
        if len(parts) == 2:
            pkg_stem, group, name = parts[0], None, parts[1]
        elif len(parts) == 3:
            pkg_stem, group, name = parts
        else:
            return False
        pkg = self._package(pkg_stem)
        return pkg is not None and self._texture_named(pkg, name, group)

    def _decode_ref(self, ref: str) -> TextureResult:
        """`Package[.Group].Name` → a `DecodedTexture` or a `TextureError`. The one lookup and
        decode path; `resolve` only adds the cache."""
        parts = ref.split(".")
        if len(parts) == 2:
            pkg_stem, group, name = parts[0], None, parts[1]
        elif len(parts) == 3:
            pkg_stem, group, name = parts
        else:
            return TextureError(ref, "unqualified-ref",
                                f"{ref!r} is not a Package[.Group].Name reference; a package "
                                f"qualifier is required (a bare name could match several)")
        pkg = self._package(pkg_stem)
        if pkg is None:
            if pkg_stem.casefold() in self._pkg_unreadable:
                return TextureError(ref, "package-unreadable",
                                    f"package {pkg_stem!r} is on the search path but will not "
                                    f"open or parse")
            return TextureError(ref, "unknown-package",
                                f"no package named {pkg_stem!r} on the composed search path")
        want = name.casefold()
        want_group = group.casefold() if group else None
        for i in textures(pkg, self._class_index):
            e = pkg.exports[i]
            if (pkg.name(e["nm"]) or "").casefold() != want:
                continue
            if want_group is not None:
                outer = pkg.name_of_ref(e["outer"])
                if outer is None or outer.casefold() != want_group:
                    continue
            return self._decode_export(ref, pkg, i)
        if want_group is not None:
            return TextureError(ref, "unknown-texture",
                                f"no Texture named {name!r} in group {group!r} of package "
                                f"{pkg_stem!r}")
        return TextureError(ref, "unknown-texture",
                            f"no Texture named {name!r} in package {pkg_stem!r}")

    def _effective_flag(self, pkg: Package, i: int, t: TextureObj, name: str) -> bool | None:
        """A texture's effective `bMasked` / `bAlphaTexture`: **the export's own tag if it is
        present, else the RESOLVED CLASS DEFAULT** — never "absent means false".

        UE1 omits any tagged property equal to its class default, so an absent tag means
        "equal to the default"; only the default says whether that is true or false. Resolving
        it walks the texture class's ancestor chain through the CODE packages on the composed
        search path (`uprops.resolve_class_defaults`), and a property the chain never states
        falls to its type's zero, which for a bool is `False`.

        **On a path with no code package the answer is `None`, not `False`.** That is exactly
        the "read any texture from any engine" case — a lone `.utx` handed to the tool — where
        no default can be resolved and neither branch of the rule applies. Reporting `False`
        would report a value nothing supplied, and "don't know" is never returned as a negative
        answer. Known cost, recorded rather than hidden: a caller that ORs the flag into a
        render decision treats `None` as falsy, so on such a path a masked texture renders
        unmasked unless something else says otherwise.
        """
        tag = t.props.get(name)
        if tag is not None:
            return bool(tag[1])
        defaults = self._class_defaults(pkg, i)
        if defaults is None:
            return None
        text = defaults.get((name.casefold(), 0))
        return False if text is None else text.strip().casefold() == "true"

    def _class_defaults(self, pkg: Package, i: int) -> dict | None:
        """The effective class defaults of this export's class, or `None` when the search path
        carries no code package to resolve them from. Memoised per resolver instance and per
        class — every texture in a package shares one answer, and the chain walk decodes whole
        `.u` packages."""
        fqcn = class_fqcn_of_export(pkg, i)
        if fqcn is None:
            return None
        key = fqcn.casefold()
        if key not in self._defaults_cache:
            from . import uprops
            try:
                self._defaults_cache[key] = uprops.resolve_class_defaults(
                    fqcn, resolver=lambda stem: self._by_stem.get(stem.casefold()),
                    _pkgs=self._defaults_pkgs)
            except Exception:
                # `uprops` raises `SchemaError` for an unreachable package, but a code package
                # is also arbitrary binary input: a corrupt one must leave the flag unknown,
                # never take down a texture decode that had already succeeded.
                self._defaults_cache[key] = None
        return self._defaults_cache[key]

    def _decode_export(self, ref: str, pkg: Package, i: int) -> TextureResult:
        """Decode one located `Texture` export into the typed result."""
        try:
            t = decode_texture(pkg, i)
        except (ValueError, struct.error, IndexError, MemoryError) as exc:
            return TextureError(ref, "corrupt-body", f"{ref}: {exc}")

        # --- array selection, then the gates -----------------------------------------
        # An array CARRIES DATA iff it is non-empty AND at least one of its mips has bytes.
        # "Mips is absent" is not a distinct concept: a zero-length Mips array and one whose
        # mips are all empty are the same thing, and both fall through to the next candidate.
        if any(m.data for m in t.mips):
            selected, array, code = t.mips, "mips", t.fmt
        elif any(m.data for m in t.comp_mips):
            selected, array, code = t.comp_mips, "comp-mips", t.comp_format
        else:
            # This check MUST come before the format gate below: a list of EMPTY mips is
            # truthy, so the gate would pass and `mip0_to_rgb` would return w*h*3 zero bytes
            # — a silent, plausible, completely black image. Procedural textures
            # (FireTexture and friends) are exactly this shape.
            return TextureError(ref, "no-mip-data",
                                f"{ref}: no mip carries pixel data "
                                f"({len(t.mips)} Mips, {len(t.comp_mips)} CompMips, all empty)")
        if t.trailing_bytes:
            # The body did not end where the export table says. On file-version 61 there are
            # no per-mip skip offsets, so this is the only integrity signal the format has.
            return TextureError(ref, "corrupt-body",
                                f"{ref}: {t.trailing_bytes} bytes past the end of the mip "
                                f"array(s), inside a body of {pkg.exports[i]['ssize']}")
        # --- DETECTION, then decodability: two separate questions --------------------
        # The array is judged against ITS OWN code (`Format` for Mips, `CompFormat` for
        # CompMips) — the two arrays hold different layouts by construction.
        found = detect_layout(selected, code=code)
        if isinstance(found, DetectionFailure):
            return TextureError(ref, found.case, f"{ref}: {found.detail}")
        # Detection SUCCEEDED and named the layout; whether a decoder exists for it is the
        # next question, and answering it separately is what lets the error say "this is a
        # 4 bytes/pixel linear texture and we have no verified decoder for it" rather than
        # "unknown". (Rows 2 and this one share a case name deliberately: both mean "a layout
        # we have not verified and will not guess at" — one learned from the code, one from
        # the data.)
        if found.name not in _DECODERS:
            mip0 = selected[0]
            per_px = len(mip0.data) / max(1, mip0.width * mip0.height)
            return TextureError(ref, "unverified-format",
                                f"{ref}: detected {found.name} (from the {found.source}) and "
                                f"there is no verified decoder for it "
                                f"({mip0.width}x{mip0.height}, {per_px:g} bytes/px)")
        mip0 = selected[0]
        pal: list = []
        if found.name in _NEEDS_PALETTE:
            # Only a palettized layout needs one; a block layout carries its colours in the
            # blocks, so a dangling Palette ref beside BC1 data is not this decode's problem.
            pal_i0 = export_index_of_ref(pkg, t.palette_ref)
            if pal_i0 is None or not (0 <= pal_i0 < len(pkg.exports)):
                return TextureError(ref, "missing-palette",
                                    f"{ref}: Palette object ref {t.palette_ref} is not one of "
                                    f"this package's {len(pkg.exports)} exports")
            try:
                pal = decode_palette(pkg, pal_i0)
            except (ValueError, struct.error, IndexError) as exc:
                return TextureError(ref, "missing-palette",
                                    f"{ref}: palette will not decode: {exc}")
            if len(pal) < 256:
                pal = pal + [(0, 0, 0)] * (256 - len(pal))
        # The mask comes ONLY from the pixel data — for P8, the palette-index-0 convention. The
        # engine's own bMasked/bAlphaTexture flags are reported, never applied.
        rgb, mask = _DECODERS[found.name](mip0, pal)
        return DecodedTexture(
            ref=ref, width=mip0.width, height=mip0.height, rgb=rgb, mask=mask,
            layout=found.name, layout_source=found.source, format_code=code, array=array,
            b_masked=self._effective_flag(pkg, i, t, "bMasked"),
            b_alpha_texture=self._effective_flag(pkg, i, t, "bAlphaTexture"),
            _levels=tuple(selected), _palette=tuple(pal))
