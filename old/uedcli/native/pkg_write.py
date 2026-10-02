"""UE1 package container writer — from-scratch assembly + byte-exact round-trip.

Promoted from `spikes/2026-06-27-decontainerize-uedcli/harness/package_rw.py`
(round-trip proven byte-exact on real `.dx`) and extended with a FROM-SCRATCH writer
that synthesizes the header/name/import/export tables, lays the file out
(header -> names -> object bodies -> imports -> exports), records each body's
SerialOffset, and mints the v68/69 GUID + single generation record
(= final export/name counts) per section 30.3.

Layout (UE1):
  header: u32 magic | u32 version(low16=ver, high16=licensee) | u32 packageflags
          u32 namecount | u32 nameoff | u32 expcount | u32 expoff
          u32 impcount | u32 impoff
          [ver>=68] FGuid(16) + u32 gencount + gencount*(u32 exp, u32 name)
  name entry (ver>=64): ci(len incl NUL) + bytes + NUL + u32 flags
  import: ci ClassPackage, ci ClassName, i32 PackageIndex, ci ObjectName
  export: ci Class, ci Super, i32 Outer, ci Name, u32 Flags, ci SerialSize,
          (ci SerialOffset only if SerialSize>0)
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

from .codec import MAGIC, write_ci, read_ci


# --- name table ------------------------------------------------------------

class NameTable:
    """Deduping string table.  `index(s)` returns a stable 0-based index, adding on
    first use.  Name order is arbitrary (every ref is by index)."""

    def __init__(self) -> None:
        self._names: list[str] = []
        self._idx: dict[str, int] = {}
        self._flags: dict[int, int] = {}   # index -> accumulated RF_LoadFor* bits (see mark())

    def index(self, s: str) -> int:
        i = self._idx.get(s)
        if i is None:
            i = len(self._names)
            self._names.append(s)
            self._idx[s] = i
        return i

    def __len__(self) -> int:
        return len(self._names)

    @property
    def names(self) -> list[str]:
        return list(self._names)

    # Name-table entry flags: 0x10 | the union of RF_LoadFor* context bits over every site that
    # references the name -- a body reference contributes its export's own load bits (an edit-only
    # Camera/Brush body contributes LoadForEdit only), a table (import/export) reference all three.
    # The engine SKIPS loading objects whose NAME lacks the load bits, so an unmarked name defaults
    # to all three. A fixed set of engine-registered names additionally carries intrinsic upper
    # bits. All measured off the 2026-09-02 UED22 import goldens (constant across levels once the
    # reference-context union is accounted for).
    NAME_FLAGS = 0x00070010
    _INTRINSIC = {n.casefold(): 0x04000400 for n in
                  ("None", "Class", "Package", "Vector", "Rotator", "Outer", "Event")}
    _INTRINSIC.update({n.casefold(): 0x04000000 for n in
                       ("Camera", "Core", "Engine", "InitialState", "Message", "Sound", "Tag",
                        "Texture", "Title", "Trigger",
                        # native texture classes (Fire.dll/Engine registrations) -- measured off
                        # the OceanLab golden (WetTexture/FireTexture); siblings included as the
                        # same registration family
                        "WetTexture", "WaterTexture", "FireTexture", "IceTexture",
                        "WavyTexture", "ScriptedTexture", "FractalTexture")})

    def mark(self, index: int, load_bits: int) -> None:
        """OR `load_bits` (masked to 0x70000) into the name's accumulated load context."""
        self._flags[index] = self._flags.get(index, 0) | (load_bits & 0x70000)

    def apply_editor_intrinsics(self) -> None:
        """OR the engine-registered names' intrinsic upper bits into the accumulated flags --
        called by the LEVEL assembler only (a `.u` stub keeps the flat legacy flags)."""
        for i, s in enumerate(self._names):
            extra = self._INTRINSIC.get(s.casefold())
            if extra:
                self._flags[i] = self._flags.get(i, 0x70000) | extra

    def encode(self) -> bytes:
        out = bytearray()
        for i, s in enumerate(self._names):
            b = s.encode("latin-1") + b"\x00"
            out += write_ci(len(b)) + b + struct.pack("<I", 0x10 | self._flags.get(i, 0x70000))
        return bytes(out)


# --- table records ---------------------------------------------------------

