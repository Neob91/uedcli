"""The UField family: the decoder for one `*Property` export, an `Enum`'s value names, a `Struct`'s
ordered members, and the `UStruct::SerializeExpr` bytecode walk a UClass body has to be replayed
through before its defaults can be reached."""
from __future__ import annotations

import struct

from ..upackage import Package, SchemaError, read_compact_index as _read_compact_index
from .base import (CPF_NET, PROPERTY_TYPES, Prop, _KINDS_WITH_TYPE_REF, _last_compact,
                   _safe_name, _schema_guard)


def _decode_property(pkg: Package, export_index1: int, owner_fqcn: str, *, _inner: bool = False) -> Prop:
    """Decode one *Property export (1-based index) into typed info. The v68/v69 UProperty body layout
    is (RE'd byte-exact 2026-07-18 — empirical decode + `Core.dll UProperty::Serialize` @ 0x10164fd0,
    see `unrealed/class-schema.md`):

        [UObject None terminator: compact] [UField.SuperField: compact] [UField.Next: compact]
        [ArrayDim: u32] [PropertyFlags: u32] [Category: FName compact]
        [RepOffset: u16 — ONLY if PropertyFlags & CPF_NET] [subclass type tail: compact ref(s)]

    (The OLD decode read the leading None-terminator AS "category" and mis-offset the header, so
    `property_flags` was garbage for every prop and `array_dim` was wrong for any static array whose
    size didn't fit the `>>16 & 0xFF` hack — see the doc. This reads the true fields.)"""
    e = pkg.exports[export_index1 - 1]
    kind = pkg.name_of_ref(e["cls"])
    so, sz = e["soff"], e["ssize"]
    if sz <= 0:
        raise SchemaError(f"property {pkg.names[e['nm']]} has empty serial body (ssize={sz})")
    buf = pkg.buf
    _none, p = _read_compact_index(buf, so)         # UObject empty tagged-prop-list terminator (==0)
    _super, p = _read_compact_index(buf, p)         # UField.SuperField
    _next, p = _read_compact_index(buf, p)          # UField.Next
    array_dim = struct.unpack_from("<I", buf, p)[0] or 1; p += 4
    property_flags = struct.unpack_from("<I", buf, p)[0]; p += 4
    cat_idx, p = _read_compact_index(buf, p)        # UProperty.Category (FName)
    category = pkg.names[cat_idx] if 0 < cat_idx < len(pkg.names) else None
    if property_flags & CPF_NET:                     # a 2-byte RepOffset sits before the type tail
        p += 2
    type_ref = _last_compact(buf, p, so + sz) if kind in _KINDS_WITH_TYPE_REF else 0
    # A ByteProperty's LOCAL enum values, decoded eagerly so a Prop carries everything actor-prop
    # validation needs (resolve_class_properties discards the loaded Package). An imported enum
    # (type_ref < 0) or a plain byte (0) yields () — validation then can't enumerate, so accepts.
    enum_names = tuple(enum_values(pkg, type_ref)) if kind == "ByteProperty" else ()
    # An ArrayProperty's type tail is its `Inner` UProperty ref — decode that property too, so the
    # ELEMENT kind is available (see `Prop.array_inner`). `_inner` stops the recursion at one level:
    # UnrealScript cannot declare `array<array<T>>`, so a nested array ref is corruption, and an
    # Inner that (corruptly) points back at itself would otherwise recurse forever.
    inner = None
    if kind == "ArrayProperty" and not _inner and 0 < type_ref <= len(pkg.exports):
        if pkg.name_of_ref(pkg.exports[type_ref - 1]["cls"]) in PROPERTY_TYPES:
            inner = _decode_property(pkg, type_ref, owner_fqcn, _inner=True)
    return Prop(name=pkg.names[e["nm"]], kind=kind, array_dim=array_dim,
                property_flags=property_flags, type_ref=type_ref,
                type_name=pkg.name_of_ref(type_ref), owner=owner_fqcn,
                enum_value_names=enum_names, category=category, array_inner=inner)


