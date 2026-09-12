"""ONE low-level reader for the shared UnrealEngine-1 package format.

`.u .dx .utx .uax .umx .unr` are all the same on-disk container (magic 0x9E2A83C1; header +
name/import/export tables; object bodies addressed by the export table). This module owns the
low-level parsing every use-case decoder builds on — the class schema + defaults (`uprops`),
and (follow-up migrations) the texture decoder (`utexture`) and the import-closure extractor
(`dxpkg`) — so no use-case or extension reimplements it (direction/packages.md 2026-07-18 10:02 §5,
"unified package core"; dev/docs/direction/packages.md).

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
import sys
from dataclasses import dataclass, field

MAGIC = 0x9E2A83C1


class SchemaError(ValueError):
    """A package/class/property structure could not be parsed (bad magic, layout desync,
    unresolvable ref). Per the no-fallback contract this is a hard error, never a silent
    degrade. (Canonical home here; `uprops` re-exports it, so `uprops.SchemaError` remains
    the same class object for every existing caller.)"""


@dataclass(frozen=True, kw_only=True)
class NameEntry:
    """One name-table row as the wire format actually stores it: text plus the real engine's
    per-entry EObjectFlags bits (RF_Native = 0x04000000, RF_HighlightName = 0x400 — see
    USCRIPT-COMPILER.md). Named for the concept, not the engine's own `FNameEntry` struct: this
    module already drops Epic's struct-prefix convention (`Package`, `PropertyTag`), and the
    real `FNameEntry` also carries a runtime-only hash/next-pointer this never touches."""
    text: str
    flags: int


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
    # Rust-decoder metadata — optional for a hand-built test fixture that skips `_parse_package`.
    name_entries: list[NameEntry] = field(default_factory=list)
    licensee: int = 0
    name_offset: int = 0
    name_count: int = 0
    import_offset: int = 0
    import_count: int = 0
    export_offset: int = 0
    export_count: int = 0
    guid_range: tuple[int, int] | None = None

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


_LOAD_CACHE: dict[tuple[str, str], tuple[int, int, "Package"]] = {}  # (realpath, name) -> (size, mtime_ns, Package)


def load_package(path: str, *, name: str | None = None) -> Package:
    """Parse a package header + name/import/export tables. Any malformed/truncated input raises
    `SchemaError` (bad magic, a too-short header, a byte-parse overrun, or an export table that
    does not consume to EOF) — the no-fallback integrity gate, so a corrupt package never reaches
    a caller as a bare `struct.error`/`IndexError` traceback.

    Memoized in-process by (realpath, resolved name, size, mtime_ns): the same package is loaded
    repeatedly within one render (e.g. one actor class's package loaded once per actor instance
    sharing that class) — profiled at 3,404 calls for 108 distinct packages rendering one photo.
    `name` is keyed too, not just `realpath`: `resolve_class_properties` calls this with `name`
    derived from a class's FQCN (e.g. `"Fire"` from `Fire.Flame`), which can legitimately differ
    in casing from the file's own stem (e.g. `fire.u` -> `"fire"`) across different callers of the
    SAME file — caching by realpath alone served one caller's requested name to another (a real,
    reproduced bug: found via `test_schema_cache.py`'s golden test failing only when
    `test_proceduraltex.py` ran first and resolved `Fire.Flame`, poisoning `fire.u`'s cache entry
    with `Package.name="Fire"` before a later `name="fire"` request). A second, on-disk tier
    (`pkg_cache.py`) survives across separate CLI invocations.

    The no-name fallback is derived from `path` (as given), not `realpath`: `_parse_package` derives
    `Package.name` the same way from its own `where=path` argument, so the two must agree — deriving
    one from `path` and the other from `realpath` would silently diverge whenever `path`'s last
    component is a symlink pointing at a differently-named file."""
    realpath = os.path.realpath(path)
    resolved_name = name if name is not None else os.path.splitext(os.path.basename(path))[0]
    cache_key = (realpath, resolved_name)
    try:
        st = os.stat(realpath)
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    cached = _LOAD_CACHE.get(cache_key)
    if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
        return cached[2]
    from . import pkg_cache  # local import: pkg_cache imports Package/NameEntry from here
    disk_hit = pkg_cache.read(realpath, resolved_name, st.st_size, st.st_mtime_ns)
    if disk_hit is not None:
        _LOAD_CACHE[cache_key] = (st.st_size, st.st_mtime_ns, disk_hit)
        return disk_hit
    try:
        buf = open(realpath, "rb").read()
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    pkg = parse_package_bytes(buf, where=path, name=name)
    _LOAD_CACHE[cache_key] = (st.st_size, st.st_mtime_ns, pkg)
    pkg_cache.write(realpath, resolved_name, st.st_size, st.st_mtime_ns, pkg)
    return pkg


def parse_package_bytes(buf: bytes, *, where: str, name: str | None = None) -> Package:
    """`load_package` over in-memory bytes; `where` names the source in errors."""
    if len(buf) < 36:
        raise SchemaError(f"{where}: too small to be an Unreal package ({len(buf)} bytes)")
    try:
        return _parse_package(buf, where, name)
    except SchemaError:
        raise
    except (struct.error, ValueError, IndexError) as e:
        raise SchemaError(f"{where}: malformed package ({e})") from e


def _parse_package(buf: bytes, path: str, name: str | None) -> Package:
    from .native_ext import import_native
    uedcli_native = import_native()
    try:
        (version, licensee, flags, names_with_flags, imports, exports_raw,
         (name_offset, name_count), (import_offset, import_count),
         (export_offset, export_count), guid_range) = uedcli_native.parse_package_raw(buf)
    except uedcli_native.PackageError as e:
        raise SchemaError(f"{path}: {e}") from e
    interned_names_with_flags = [(sys.intern(text), flags_) for text, flags_ in names_with_flags]
    names = [text for text, _flags in interned_names_with_flags]
    name_entries = [NameEntry(text=text, flags=flags_) for text, flags_ in interned_names_with_flags]
    exports = [
        dict(cls=cls, sup=sup, outer=outer, nm=nm, flags=flv, ssize=ssize, soff=soff)
        for cls, sup, outer, nm, flv, ssize, soff in exports_raw
    ]
    return Package(
        name=sys.intern(name or os.path.splitext(os.path.basename(path))[0]), version=version,
        names=names, imports=imports, exports=exports, buf=buf,
        name_entries=name_entries, licensee=licensee,
        name_offset=name_offset, name_count=name_count,
        import_offset=import_offset, import_count=import_count,
        export_offset=export_offset, export_count=export_count,
        guid_range=guid_range,
    )


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
    span: tuple[int, int] = (0, 0)  # [start, end) of the WHOLE tag in the package buffer


def read_property_tags(pkg: Package, pos: int, end: int) -> tuple[list[PropertyTag], int]:
    """Parse a tagged-property list starting at `pos`, up to the terminating "None" name.
    Returns (tags, pos_after_None). Raises `SchemaError` on any overrun/desync."""
    from .native_ext import import_native
    uedcli_native = import_native()
    try:
        raw_tags, next_pos = uedcli_native.read_property_tags_raw(pkg.buf, pos, end, pkg.names)
    except uedcli_native.PackageError as e:
        raise SchemaError(str(e)) from e
    tags = [
        PropertyTag(name=sys.intern(name), ptype=ptype,
                    struct_name=(sys.intern(struct_name) if struct_name is not None else None),
                    array_index=array_index, bool_value=bool_value, raw=bytes(raw), span=span)
        for name, ptype, struct_name, array_index, bool_value, raw, span in raw_tags
    ]
    return tags, next_pos
