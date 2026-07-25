"""ONE low-level reader for the shared UnrealEngine-1 package format.

`.u .dx .utx .uax .umx .unr` are all the same on-disk container (magic 0x9E2A83C1; header +
name/import/export tables; object bodies addressed by the export table). This module owns the
low-level parsing every use-case decoder builds on — the class schema + defaults (`uprops`),
and (follow-up migrations) the texture decoder (`utexture`) and the import-closure extractor
(`dxpkg`) — so no use-case or extension reimplements it (decisions.md 2026-07-18 10:02 §5,
"unified package core"; direction.md "One package-format core").

Owns:
- `read_compact_index` — the FCompactIndex signed variable-length int (canonical copy).
- `read_fstring` — a compact-length latin-1 string (v>=64 form).
- `Package` + `load_package` — header (v61/68/69) + name/import/export tables (moved here from
  `uprops`, which now imports them), plus object-ref helpers including full outer-chain
  qualification (`object_path`/`object_class_name`) for rendering `Class'Package.Name'` refs.
- `PropertyTag` + `read_property_tags` — the UE1 tagged-property list (name, info byte
  [type nibble | size code | bit7], optional struct name, optional array index, value span),
  generalizing the verified partial parser in `utexture._read_props` (same wire facts) while
  keeping raw value spans for per-kind decoding by the caller.

Every parse error raises `SchemaError` (the no-fallback contract): a malformed package is a
named error, never a bare struct.error/IndexError traceback.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

MAGIC = 0x9E2A83C1


class SchemaError(ValueError):
    """A package/class/property structure could not be parsed (bad magic, layout desync,
    unresolvable ref). Per the no-fallback contract this is a hard error, never a silent
    degrade. (Canonical home here; `uprops` re-exports it, so `uprops.SchemaError` remains
    the same class object for every existing caller.)"""


def read_compact_index(buf: bytes, pos: int) -> tuple[int, int]:
    """FCompactIndex: signed, variable length (UE1). Returns (value, next_pos)."""
    b = buf[pos]; pos += 1
    neg = b & 0x80
    val = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80) or shift >= 27:
                break
            shift += 7
    return (-val if neg else val), pos


def read_fstring(buf: bytes, pos: int) -> tuple[str, int]:
    """A v>=64 FString: compact byte length (including the terminating NUL), latin-1 bytes.
    Returns (text_without_nul, next_pos)."""
    length, pos = read_compact_index(buf, pos)
    if length < 0 or pos + length > len(buf):
        raise SchemaError(f"FString overruns buffer (len={length} at {pos})")
    s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
    return s, pos + length


def read_array_index(buf: bytes, pos: int) -> tuple[int, int]:
    """A property tag's static-array element index (present when the info byte's bit7 is set on
    a non-bool tag). UE1 packed form: 1 byte if <0x80; 2 bytes ((b0&0x3F)<<8|b1) if the top two
    bits are 10; 4 bytes ((b0&0x3F)<<24|…) if 11."""
    b0 = buf[pos]
    if b0 < 0x80:
        return b0, pos + 1
    if (b0 & 0xC0) == 0x80:
        return ((b0 & 0x3F) << 8) | buf[pos + 1], pos + 2
    return (((b0 & 0x3F) << 24) | (buf[pos + 1] << 16)
            | (buf[pos + 2] << 8) | buf[pos + 3]), pos + 4


@dataclass(frozen=True, kw_only=True)
class Package:
    name: str                       # the package stem (e.g. "Engine")
    version: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]   # (ClassPackage, ClassName, PackageIndex, ObjectName)
    exports: list[dict]                          # cls, sup, outer, nm, flags, ssize, soff
    buf: bytes

    def name_of_ref(self, idx: int) -> str | None:
        """Resolve a signed object reference: 0=None, >0 export idx-1, <0 import -idx-1.
        An OUT-OF-RANGE ref (a corrupt-but-loadable package — `load_package` checks only
        consume-to-EOF, not ref bounds) returns None, never a bare IndexError (review
        finding: byte-flip fuzzing reached `self.exports[idx-1]` with a garbage idx)."""
        if idx == 0:
            return None
        if idx > 0:
            if idx > len(self.exports):
                return None
            e = self.exports[idx - 1]
            return self.names[e["nm"]] if 0 <= e["nm"] < len(self.names) else None
        j = -idx - 1
        return self.names[self.imports[j][3]] if 0 <= j < len(self.imports) else None

    def import_package_of(self, import_idx0: int) -> str | None:
        """The owning package name of import `import_idx0` (0-based), by walking the outer chain
        (PackageIndex) to its root."""
        cur = self.imports[import_idx0]
        for _ in range(64):
            _cp, _cn, pi, on = cur
            if pi == 0:
                return self.names[on]
            if pi < 0:
                cur = self.imports[-pi - 1]
            else:
                return None
        return None

    def object_path(self, idx: int) -> str | None:
        """The fully-qualified dotted path of the object behind signed ref `idx`
        (`Package[.Group…].Name`), by walking the outer chain to the root. For an export the
        root package is THIS package. None for a 0 ref or an unresolvable chain."""
        if idx == 0:
            return None
        parts: list[str] = []
        if idx > 0:
            cur = idx
            for _ in range(64):
                if not (1 <= cur <= len(self.exports)):
                    return None                      # corrupt ref chain: None, not IndexError
                e = self.exports[cur - 1]
                nm = self.names[e["nm"]] if 0 <= e["nm"] < len(self.names) else None
                if nm is None:
                    return None
                parts.append(nm)
                outer = e["outer"]
                if outer == 0:
                    parts.append(self.name)
                    return ".".join(reversed(parts))
                if outer < 0:                    # export nested under an import (shouldn't happen)
                    imp_path = self.object_path(outer)
                    return None if imp_path is None else f"{imp_path}.{'.'.join(reversed(parts))}"
                cur = outer
            return None
        j = -idx - 1
        for _ in range(64):
            if not (0 <= j < len(self.imports)):
                return None                          # corrupt ref chain: None, not IndexError
            _cp, _cn, pi, on = self.imports[j]
            nm = self.names[on] if 0 <= on < len(self.names) else None
            if nm is None:
                return None
            parts.append(nm)
            if pi == 0:
                return ".".join(reversed(parts))
            if pi > 0:
                return None                      # import nested under an export: not a thing
            j = -pi - 1
        return None

    def object_class_name(self, idx: int) -> str | None:
        """The CLASS name of the object behind signed ref `idx` (`Texture`, `Class`, …) — for an
        import from its ClassName field, for an export by resolving its class ref (None ⇒ the
        root `Class`)."""
        if idx == 0:
            return None
        if idx > 0:
            if idx > len(self.exports):
                return None
            cls_ref = self.exports[idx - 1]["cls"]
            return "Class" if cls_ref == 0 else self.name_of_ref(cls_ref)
        j = -idx - 1
        if not (0 <= j < len(self.imports)):
            return None
        cn = self.imports[j][1]
        return self.names[cn] if 0 <= cn < len(self.names) else None


def load_package(path: str, *, name: str | None = None) -> Package:
    """Parse a package header + name/import/export tables. Any malformed/truncated input raises
    `SchemaError` (bad magic, a too-short header, a byte-parse overrun, or an export table that
    does not consume to EOF) — the no-fallback integrity gate, so a corrupt package never reaches
    a caller as a bare `struct.error`/`IndexError` traceback."""
    try:
        buf = open(path, "rb").read()
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    if len(buf) < 36:
        raise SchemaError(f"{path}: too small to be an Unreal package ({len(buf)} bytes)")
    try:
        return _parse_package(buf, path, name)
    except SchemaError:
        raise
    except (struct.error, ValueError, IndexError) as e:
        raise SchemaError(f"{path}: malformed package ({e})") from e


def _parse_package(buf: bytes, path: str, name: str | None) -> Package:
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != MAGIC:
        raise SchemaError(f"{path}: bad magic {tag:#010x} (not an Unreal package)")
    version = ver_l & 0xFFFF

    def read_name(pos: int) -> tuple[str, int]:
        if version < 64:                       # null-terminated string + u32 flags
            end = buf.index(b"\x00", pos)
            return buf[pos:end].decode("latin-1"), end + 1 + 4
        s, pos = read_fstring(buf, pos)
        return s, pos + 4                       # + u32 ObjectFlags

    names, pos = [], nameoff
    for _ in range(namecnt):
        s, pos = read_name(pos)
        names.append(s)
    imports, pos = [], impoff
    for _ in range(impcnt):
        cp, pos = read_compact_index(buf, pos)
        cn, pos = read_compact_index(buf, pos)
        pi = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        on, pos = read_compact_index(buf, pos)
        imports.append((cp, cn, pi, on))
    exports, pos = [], expoff
    for _ in range(expcnt):
        cls, pos = read_compact_index(buf, pos)
        sup, pos = read_compact_index(buf, pos)
        outer = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        nm, pos = read_compact_index(buf, pos)
        flv = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        ssize, pos = read_compact_index(buf, pos)
        soff = 0
        if ssize > 0:
            soff, pos = read_compact_index(buf, pos)
        exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm, flags=flv, ssize=ssize, soff=soff))
    # Integrity: the export loop must not OVERRUN the file (a truncated/desynced package reads a
    # compact past EOF → an earlier IndexError, or `pos > len` here). A small TRAILING remainder is
    # tolerated — some real DX packages carry a few bytes of padding after the export table (e.g.
    # `CaroneElevatorSet.u` has 1 trailing byte; UnrealEd and uedctl's own `utexture` parser both load
    # it fine). An exact `pos == len` gate false-rejected those as "partial schema".
    if pos > len(buf):
        raise SchemaError(f"{path}: export table overran EOF "
                          f"(cursor {pos} > size {len(buf)}) — truncated or desynced package")
    return Package(name=name or os.path.splitext(os.path.basename(path))[0], version=version,
                   names=names, imports=imports, exports=exports, buf=buf)


# ── the UE1 tagged-property list ─────────────────────────────────────────────────────────────
# Wire facts shared with (and originally verified by) `utexture._read_props`, byte-identical
# against UCC batchexport across the DX texture corpus: tag = FName compact (name; "None"
# terminates) + info byte [bits 0-3 type | bits 4-6 size code | bit 7 array-flag/bool-value] +
# (StructProperty only) struct-name compact + explicit size bytes per the size code + (non-bool,
# bit7 set) packed array index + `size` raw value bytes. Bool carries its VALUE in bit 7 and has
# no payload.

PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME = 1, 2, 3, 4, 5, 6
PT_STR_LEGACY, PT_CLASS_LEGACY, PT_ARRAY, PT_STRUCT = 7, 8, 9, 10
PT_VECTOR_LEGACY, PT_ROTATOR_LEGACY, PT_STR, PT_MAP, PT_FIXED = 11, 12, 13, 14, 15
_SIZE_FIXED = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}


@dataclass(frozen=True, kw_only=True)
class PropertyTag:
    name: str                       # property name (canonical name-table spelling)
    ptype: int                      # PT_* type nibble
    struct_name: str | None         # StructProperty's struct type name (e.g. "Vector")
    array_index: int                # static-array element index (0 for a scalar tag)
    bool_value: bool | None         # PT_BOOL: the value (bit 7); None otherwise
    raw: bytes                      # the raw value bytes (empty for PT_BOOL)


def read_property_tags(pkg: Package, pos: int, end: int) -> tuple[list[PropertyTag], int]:
    """Parse a tagged-property list starting at `pos`, up to the terminating "None" name.
    Returns (tags, pos_after_None). Raises `SchemaError` on any overrun/desync."""
    buf = pkg.buf
    if end > len(buf):
        raise SchemaError(f"tagged-property list bounds exceed the file ({end} > {len(buf)})")
    tags: list[PropertyTag] = []
    while True:
        if pos >= end:
            raise SchemaError(f"tagged-property list overran its bounds at {pos} (no None)")
        nidx, pos = read_compact_index(buf, pos)
        if not (0 <= nidx < len(pkg.names)):
            raise SchemaError(f"tagged-property name index {nidx} out of range at {pos}")
        name = pkg.names[nidx]
        if name == "None":
            return tags, pos
        info = buf[pos]; pos += 1
        ptype = info & 0x0F
        size_code = (info >> 4) & 0x07
        bit7 = bool(info & 0x80)
        struct_name = None
        if ptype == PT_STRUCT:
            sidx, pos = read_compact_index(buf, pos)
            struct_name = pkg.names[sidx] if 0 <= sidx < len(pkg.names) else None
        if size_code in _SIZE_FIXED:
            size = _SIZE_FIXED[size_code]
        elif size_code == 5:
            size = buf[pos]; pos += 1
        elif size_code == 6:
            size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == PT_BOOL:
            tags.append(PropertyTag(name=name, ptype=ptype, struct_name=None,
                                    array_index=0, bool_value=bit7, raw=b""))
            continue
        array_index = 0
        if bit7:
            array_index, pos = read_array_index(buf, pos)
        if pos + size > end:
            raise SchemaError(f"tagged property {name} value overruns its bounds "
                              f"({pos}+{size} > {end})")
        raw = buf[pos:pos + size]; pos += size
        tags.append(PropertyTag(name=name, ptype=ptype, struct_name=struct_name,
                                array_index=array_index, bool_value=None, raw=raw))