@dataclass
class ImportRec:
    class_package: int   # name index of the class's package (e.g. "Core")
    class_name: int      # name index of the class name (e.g. "Class", "Package")
    package_index: int   # object-ref of the outer (0 for a root package)
    object_name: int     # name index of the imported object's name


@dataclass
class ExportRec:
    cls: int             # object-ref of the class (import<0 or export>0)
    super_ref: int       # object-ref of Super (0 for none)
    outer: int           # object-ref of Outer (0 = package root)
    name: int            # name index of the object's name
    flags: int           # RF_* object flags
    body: bytes          # the serialized object body
    serial_offset: int = 0  # filled at layout


# --- from-scratch package assembly ----------------------------------------

def build_package(*, version: int, licensee: int, package_flags: int,
                  names: NameTable, imports: list[ImportRec],
                  exports: list[ExportRec], guid: bytes | None = None) -> bytes:
    """Assemble a full package.  `exports` bodies are already serialized; this lays
    them out, records each SerialOffset, encodes the three tables, mints the GUID +
    single generation record, and back-patches the header offsets."""
    if guid is None:
        guid = os.urandom(16)
    if len(guid) != 16:
        raise ValueError(f"GUID must be 16 bytes, got {len(guid)}")

    names_b = names.encode()

    ver_l = (version & 0xFFFF) | ((licensee & 0xFFFF) << 16)
    # header length depends only on version (fixed table geometry)
    header_len = 36
    if version >= 68:
        header_len += 16 + 4 + 8 * 1   # guid + gencount + one FGenerationInfo
    else:
        header_len += 8                # heritage count+offset (legacy)

    nameoff = header_len
    dataoff = nameoff + len(names_b)

    # lay out bodies contiguously from dataoff, recording each SerialOffset
    bodies = bytearray()
    pos = dataoff
    for e in exports:
        e.serial_offset = pos if len(e.body) > 0 else 0
        bodies += e.body
        pos += len(e.body)

    imports_b = _enc_imports(imports)
    impoff = dataoff + len(bodies)
    expoff = impoff + len(imports_b)
    exports_b = _enc_exports(exports)

    # header
    out = bytearray()
    out += struct.pack("<9I", MAGIC, ver_l, package_flags,
                       len(names), nameoff, len(exports), expoff,
                       len(imports), impoff)
    if version >= 68:
        out += guid
        out += struct.pack("<I", 1)                       # one generation
        out += struct.pack("<II", len(exports), len(names))
    else:
        out += struct.pack("<II", 0, 0)                   # heritage (unused here)
    assert len(out) == header_len, (len(out), header_len)

    out += names_b + bodies + imports_b + exports_b
    return bytes(out)


def _enc_imports(imports: list[ImportRec]) -> bytes:
    out = bytearray()
    for im in imports:
        out += write_ci(im.class_package) + write_ci(im.class_name)
        out += struct.pack("<i", im.package_index) + write_ci(im.object_name)
    return bytes(out)


def _enc_exports(exports: list[ExportRec]) -> bytes:
    out = bytearray()
    for e in exports:
        out += write_ci(e.cls) + write_ci(e.super_ref)
        out += struct.pack("<i", e.outer) + write_ci(e.name)
        out += struct.pack("<I", e.flags) + write_ci(len(e.body))
        if len(e.body) > 0:
            out += write_ci(e.serial_offset)
    return bytes(out)


# --- re-lay an existing package with replaced bodies --------------------------

def _names_end(buf: bytes, version: int, namecnt: int, nameoff: int) -> int:
    pos = nameoff
    for _ in range(namecnt):
        if version < 64:
            pos = buf.index(b"\x00", pos) + 1
        else:
            length, pos = read_ci(buf, pos)
            pos += length
        pos += 4
    return pos


