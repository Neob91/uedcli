"""Offline decoder for the typed information in a UE1 `.u` package's `UProperty`
serial bodies — the follow-on to name-only class-property extraction
(`2026-06-26-class-property-extraction.md`).

For each property export record (the `*Property` objects whose `Outer` is a
class), this reads the property's **serial body** (at the export's
`SerialOffset`/`SerialSize`) and recovers:

  - `array_dim`     — static-array size (`Foo[N]`), 1 for a scalar.
  - `property_flags`— the low-16 `CPF_*` flag bits (the high bits also exist on
                      disk but the low 16 carry the bits we care about).
  - `type_ref`      — the type-specific tail object reference (the body's last
                      compact):
        ByteProperty   -> its Enum object (None for a plain byte)
        ObjectProperty -> the referenced object class (e.g. Texture, Mesh)
        ClassProperty  -> the meta-class
        StructProperty -> the referenced Struct (e.g. Vector, Rotator)
        ArrayProperty  -> the INNER PROPERTY export (not the element type — see
                          `element_type_ref` for the one extra indirection)
        Int/Float/Str/Name/Bool/Pointer -> None (no type ref)
  - For ByteProperty whose `type_ref` is an Enum, `enum_values()` decodes the
    Enum object's body into its ordered tag names (e.g. ECameraTypes ->
    [CT_Predefined, ...]) — the data that enables enum-value validation.

GROUNDING (all confirmed against real bytes, see the spike .md):

  Property body header (UT-lineage v68 & v69), from the package's start byte:
    category : compact-index      the var's `var(Category)` FName index. For an
                                  uncategorized var it is `None` — which is NOT
                                  always index 0 / 1 byte: a package's name table
                                  can hold a `None` entry at a >63 index (e.g.
                                  core.u at 362), so this compact is 1 OR 2 bytes
                                  wide. It MUST be read as a compact, not assumed
                                  to be the fixed `00`. (Reading it wrong is why a
                                  hardcoded `combined @ offset 2` mis-decodes
                                  every body whose category compact isn't 1 byte.)
    0x00                          one pad/separator byte
    combined : uint32             a packed dword (little-endian):
                                    bits  0-15 : low PropertyFlags
                                    bits 16-23 : ArrayDim  (one byte, max 255;
                                                 0 means a scalar -> reported 1)
                                    bits 24-31 : high PropertyFlags
                                  So  array_dim = (combined >> 16) & 0xFF.
                                  (A naive `combined >> 16` is WRONG: it folds
                                  the bits-24-31 PropertyFlags into the dim and
                                  yields bogus values like 257 — the `& 0xFF`
                                  mask is load-bearing.)
    ...                           per-kind middle (ElementSize / RepOffset) whose
                                  exact widths vary; NOT needed for the typed decode
    type_ref : compact-index      the LAST compact index of the body. For the
                                  simple-ref kinds it IS the type:
                                    ByteProperty   -> the Enum (0 == plain byte)
                                    ObjectProperty -> the object class
                                    StructProperty -> the Struct
                                    ClassProperty  -> the meta-class
                                  For ArrayProperty the last compact is the INNER
                                  PROPERTY's own export, NOT its element type — to
                                  get the element type, decode_property() that
                                  inner export and read ITS type_ref (one extra
                                  indirection; see PropertyInfo.element_type_ref).

  Enum body (UEnum::Serialize), 100% byte-exact, cursor lands at EOF:
    None(compact) Next(compact) <one skipped compact> Count(compact)
    Count x Name(compact)        the ordered enum tag name indices

`array_dim = combined>>16` is validated against the known static arrays
(`MultiSkins[8]`, `Mover.KeyPos[8]`/`KeyRot[8]`); a scalar's high 16 bits are 0
and are reported as 1. The type ref read-from-end is validated against the
structural decode of every replicated (net) property (which lands byte-exact)
and against the decompiled `var` types.

Pure offline: parses `.u` bytes, never runs the editor. Reuses
`uedctl.dxpkg._read_compact_index`.
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass

# Import the production compact-index primitive.
try:
    from uedctl.dxpkg import _read_compact_index
except ModuleNotFoundError:  # running from the harness dir directly
    sys.path.insert(0, ".")
    from uedctl.dxpkg import _read_compact_index

_MAGIC = 0x9E2A83C1

# The closed set of UProperty subclasses (proven finite=11 by the name-only spike).
_PROPERTY_TYPES = frozenset({
    "ArrayProperty", "BoolProperty", "ByteProperty", "ClassProperty",
    "FloatProperty", "IntProperty", "NameProperty", "ObjectProperty",
    "PointerProperty", "StrProperty", "StructProperty",
})
# Kinds that carry a type-specific object reference as the body's final compact.
_KINDS_WITH_TYPE_REF = frozenset({
    "ByteProperty", "ObjectProperty", "StructProperty", "ClassProperty",
    "ArrayProperty",
})


@dataclass(frozen=True, kw_only=True)
class Package:
    version: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]  # (ClassPackage, ClassName, PackageIndex, ObjectName)
    exports: list[dict]                        # cls, sup, outer, nm, flags, ssize, soff
    buf: bytes
    size: int

    def name_of_ref(self, idx: int) -> str | None:
        """Resolve a signed object reference: 0=None, >0 export idx-1, <0 import -idx-1."""
        if idx == 0:
            return None
        if idx > 0:
            e = self.exports[idx - 1]
            return self.names[e["nm"]] if 0 <= e["nm"] < len(self.names) else None
        j = -idx - 1
        if 0 <= j < len(self.imports):
            return self.names[self.imports[j][3]]
        return None


def load_package(path: str) -> Package:
    buf = open(path, "rb").read()
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != _MAGIC:
        raise ValueError(f"{path}: bad magic {tag:#010x} (not an Unreal package)")
    version = ver_l & 0xFFFF

    def read_name(pos: int) -> tuple[str, int]:
        if version < 64:  # null-terminated string + u32 flags (no compact prefix)
            end = buf.index(b"\x00", pos)
            return buf[pos:end].decode("latin-1"), end + 1 + 4
        length, pos = _read_compact_index(buf, pos)
        s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
        return s, pos + length + 4

    names, pos = [], nameoff
    for _ in range(namecnt):
        s, pos = read_name(pos)
        names.append(s)

    imports, pos = [], impoff
    for _ in range(impcnt):
        cp, pos = _read_compact_index(buf, pos)
        cn, pos = _read_compact_index(buf, pos)
        pi = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        on, pos = _read_compact_index(buf, pos)
        imports.append((cp, cn, pi, on))

    exports, pos = [], expoff
    for _ in range(expcnt):
        cls, pos = _read_compact_index(buf, pos)
        sup, pos = _read_compact_index(buf, pos)
        outer = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        nm, pos = _read_compact_index(buf, pos)
        flv = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        ssize, pos = _read_compact_index(buf, pos)
        soff = 0
        if ssize > 0:
            soff, pos = _read_compact_index(buf, pos)
        exports.append(dict(cls=cls, sup=sup, outer=outer, nm=nm,
                            flags=flv, ssize=ssize, soff=soff))

    # The cursor-to-EOF integrity check (no-fallback contract): a layout error
    # on any record desyncs and misses EOF.
    if pos != len(buf):
        raise ValueError(f"{path}: export table did not consume to EOF "
                         f"(cursor {pos} != size {len(buf)})")
    return Package(version=version, names=names, imports=imports,
                   exports=exports, buf=buf, size=len(buf))


@dataclass(frozen=True, kw_only=True)
class PropertyInfo:
    name: str
    kind: str                     # e.g. "ByteProperty"
    array_dim: int                # static-array size; 1 for a scalar
    property_flags: int           # low-16 CPF_* bits
    type_ref: int                 # signed object ref of the type tail (0 == None)
    type_name: str | None         # resolved name of type_ref
    element_type_ref: int = 0     # ArrayProperty only: the element's type (one
    element_type_name: str | None = None  # extra indirection through the inner prop)


def _last_compact(buf: bytes, start: int, end: int) -> int:
    """The body's final compact index (the type tail for the typed kinds)."""
    pos, last = start, 0
    while pos < end:
        last, pos = _read_compact_index(buf, pos)
    return last


