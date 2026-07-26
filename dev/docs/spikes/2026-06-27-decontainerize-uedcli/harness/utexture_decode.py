"""Native (pure-Python, no wine/UCC) decoder for Unreal Engine 1 / Deus Ex
textures: UTexture + UPalette → RGB pixels → PNG.

Goal: prove uedcli can extract textures WITHOUT `UCC.exe batchexport` (the only
current path). Reverse-engineered from real `.utx` bytes and the well-known UE1
package + object-serialization format; validated against UCC's own PCX export.

UE1 object serial body = a tagged-property list terminated by the name "None",
then class-specific trailing data. For UTexture the trailing data is the Mips
TArray (each FMipmap = a skip-offset, a lazy byte array of pixel data, then
USize/VSize/UBits/VBits). For UPalette it is a TArray<FColor> of 256 RGBA.

Self-contained: vendors a compact package reader (names/imports/exports) so the
spike runs standalone; the production path will reuse uedcli.dxpkg + the export
reader from the 2026-06-26-uproperty-typed-decode harness.

Usage:
    python utexture_decode.py <pkg.utx> [--list] [--name NAME] [--out DIR]
"""
from __future__ import annotations

import struct
import sys
import zlib
from dataclasses import dataclass, field

_MAGIC = 0x9E2A83C1

# ETextureFormat (UE1). DeusEx content is overwhelmingly P8.
TEXF = {0: "P8", 1: "RGBA7", 2: "RGB16", 3: "DXT1", 4: "RGB8", 5: "RGBA8"}


def ci(buf: bytes, pos: int) -> tuple[int, int]:
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
    version: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]
    exports: list[dict]
    buf: bytes

    def name_of_ref(self, idx: int) -> str | None:
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
    buf = open(path, "rb").read()
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != _MAGIC:
        raise ValueError(f"{path}: bad magic {tag:#010x}")
    version = ver_l & 0xFFFF

    def read_name(pos):
        if version < 64:
            end = buf.index(b"\x00", pos)
            return buf[pos:end].decode("latin-1"), end + 1 + 4
        length, pos = ci(buf, pos)
        s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
        return s, pos + length + 4

    names, pos = [], nameoff
    for _ in range(namecnt):
        s, pos = read_name(pos); names.append(s)
    imports, pos = [], impoff
    for _ in range(impcnt):
        cp, pos = ci(buf, pos); cn, pos = ci(buf, pos)
        pkgi = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        on, pos = ci(buf, pos)
        imports.append((cp, cn, pkgi, on))
    exports, pos = [], expoff
    for _ in range(expcnt):
        cls, pos = ci(buf, pos); sup, pos = ci(buf, pos)
        outer = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        nm, pos = ci(buf, pos)
        flv = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        ssize, pos = ci(buf, pos)
        soff = 0
        if ssize > 0:
            soff, pos = ci(buf, pos)
        exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm,
                            flags=flv, ssize=ssize, soff=soff))
    if pos != len(buf):
        raise ValueError(f"export table did not reach EOF: {pos} != {len(buf)}")
    return Package(version, names, imports, exports, buf)


# --- tagged property list (UE1 FPropertyTag) ----------------------------------

# on-disk FPropertyTag type nibble
PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STR_LEGACY = 1, 2, 3, 4, 5, 6, 7
PT_OBJECT_LEGACY = 8
PT_STRUCT = 10
_SIZE_FIXED = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}


def read_props(buf, pos, end, names):
    """Return (props_dict, pos_after_None). props maps name -> (ptype, value)."""
    props = {}
    while pos < end:
        nidx, pos = ci(buf, pos)
        name = names[nidx] if 0 <= nidx < len(names) else f"<{nidx}>"
        if name == "None":
            break
        info = buf[pos]; pos += 1
        ptype = info & 0x0F
        size_code = (info >> 4) & 0x07
        array_flag = info & 0x80
        struct_name = None
        if ptype == PT_STRUCT:
            sidx, pos = ci(buf, pos); struct_name = names[sidx]
        if size_code in _SIZE_FIXED:
            size = _SIZE_FIXED[size_code]
        elif size_code == 5:
            size = buf[pos]; pos += 1
        elif size_code == 6:
            size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == PT_BOOL:
            props[name] = (ptype, bool(array_flag)); continue
        if array_flag:  # non-bool array element: skip the array index
            b = buf[pos]; pos += 1
            if b >= 0x80:
                pos += 1 if (b & 0xC0) == 0x80 else 3
        raw = buf[pos:pos + size]; pos += size
        if ptype == PT_BYTE:
            val = raw[0]
        elif ptype == PT_INT:
            val = int.from_bytes(raw, "little", signed=True)
        elif ptype == PT_FLOAT:
            val = struct.unpack("<f", raw)[0]
        elif ptype in (PT_OBJECT, PT_NAME, PT_OBJECT_LEGACY):
            val = ci(raw, 0)[0]
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
    e = pkg.exports[i0]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    end = so + sz
    props, pos = read_props(buf, so, end, pkg.names)
    fmt = props.get("Format", (PT_BYTE, 0))[1]
    pal = props.get("Palette", (PT_OBJECT, 0))[1]
    # Trailing: Mips = TArray<FMipmap>
    mipcount, pos = ci(buf, pos)
    mips = []
    for _ in range(mipcount):
        # FMipmap: a TLazyArray skip-offset (absolute file pos past the data) —
        # present only in Ar.Ver >= 63 (v68/69), ABSENT in v61 — then the byte data
        # (compact count + bytes), then USize/VSize/UBits/VBits.
        if pkg.version >= 63:
            skip = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        else:
            skip = None
        dcount, pos = ci(buf, pos)
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
    obj = TextureObj(pkg.names[e["nm"]], fmt, pal, mips, props)
    obj._body_end = pos  # for the EOF check
    obj._decl_end = end
    return obj