@_schema_guard
def enum_values(pkg: Package, type_ref: int) -> list[str]:
    """The ordered value names of a ByteProperty's enum `type_ref`. A positive ref is a LOCAL Enum
    export (decoded byte-exact); a 0 ref is a plain byte (→ []). A negative (cross-package import)
    ref needs the owning package loaded — callers that want its values resolve that package and
    decode the enum there; here it returns [] with the owner discoverable via `import_package_of`."""
    if type_ref <= 0:
        return []
    e = pkg.exports[type_ref - 1]
    if pkg.name_of_ref(e["cls"]) != "Enum":
        return []
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _skip, p = _read_compact_index(buf, p)
    count, p = _read_compact_index(buf, p)
    vals = []
    for _ in range(count):
        v, p = _read_compact_index(buf, p)
        vals.append(pkg.names[v])
    if p != e["soff"] + e["ssize"]:
        raise SchemaError(f"enum {pkg.names[e['nm']]} body did not consume to EOF")
    return vals


# ══ Class DEFAULT VALUES — the SerializeExpr walker + UClass-tail defaults decoder ═══════════
# (spec in board item `materialize-post-verify-fails-when-the-trunk` §5.2; direction/packages.md 2026-07-18 10:02 §5.)
#
# A UClass export body is:
#   [UField.SuperField][UField.Next]                       (compacts; NO leading None terminator —
#                                                           UE1 skips the UObject tagged list for
#                                                           UClass objects and serializes the class
#                                                           DEFAULTS at the tail instead)
#   [UStruct: ScriptText][Children][FriendlyName][Line:u32][TextPos:u32][ScriptSize:u32][script…]
#   [UState: ProbeMask:u64][IgnoreMask:u64][LabelTableOffset:u16][StateFlags:u32]
#   [UClass: ClassFlags:u32][ClassGuid:16B][Dependencies:TArray{Class compact,Deep u32,CRC u32}]
#   [PackageImports:TArray{name compact}][ClassWithin: compact][ClassConfigName: name compact]
#   [DEFAULTS: tagged-property list, "None"-terminated]  → must land EXACTLY at soff+ssize.
#
# The script bytecode has NO on-disk byte length — `ScriptSize` counts the IN-MEMORY size, and
# names/object refs are compact on disk but 4 bytes in memory, so the walker tracks both cursors
# and replays `UStruct::SerializeExpr` token by token. Unknown opcode / any desync raises
# `SchemaError` (no-fallback). Validated by the corpus-integrity test: every class in every game
# `.u` must walk clean and land the defaults list exactly at EOF.

_EX_END_FUNCTION_PARMS = 0x16