def decode_property(pkg: Package, export_index: int) -> PropertyInfo:
    """Decode one *Property export's serial body into its typed info.

    `export_index` is 1-based (the convention used by object references)."""
    e = pkg.exports[export_index - 1]
    kind = pkg.name_of_ref(e["cls"])
    if kind not in _PROPERTY_TYPES:
        raise ValueError(f"export {export_index} ({pkg.names[e['nm']]}) is not a "
                         f"property (class={kind})")
    so, sz = e["soff"], e["ssize"]
    if sz <= 0:  # a property with no serial body cannot be decoded — hard signal
        raise ValueError(f"property {pkg.names[e['nm']]} has empty serial body "
                         f"(ssize={sz}); cannot decode typed info")
    buf = pkg.buf
    # category(compact) + 1 pad byte + combined(u32). The category compact is 1
    # OR 2 bytes wide (a package may hold a `None` entry at a >63 index), so it
    # MUST be read, not assumed fixed-width.
    _category, p = _read_compact_index(buf, so)
    p += 1
    combined = struct.unpack_from("<I", buf, p)[0]
    array_dim = ((combined >> 16) & 0xFF) or 1   # bits 16-23; & 0xFF is load-bearing
    property_flags = combined & 0xFFFF
    type_ref = 0
    if kind in _KINDS_WITH_TYPE_REF:
        type_ref = _last_compact(buf, p + 4, so + sz)
    elem_ref, elem_name = 0, None
    if kind == "ArrayProperty" and type_ref > 0:
        # the last compact is the inner PROPERTY export; its element type needs
        # one more decode (the inner prop's own type_ref).
        try:
            inner = decode_property(pkg, type_ref)
            elem_ref, elem_name = inner.type_ref, inner.type_name
        except Exception:
            pass  # inner not a simple-ref kind (e.g. nested array) — leave None
    return PropertyInfo(
        name=pkg.names[e["nm"]],
        kind=kind,
        array_dim=array_dim,
        property_flags=property_flags,
        type_ref=type_ref,
        type_name=pkg.name_of_ref(type_ref),
        element_type_ref=elem_ref,
        element_type_name=elem_name,
    )