def decode_palette(pkg: Package, i0: int) -> list[tuple[int, int, int]]:
    e = pkg.exports[i0]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    _props, pos = read_props(buf, so, so + sz, pkg.names)
    count, pos = ci(buf, pos)
    cols = []
    for _ in range(count):
        r, g, b, _a = buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]
        pos += 4
        cols.append((r, g, b))
    if pos != so + sz:
        raise ValueError(f"palette body not at EOF: {pos} != {so + sz} (count={count})")
    return cols


def export_index_of_ref(pkg: Package, ref: int) -> int | None:
    """A local export object ref (>0) -> 0-based export index."""
    return ref - 1 if ref > 0 else None


def textures(pkg: Package) -> list[int]:
    return [i for i, e in enumerate(pkg.exports) if pkg.class_of_export(i) == "Texture"]


# --- minimal PNG writer (stdlib only) -----------------------------------------

def write_png(path: str, width: int, height: int, rgb: bytes):
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgb[y * width * 3:(y + 1) * width * 3]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)


def mip0_to_rgb(mip: Mip, palette: list[tuple[int, int, int]]) -> bytes:
    out = bytearray(mip.width * mip.height * 3)
    for i, idx in enumerate(mip.data):
        r, g, b = palette[idx]
        out[i * 3] = r; out[i * 3 + 1] = g; out[i * 3 + 2] = b
    return bytes(out)


def main(argv):
    path = argv[1]
    pkg = load_package(path)
    print(f"package {path}: version={pkg.version} names={len(pkg.names)} "
          f"imports={len(pkg.imports)} exports={len(pkg.exports)}")
    tex_idxs = textures(pkg)
    fmt_hist = {}
    for i in tex_idxs:
        try:
            t = decode_texture(pkg, i)
        except Exception as ex:
            print(f"  [FAIL] {pkg.names[pkg.exports[i]['nm']]}: {ex}")
            continue
        fmt_hist[t.fmt] = fmt_hist.get(t.fmt, 0) + 1
    print(f"textures={len(tex_idxs)}  format histogram="
          + ", ".join(f"{TEXF.get(k, k)}={v}" for k, v in sorted(fmt_hist.items())))

    if "--list" in argv:
        for i in tex_idxs[:40]:
            t = decode_texture(pkg, i)
            w, h = (t.mips[0].width, t.mips[0].height) if t.mips else (0, 0)
            print(f"  {t.name:30s} {TEXF.get(t.fmt, t.fmt):6s} {w}x{h} "
                  f"mips={len(t.mips)} pal={t.palette_ref}")
        return

    want = None
    if "--name" in argv:
        want = argv[argv.index("--name") + 1].lower()
    outdir = argv[argv.index("--out") + 1] if "--out" in argv else None

    for i in tex_idxs:
        t = decode_texture(pkg, i)
        if want and t.name.lower() != want:
            continue
        if t.fmt != 0:
            print(f"  {t.name}: format {TEXF.get(t.fmt, t.fmt)} (not P8, skipping decode)")
            continue
        pal_i0 = export_index_of_ref(pkg, t.palette_ref)
        if pal_i0 is None:
            print(f"  {t.name}: palette ref {t.palette_ref} not a local export")
            continue
        pal = decode_palette(pkg, pal_i0)
        m = t.mips[0]
        rgb = mip0_to_rgb(m, pal)
        print(f"  {t.name}: {m.width}x{m.height} P8 palette[{len(pal)}] "
              f"body_consumed_to_eof={t._body_end == t._decl_end}")
        if outdir:
            import os
            os.makedirs(outdir, exist_ok=True)
            p = os.path.join(outdir, f"{t.name}.png")
            write_png(p, m.width, m.height, rgb)
            print(f"    wrote {p}")
        if want:
            break


if __name__ == "__main__":
    main(sys.argv)