def _walk_expr(pkg: Package, pos: int, mem: int) -> tuple[int, int, int]:
    """Replay one SerializeExpr: returns (pos, mem, token). Token semantics per the UE1 v68
    opcode set; disk/memory sizes differ only for compacts (name/object refs: compact on disk,
    4 in memory)."""
    buf = pkg.buf
    tok = buf[pos]; pos += 1; mem += 1

    def obj() -> None:                              # object ref: compact disk / 4 mem
        nonlocal pos, mem
        _v, pos = _read_compact_index(buf, pos)
        mem += 4

    def name() -> None:                             # FName: compact disk / 4 mem
        nonlocal pos, mem
        _v, pos = _read_compact_index(buf, pos)
        mem += 4

    def fixed(n: int) -> None:                      # n bytes, same on disk and in memory
        nonlocal pos, mem
        pos += n; mem += n

    def expr() -> int:
        nonlocal pos, mem
        pos, mem, t = _walk_expr(pkg, pos, mem)
        return t

    def parms() -> None:                            # function args until EX_EndFunctionParms
        while expr() != _EX_END_FUNCTION_PARMS:
            pass

    if tok >= 0x70:                                 # single-byte native call index
        parms()
    elif tok >= 0x60:                               # extended native: high nibble + 1 byte
        fixed(1)
        parms()
    elif 0x39 <= tok <= 0x5F:                       # conversion tokens: 1 operand each
        expr()
    elif tok in (0x00, 0x01, 0x02):                 # Local/Instance/DefaultVariable
        obj()
    elif tok == 0x04:                               # Return
        expr()
    elif tok == 0x05:                               # Switch: size byte + expr
        fixed(1); expr()
    elif tok == 0x06:                               # Jump: u16
        fixed(2)
    elif tok == 0x07:                               # JumpIfNot: u16 + expr
        fixed(2); expr()
    elif tok == 0x08:                               # Stop
        pass
    elif tok == 0x09:                               # Assert: u16 line + expr
        fixed(2); expr()
    elif tok == 0x0A:                               # Case: u16 next; 0xFFFF == default (no expr)
        w = struct.unpack_from("<H", buf, pos)[0]
        fixed(2)
        if w != 0xFFFF:
            expr()
    elif tok == 0x0B:                               # Nothing
        pass
    elif tok == 0x0C:                               # LabelTable: {name,u32} until "None"
        while True:
            v, pos2 = _read_compact_index(buf, pos)
            pos = pos2; mem += 4
            nm = pkg.names[v] if 0 <= v < len(pkg.names) else None
            fixed(4)
            if nm == "None":
                break
    elif tok == 0x0D:                               # GotoLabel
        expr()
    elif tok == 0x0E:                               # EatString
        expr()
    elif tok in (0x0F, 0x14):                       # Let / LetBool
        expr(); expr()
    elif tok == 0x11:                               # New: 4 exprs
        expr(); expr(); expr(); expr()
    elif tok == 0x12:                               # ClassContext: expr + u16 + byte + expr
        expr(); fixed(3); expr()
    elif tok == 0x13:                               # MetaCast: class + expr
        obj(); expr()
    elif tok == 0x16:                               # EndFunctionParms
        pass
    elif tok == 0x17:                               # Self
        pass
    elif tok == 0x18:                               # Skip: u16 + expr
        fixed(2); expr()
    elif tok == 0x19:                               # Context: expr + u16 + byte + expr
        expr(); fixed(3); expr()
    elif tok == 0x1A:                               # ArrayElement: index expr + base expr
        expr(); expr()
    elif tok == 0x1B:                               # VirtualFunction: name + parms
        name(); parms()
    elif tok == 0x1C:                               # FinalFunction: func + parms
        obj(); parms()
    elif tok == 0x1D:                               # IntConst
        fixed(4)
    elif tok == 0x1E:                               # FloatConst
        fixed(4)
    elif tok == 0x1F:                               # StringConst: NUL-terminated
        end = buf.index(b"\x00", pos)
        n = end - pos + 1
        fixed(n)
    elif tok == 0x20:                               # ObjectConst
        obj()
    elif tok == 0x21:                               # NameConst
        name()
    elif tok in (0x22, 0x23):                       # RotationConst / VectorConst: 12 bytes
        fixed(12)
    elif tok == 0x24:                               # ByteConst
        fixed(1)
    elif tok in (0x25, 0x26, 0x27, 0x28):           # IntZero/IntOne/True/False
        pass
    elif tok == 0x29:                               # NativeParm
        obj()
    elif tok == 0x2A:                               # NoObject
        pass
    elif tok == 0x2C:                               # IntConstByte
        fixed(1)
    elif tok == 0x2D:                               # BoolVariable
        expr()
    elif tok == 0x2E:                               # DynamicCast: class + expr
        obj(); expr()
    elif tok == 0x2F:                               # Iterator: expr + u16
        expr(); fixed(2)
    elif tok in (0x30, 0x31):                       # IteratorPop / IteratorNext
        pass
    elif tok in (0x32, 0x33):                       # StructCmpEq/Ne: struct + expr + expr
        obj(); expr(); expr()
    elif tok == 0x34:                               # UnicodeStringConst: u16 units until 0
        while struct.unpack_from("<H", buf, pos)[0] != 0:
            fixed(2)
        fixed(2)
    elif tok == 0x36:                               # StructMember: property + expr
        obj(); expr()
    elif tok == 0x38:                               # GlobalFunction: name + parms
        name(); parms()
    else:
        raise SchemaError(f"unknown script opcode {tok:#04x} at {pos - 1} in {pkg.name}")
    return pos, mem, tok