def enum_values(pkg: Package, enum_export_index: int) -> list[str]:
    """Decode a UEnum object's body into its ordered tag names. Byte-exact:
    None(c) Next(c) <skip 1 compact> Count(c) Count x Name(c); lands at EOF."""
    e = pkg.exports[enum_export_index - 1]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    p = so
    _none, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _skip, p = _read_compact_index(buf, p)
    count, p = _read_compact_index(buf, p)
    vals = []
    for _ in range(count):
        v, p = _read_compact_index(buf, p)
        vals.append(pkg.names[v])
    if p != so + sz:  # integrity: a bad layout would not land at EOF
        raise ValueError(f"enum {pkg.names[e['nm']]} body did not consume to EOF "
                         f"(cursor {p} != {so + sz})")
    return vals


def class_export_index(pkg: Package, class_name: str) -> int | None:
    """The 1-based export index of a UClass by name."""
    for i, e in enumerate(pkg.exports):
        if pkg.names[e["nm"]] == class_name and pkg.name_of_ref(e["cls"]) in (None, "Class"):
            return i + 1
    return None


def class_properties(pkg: Package, class_name: str) -> list[PropertyInfo]:
    """Own (not inherited) properties of a class, decoded with typed info.

    Properties = export records whose Outer is the class and whose type is a
    *Property (the name-only spike's rule), now decoded for type/array."""
    ci = class_export_index(pkg, class_name)
    if ci is None:
        raise ValueError(f"class not found: {class_name}")
    out = []
    for i, e in enumerate(pkg.exports):
        if e["outer"] == ci:
            kind = pkg.name_of_ref(e["cls"])
            if kind in _PROPERTY_TYPES:
                out.append(decode_property(pkg, i + 1))
    return out


def enum_index_by_name(pkg: Package, enum_name: str) -> int | None:
    for i, e in enumerate(pkg.exports):
        if pkg.names[e["nm"]] == enum_name and pkg.name_of_ref(e["cls"]) == "Enum":
            return i + 1
    return None


def enum_values_for_type_ref(pkg: Package, type_ref: int) -> list[str] | str:
    """Resolve a ByteProperty's enum type_ref to its value list.

    A positive ref is a LOCAL Enum export -> decode it. A NEGATIVE ref is a
    CROSS-PACKAGE import: the enum is defined in another package, so the body
    isn't here — return a marker telling the caller which package to load.
    (For validation, the schema builder must open that package and decode the
    enum there; this is the same cross-package walk class-property inheritance
    already does via the import table.)"""
    if type_ref == 0:
        return []  # plain byte, no enum
    if type_ref > 0:
        return enum_values(pkg, type_ref)
    # import: find its owning package by walking the import outer chain to root
    j = -type_ref - 1
    cp, cn, pi, on = pkg.imports[j]
    pkg_name = None
    cur = pkg.imports[j]
    for _ in range(64):
        _cp, _cn, _pi, _on = cur
        if _pi == 0:
            pkg_name = pkg.names[_on]
            break
        if _pi < 0:
            cur = pkg.imports[-_pi - 1]
        else:
            break
    return f"<imported enum {pkg.names[on]} from package {pkg_name}: load it to validate>"


if __name__ == "__main__":
    pkg = load_package(sys.argv[1] if len(sys.argv) > 1 else "uned/UED22/Engine.u")
    print(f"version={pkg.version} names={len(pkg.names)} exports={len(pkg.exports)}")
    for p in class_properties(pkg, "Actor"):
        extra = ""
        if p.kind == "ByteProperty" and p.type_ref > 0:
            extra = "  enum=" + ",".join(enum_values(pkg, p.type_ref))
        elif p.kind == "ArrayProperty" and p.element_type_name:
            extra = f"  element={p.element_type_name}"
        dim = f"[{p.array_dim}]" if p.array_dim != 1 else ""
        print(f"  {p.name}{dim} : {p.kind} -> {p.type_name}{extra}")
