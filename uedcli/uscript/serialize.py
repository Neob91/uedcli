"""Serialize a resolved `CompiledPackage` (see `model.py`) to `.u` bytes.

Purely mechanical: the model is already linked (names/imports/exports ordered, every ref resolved),
so this only encodes fields. Container assembly (header, generation record, table layout, offset
back-patching) reuses the map-parity writer `native.pkg_write.build_package`. Per-object bodies are
encoded here from the structured model. Byte-parity with UCC is decided upstream by the compiler
that builds the model; this module's job is a faithful encode, pinned by `test_uscript_serialize`.
"""
from __future__ import annotations

from ..native.codec import enc_u16, enc_u32, enc_u64, write_ci, write_fstring
from ..native.pkg_write import ExportRec, ImportRec, NameTable, build_package
from .model import (ClassBody, CompiledPackage, ConstBody, EnumBody, Export, FunctionBody,
                    ObjectBody, PropertyBody, StructBody, TextBufferBody)

_FUNC_NET = 0x40   # FUNC_Net: adds a trailing u16 RepOffset


def _textbuffer_body(b: TextBufferBody, none_ref: int) -> bytes:
    return write_ci(none_ref) + enc_u32(b.pos) + enc_u32(b.top) + write_fstring(b.text)


def _property_body(b: PropertyBody, none_ref: int) -> bytes:
    out = (write_ci(none_ref) + write_ci(0) + write_ci(b.next_field)
           + enc_u32(b.array_dim) + enc_u32(b.property_flags) + write_ci(b.category))
    for ref in b.type_tail:               # subclass type-ref stream (Enum/PropertyClass/Struct/Inner)
        out += write_ci(ref)
    return out


def _enum_body(b: EnumBody, none_ref: int) -> bytes:
    out = write_ci(none_ref) + write_ci(0) + write_ci(b.next_field) + write_ci(len(b.values))
    for v in b.values:
        out += write_ci(v)
    return out


def _const_body(b: ConstBody, none_ref: int) -> bytes:
    return write_ci(none_ref) + write_ci(0) + write_ci(b.next_field) + write_fstring(b.value)


def _struct_body(b: StructBody, none_ref: int) -> bytes:
    return (write_ci(none_ref) + write_ci(b.super_field) + write_ci(b.next_field)
            + write_ci(0) + write_ci(b.children) + write_ci(b.friendly_name)
            + enc_u32(b.line) + enc_u32(b.text_pos) + enc_u32(b.script_size))


def _function_body(b: FunctionBody, none_ref: int) -> bytes:
    out = bytearray()
    out += write_ci(none_ref)
    out += write_ci(b.super_field)
    out += write_ci(b.next_field)
    out += write_ci(0)                    # ScriptText: a function holds none
    out += write_ci(b.children)
    out += write_ci(b.friendly_name)
    out += enc_u32(b.line) + enc_u32(b.text_pos) + enc_u32(b.script_size)
    out += b.script
    out += enc_u16(b.inative) + bytes((b.oper_precedence,)) + enc_u32(b.function_flags)
    if b.function_flags & _FUNC_NET:
        out += enc_u16(b.rep_offset)
    return bytes(out)


def _class_body(b: ClassBody) -> bytes:
    out = bytearray()
    out += write_ci(b.super_field)
    out += write_ci(b.next_field)
    out += write_ci(b.script_text)
    out += write_ci(b.children)
    out += write_ci(b.friendly_name)
    out += enc_u32(b.line) + enc_u32(b.text_pos)
    out += enc_u32(len(b.script)) + b.script
    out += enc_u64(b.probe_mask) + enc_u64(b.ignore_mask)
    out += enc_u16(b.label_table_offset) + enc_u32(b.state_flags)
    out += enc_u32(b.class_flags) + b.class_guid
    out += write_ci(len(b.dependencies))
    for d in b.dependencies:
        out += write_ci(d.cls) + enc_u32(d.deep) + enc_u32(d.script_text_crc)
    out += write_ci(len(b.package_imports))
    for n in b.package_imports:
        out += write_ci(n)
    out += write_ci(b.class_within)
    out += write_ci(b.class_config_name)
    out += b.default_props
    return bytes(out)


def _body_bytes(e: Export, none_ref: int) -> bytes:
    match e.body:
        case TextBufferBody():
            return _textbuffer_body(e.body, none_ref)
        case ClassBody():
            return _class_body(e.body)          # UClass skips the leading None terminator
        case PropertyBody():
            return _property_body(e.body, none_ref)
        case EnumBody():
            return _enum_body(e.body, none_ref)
        case ConstBody():
            return _const_body(e.body, none_ref)
        case StructBody():
            return _struct_body(e.body, none_ref)
        case FunctionBody():
            return _function_body(e.body, none_ref)
        case ObjectBody():
            return e.body.props + e.body.trailer     # UObject body: no leading None ref
        case _:
            raise NotImplementedError(f"no serializer for body {type(e.body).__name__}")


def serialize(pkg: CompiledPackage) -> bytes:
    """Encode `pkg` to `.u` bytes. `pkg.guid` is written verbatim (parity excludes it)."""
    names = NameTable()
    for n in pkg.names:
        i = names.index(n.text)
        # store the full flags directly; NameTable.encode ORs 0x10, so strip that bit here.
        names._flags[i] = n.flags & ~0x10
    # Every non-UClass body opens with the UObject tagged-prop list's "None" terminator — a NAME ref,
    # not a literal 0 (UCC can order the table with "None" off index 0).
    none_ref = next(i for i, n in enumerate(pkg.names) if n.text == "None")
    imports = [ImportRec(im.class_package, im.class_name, im.package_index, im.object_name)
               for im in pkg.imports]
    exports = [ExportRec(cls=e.cls, super_ref=e.super_ref, outer=e.outer, name=e.name,
                         flags=e.flags, body=_body_bytes(e, none_ref)) for e in pkg.exports]
    return build_package(version=pkg.version, licensee=pkg.licensee,
                         package_flags=pkg.package_flags, names=names,
                         imports=imports, exports=exports, guid=pkg.guid)