def relayout_package(pkg, *, bodies: dict[int, bytes], new_names: list[str] = ()) -> bytes:
    """Re-lay a parsed package (`upackage.Package`: `buf` + tables) with the export bodies in
    `bodies` (0-based export index -> new body) replaced and every other body, the header (GUID,
    generations), the name table and the import table kept byte-for-byte. `new_names` are appended
    to the name table (table-context flags); the header's name count and the last generation record
    follow. Export sizes/offsets are re-encoded — the canonical compact-index encoding the engine
    itself writes, so an unchanged package round-trips byte-identical."""
    buf = pkg.buf
    (_tag, ver_l, _flags, namecnt, nameoff, _expcnt, _expoff,
     _impcnt, impoff) = struct.unpack_from("<9I", buf, 0)
    version = ver_l & 0xFFFF
    out = bytearray(buf[:_names_end(buf, version, namecnt, nameoff)])
    for n in new_names:
        b = n.encode("latin-1") + b"\x00"
        out += write_ci(len(b)) + b + struct.pack("<I", NameTable.NAME_FLAGS)
    exports = []
    for i, e in enumerate(pkg.exports):
        body = bodies.get(i, buf[e["soff"]:e["soff"] + e["ssize"]])
        rec = ExportRec(cls=e["cls"], super_ref=e["sup"], outer=e["outer"], name=e["nm"],
                        flags=e["flags"], body=body, serial_offset=len(out) if body else 0)
        out += body
        exports.append(rec)
    new_impoff = len(out)
    out += _enc_imports([ImportRec(*im) for im in pkg.imports])
    new_expoff = len(out)
    out += _enc_exports(exports)
    struct.pack_into("<I", out, 12, namecnt + len(new_names))
    struct.pack_into("<I", out, 24, new_expoff)
    struct.pack_into("<I", out, 32, new_impoff)
    if new_names and version >= 68:
        gencount, = struct.unpack_from("<I", buf, 52)
        struct.pack_into("<I", out, 56 + 8 * (gencount - 1) + 4, namecnt + len(new_names))
    return bytes(out)


# --- reader (self-check re-parse) -----------------------------------------

@dataclass
class ParsedPackage:
    version: int
    licensee: int
    flags: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]
    exports: list[dict]
    guid: bytes | None
    buf: bytes

    def name_of_ref(self, ref: int) -> str | None:
        if ref == 0:
            return None
        if ref > 0:
            return self.names[self.exports[ref - 1]["nm"]]
        j = -ref - 1
        return self.names[self.imports[j][3]] if 0 <= j < len(self.imports) else None

    def class_of_export(self, i0: int) -> str | None:
        return self.name_of_ref(self.exports[i0]["cls"])


def parse_package(buf: bytes) -> ParsedPackage:
    """Full header/name/import/export parse; asserts the export table reaches EOF
    (the always-on self-check's structural spine)."""
    (tag, ver_l, flags, namecnt, nameoff, expcnt, expoff,
     impcnt, impoff) = struct.unpack_from("<9I", buf, 0)
    if tag != MAGIC:
        raise ValueError(f"bad package magic {tag:#010x}")
    version = ver_l & 0xFFFF
    licensee = (ver_l >> 16) & 0xFFFF
    pos = 36
    guid = None
    if version >= 68:
        guid = buf[pos:pos + 16]; pos += 16
        gencount, = struct.unpack_from("<I", buf, pos); pos += 4
        pos += 8 * gencount
    else:
        pos += 8

    names = []
    pos = nameoff
    for _ in range(namecnt):
        if version < 64:
            end = buf.index(b"\x00", pos)
            s = buf[pos:end].decode("latin-1"); pos = end + 1
        else:
            length, pos = read_ci(buf, pos)
            s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
            pos += length
        pos += 4                                    # flags
        names.append(s)

    imports = []
    pos = impoff
    for _ in range(impcnt):
        cp, pos = read_ci(buf, pos); cn, pos = read_ci(buf, pos)
        pi, = struct.unpack_from("<i", buf, pos); pos += 4
        on, pos = read_ci(buf, pos)
        imports.append((cp, cn, pi, on))

    exports = []
    pos = expoff
    for _ in range(expcnt):
        cls, pos = read_ci(buf, pos); sup, pos = read_ci(buf, pos)
        outer, = struct.unpack_from("<i", buf, pos); pos += 4
        nm, pos = read_ci(buf, pos)
        fl, = struct.unpack_from("<I", buf, pos); pos += 4
        ssize, pos = read_ci(buf, pos)
        soff = 0
        if ssize > 0:
            soff, pos = read_ci(buf, pos)
        exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm,
                            flags=fl, ssize=ssize, soff=soff))
    if pos != len(buf):
        raise ValueError(f"export table did not reach EOF: {pos} != {len(buf)}")
    return ParsedPackage(version, licensee, flags, names, imports, exports, guid, buf)
