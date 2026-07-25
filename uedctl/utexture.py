"""Native (pure-Python, no wine/UCC) decoder for UnrealEngine-1 textures: UTexture +
UPalette exports out of a package file (`.utx`/`.u`) → RGB pixel bytes.

Promoted from `dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness/utexture_decode.py`
(the spike file stays put as evidence). The decoder was validated byte-identical to
`UCC batchexport`'s own PCX output across the whole Deus Ex texture corpus (spike
`2026-06-27-decontainerize-uedctl/01-native-texture-decode.md`, ✅ RESOLVED). API is the
spike's, unchanged: `load_package` / `decode_texture` / `decode_palette` / `mip0_to_rgb`
(the spike's stdlib PNG writer is dropped — Pillow owns image encode in uedctl).

On top of the decoder sits the preview-facing ref resolver (`TextureResolver`): a
`Package[.Group].Name` texture ref → decoded `(width, height, rgb_bytes)`, searching the
composed config package list (`config.composed_search_files` — project overlay shadows
game base, same stem-dedup contract as materialize). Per-invocation caching only; no
on-disk cache. A bare (unqualified) ref, an unknown package/texture, or an undecodable
format all resolve to None (a MISS — the caller decides how to surface it); resolution
never raises for a missing/corrupt package.

UE1 object serial body = a tagged-property list terminated by the name "None", then
class-specific trailing data. For UTexture the trailing data is the Mips TArray (each
FMipmap = a lazy-array skip-offset [absent below file-version 63 — e.g. v61 packages],
the pixel bytes, then USize/VSize/UBits/VBits). For UPalette it is a TArray of 256 RGBA.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

_MAGIC = 0x9E2A83C1

# ETextureFormat (UE1). DeusEx content is overwhelmingly P8 (8-bit palettized).
TEXF = {0: "P8", 1: "RGBA7", 2: "RGB16", 3: "DXT1", 4: "RGB8", 5: "RGBA8"}


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

    def name_of_ref(self, idx: int) -> str | None:
        """Object-ref → bare object name (export>0, import<0, 0=None)."""
        if idx == 0:
            return None
        if idx > 0:
            e = self.exports[idx - 1]
            return self.names[e["nm"]]
        j = -idx - 1
        return self.names[self.imports[j][3]] if 0 <= j < len(self.imports) else None

    def class_of_export(self, i0: int) -> str | None:
        """Class name of export at 0-based index i0 (None == a UClass itself)."""
        return self.name_of_ref(self.exports[i0]["cls"])


def load_package(path: str) -> Package:
    """Parse a package file's header + name/import/export tables. Raises ValueError on a
    non-package / truncated file (the resolver catches this and treats it as a miss)."""
    with open(path, "rb") as f:
        buf = f.read()
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != _MAGIC:
        raise ValueError(f"{path}: bad magic {tag:#010x}")
    version = ver_l & 0xFFFF

    def read_name(pos):
        if version < 64:
            end = buf.index(b"\x00", pos)
            return buf[pos:end].decode("latin-1"), end + 1 + 4
        length, pos = _ci(buf, pos)
        s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
        return s, pos + length + 4

    names, pos = [], nameoff
    for _ in range(namecnt):
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
    name: str
    fmt: int
    palette_ref: int
    mips: list[Mip] = field(default_factory=list)
    props: dict = field(default_factory=dict)


def decode_texture(pkg: Package, i0: int) -> TextureObj:
    """Decode the UTexture export at 0-based index `i0` (props + all mips). Raises
    ValueError on any layout inconsistency (never silently mis-reads)."""
    e = pkg.exports[i0]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    end = so + sz
    props, pos = _read_props(buf, so, end, pkg.names)
    fmt = props.get("Format", (_PT_BYTE, 0))[1]
    pal = props.get("Palette", (_PT_OBJECT, 0))[1]
    # Trailing: Mips = TArray<FMipmap>
    mipcount, pos = _ci(buf, pos)
    mips = []
    for _ in range(mipcount):
        # FMipmap: a TLazyArray skip-offset (absolute file pos past the data) — present
        # only in file-version >= 63 (v68/v69), ABSENT in v61 — then the byte data
        # (compact count + bytes), then USize/VSize/UBits/VBits.
        if pkg.version >= 63:
            skip = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        else:
            skip = None
        dcount, pos = _ci(buf, pos)
        data = buf[pos:pos + dcount]; pos += dcount
        if skip is not None and pos != skip:
            raise ValueError(f"mip skip-offset mismatch: pos={pos} skip={skip} "
                             f"(FMipmap layout wrong)")
        usize, vsize = struct.unpack_from("<II", buf, pos); pos += 8
        pos += 2  # UBits, VBits
        mips.append(Mip(usize, vsize, data))
    if pos != end:
        raise ValueError(f"texture body not at EOF: pos={pos} != end={end} "
                         f"(trailing {end - pos} bytes unparsed)")
    return TextureObj(pkg.names[e["nm"]], fmt, pal, mips, props)


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


def textures(pkg: Package) -> list[int]:
    """0-based export indices of every Texture-classed export in the package."""
    return [i for i, e in enumerate(pkg.exports) if pkg.class_of_export(i) == "Texture"]


def mip0_to_rgb(mip: Mip, palette: list[tuple[int, int, int]]) -> bytes:
    """P8 mip bytes + palette → packed RGB (width*height*3 bytes, row-major)."""
    out = bytearray(mip.width * mip.height * 3)
    for i, idx in enumerate(mip.data):
        r, g, b = palette[idx]
        out[i * 3] = r; out[i * 3 + 1] = g; out[i * 3 + 2] = b
    return bytes(out)


# --- ref resolution over the composed search path ------------------------------

class TextureResolver:
    """Resolve `Package[.Group].Name` texture refs to decoded RGB over a composed package
    file list (the `(host_path, provenance)` tuples of `config.composed_search_files`, or
    plain path strings). Stem lookup is case-insensitive (FName semantics); the list is
    already stem-deduped project-shadows-base, so first-match IS the effective package.

    `resolve(ref)` → `(width, height, rgb_bytes)` or None on ANY miss: a bare
    (unqualified) ref — a dotted package qualifier is required, consistent with
    `assemble._patch_surf_refs` (a cross-package stem scan would be ambiguous); an
    unknown package stem; a package file that fails to parse; an unknown texture name
    (or group mismatch on a 3-part ref); a non-P8 format; a non-local palette. Never
    raises for content problems. Results (including misses) are cached per resolver
    instance — per-invocation caching only."""

    def __init__(self, search_files) -> None:
        self._by_stem: dict[str, str] = {}
        for entry in search_files:
            path = entry[0] if isinstance(entry, tuple) else entry
            stem = os.path.splitext(os.path.basename(path))[0].casefold()
            self._by_stem.setdefault(stem, path)
        self._pkg_cache: dict[str, Package | None] = {}
        self._ref_cache: dict[str, tuple[int, int, bytes] | None] = {}
        self._masked_cache: dict[str, tuple[int, int, bytes, bytes] | None] = {}
        self._exists_cache: dict[str, bool] = {}

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
                    self._pkg_cache[key] = None      # unreadable/corrupt package → miss
        return self._pkg_cache[key]

    def resolve(self, ref: str) -> tuple[int, int, bytes] | None:
        key = ref.casefold()
        if key not in self._ref_cache:
            self._ref_cache[key] = self._resolve_uncached(ref)
        return self._ref_cache[key]

    def _texture_named(self, pkg: Package, name: str, group: str | None) -> bool:
        want = name.casefold()
        want_group = group.casefold() if group else None
        for i in textures(pkg):
            e = pkg.exports[i]
            if pkg.names[e["nm"]].casefold() != want:
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
            self._exists_cache[key] = self._exists_uncached(ref)
        return self._exists_cache[key]

    def _exists_uncached(self, ref: str) -> bool:
        parts = ref.split(".")
        if len(parts) == 1:                              # bare name → any package on the path
            return any(pkg is not None and self._texture_named(pkg, parts[0], None)
                       for pkg in (self._package(stem) for stem in self._by_stem))
        if len(parts) == 2:
            pkg_stem, group, name = parts[0], None, parts[1]
        elif len(parts) == 3:
            pkg_stem, group, name = parts
        else:
            return False
        pkg = self._package(pkg_stem)
        return pkg is not None and self._texture_named(pkg, name, group)

    def resolve_masked(self, ref: str) -> tuple[int, int, bytes, bytes] | None:
        """Like `resolve`, but also returns a transparency `mask` (w*h bytes, 1 = opaque, 0 =
        transparent). DeusEx editor sprites are masked with palette index 0 = transparent, so a
        sprite blit can skip those pixels and not occlude the geometry behind it. Same miss rules +
        per-instance caching as `resolve`."""
        key = ref.casefold()
        if key not in self._masked_cache:
            got = self._decode_ref(ref)
            if got is None:
                self._masked_cache[key] = None
            else:
                m, pal = got
                self._masked_cache[key] = (m.width, m.height, mip0_to_rgb(m, pal),
                                           bytes(1 if idx != 0 else 0 for idx in m.data))
        return self._masked_cache[key]

    def _decode_ref(self, ref: str):
        """Shared texture lookup+decode for `resolve`/`resolve_masked`: `Package[.Group].Name` →
        `(mip0, palette)` or None on any miss (bare/over-dotted ref, unknown package/texture, group
        mismatch, non-P8, undecodable, non-local palette)."""
        parts = ref.split(".")
        if len(parts) == 2:
            pkg_stem, group, name = parts[0], None, parts[1]
        elif len(parts) == 3:
            pkg_stem, group, name = parts
        else:
            return None                              # bare or over-dotted ref → miss
        pkg = self._package(pkg_stem)
        if pkg is None:
            return None
        want = name.casefold()
        want_group = group.casefold() if group else None
        for i in textures(pkg):
            e = pkg.exports[i]
            if pkg.names[e["nm"]].casefold() != want:
                continue
            if want_group is not None:
                outer = pkg.name_of_ref(e["outer"])
                if outer is None or outer.casefold() != want_group:
                    continue
            try:
                t = decode_texture(pkg, i)
            except (ValueError, struct.error, IndexError):
                return None
            if t.fmt != 0 or not t.mips:             # only P8 decodes (DX corpus is P8)
                return None
            pal_i0 = export_index_of_ref(pkg, t.palette_ref)
            if pal_i0 is None or not (0 <= pal_i0 < len(pkg.exports)):
                return None
            try:
                pal = decode_palette(pkg, pal_i0)
            except (ValueError, struct.error, IndexError):
                return None
            if len(pal) < 256:
                pal = pal + [(0, 0, 0)] * (256 - len(pal))
            return t.mips[0], pal
        return None

    def _resolve_uncached(self, ref: str) -> tuple[int, int, bytes] | None:
        got = self._decode_ref(ref)
        if got is None:
            return None
        m, pal = got
        return (m.width, m.height, mip0_to_rgb(m, pal))