def _skip_script(pkg: Package, pos: int, script_size: int) -> int:
    """Walk the whole script blob (in-memory size `script_size`), returning the disk position
    after it. A desync (memory cursor overshoots) raises `SchemaError`."""
    mem = 0
    while mem < script_size:
        pos, mem, _t = _walk_expr(pkg, pos, mem)
    if mem != script_size:
        raise SchemaError(f"script walk desync in {pkg.name}: memory cursor {mem} != "
                          f"ScriptSize {script_size}")
    return pos


def _field_next(pkg: Package, export_index1: int) -> int:
    """A UProperty export's `UField.Next` ref (the Children linked-list pointer): the 3rd compact
    of its body ([None][SuperField][Next]…)."""
    e = pkg.exports[export_index1 - 1]
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _sup, p = _read_compact_index(buf, p)
    nxt, _p = _read_compact_index(buf, p)
    return nxt


def struct_children_ref(pkg: Package, struct_index1: int) -> int:
    """A Struct export's `UStruct.Children` head ref. Struct body (class `Struct` ≠ `Class`, so
    the leading UObject None terminator IS present): [None][SuperField][Next][ScriptText]
    [Children]…"""
    e = pkg.exports[struct_index1 - 1]
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _sup, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _st, p = _read_compact_index(buf, p)
    children, _p = _read_compact_index(buf, p)
    return children


def find_struct_export(pkg: Package, struct_name: str) -> int | None:
    """1-based export index of a `Struct` export by name (case-insensitive)."""
    want = struct_name.casefold()
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) == "Struct":
            nm = _safe_name(pkg, e["nm"])
            if nm is not None and nm.casefold() == want:
                return i + 1
    return None


@_schema_guard
def struct_members(pkg: Package, struct_index1: int, *, owner: str,
                   _seen: set | None = None) -> list[Prop]:
    """The ORDERED member properties of a Struct export — the `Children` linked list walked via
    each member's `UField.Next` (declaration order; the export-table order is NOT reliable, and
    the in-struct binary layout depends on this order). A struct with a super-struct contributes
    its super's members FIRST (UE1 in-memory layout), recursively."""
    if not (1 <= struct_index1 <= len(pkg.exports)):
        raise SchemaError(f"struct export index {struct_index1} out of range in {pkg.name} "
                          f"(wrong resolving package?)")
    seen = _seen if _seen is not None else set()
    if struct_index1 in seen:                        # corrupt self/cyclic super ref (fuzz finding)
        raise SchemaError(f"cyclic super-struct chain in {pkg.name} ({owner})")
    seen.add(struct_index1)
    e = pkg.exports[struct_index1 - 1]
    out: list[Prop] = []
    sup_ref = e["sup"]
    if sup_ref > 0:                                  # super-struct members lead (local supers only
        out.extend(struct_members(pkg, sup_ref, owner=owner, _seen=seen))  # DX: Plane ext. Vector
    elif sup_ref < 0:
        raise SchemaError(f"imported super-struct not supported for {owner}")
    cur = struct_children_ref(pkg, struct_index1)
    for _ in range(256):
        if cur == 0:
            return out
        if cur < 0:
            raise SchemaError(f"struct child is an import in {owner}")
        ee = pkg.exports[cur - 1]
        if pkg.name_of_ref(ee["cls"]) in PROPERTY_TYPES:
            out.append(_decode_property(pkg, cur, owner))
        cur = _field_next(pkg, cur)
    raise SchemaError(f"struct member chain did not terminate in {owner}")
