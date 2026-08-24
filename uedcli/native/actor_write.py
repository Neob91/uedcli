"""Actor & helper-object body writers — StateFrame + FPropertyTag list + struct
value layouts + UPolys/FPoly.

Promoted from `prop_writer.py` (property tags, round-trip proven) and
`upolys_decode.py` (FPoly format, EOF-validated 6566/6587).  Section 30.2 pins the
StateFrame and struct layouts; the writer picks canonical size codes (the loader
accepts any valid FPropertyTag encoding — byte-match with the editor is not required).
"""
from __future__ import annotations

import struct

from .codec import write_ci, enc_i32, enc_f32, enc_u16

RF_HasStack = 0x02000000

PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_ARRAY, PT_STRUCT, PT_STR = \
    1, 2, 3, 4, 5, 6, 9, 10, 13


# --- StateFrame (§2.1) -----------------------------------------------------

def state_frame(class_ref: int) -> bytes:
    """The populated StateFrame every resting AActor carries: Node=StateNode=<class
    ref>, ProbeMask=~0, LatentAction=0, Offset=-1 (present because Node != 0)."""
    out = bytearray()
    out += write_ci(class_ref)                       # Node
    out += write_ci(class_ref)                       # StateNode
    out += struct.pack("<Q", 0xFFFFFFFFFFFFFFFF)     # ProbeMask
    out += struct.pack("<I", 0)                      # LatentAction
    out += write_ci(-1)                              # Offset = INDEX_NONE
    return bytes(out)


# --- property tags (§2.2) --------------------------------------------------

def _info(ptype: int, size_code: int, array_or_bool: bool) -> int:
    return (ptype & 0x0F) | ((size_code & 0x07) << 4) | (0x80 if array_or_bool else 0)


class Prop:
    """One property to encode.  Values are resolved to name/object refs by the caller
    (it holds the name table + object graph)."""

    def __init__(self, name: str, ptype: int, value, struct_name: str | None = None,
                 array_index: int | None = None):
        self.name = name
        self.ptype = ptype
        self.value = value
        self.struct_name = struct_name
        self.array_index = array_index


class StructValue:
    """A NON-atomic struct value as ordered member props. UE1 serializes a struct value member-wise
    (`SerializeBin`): each member's value bytes in DECLARATION order, no names, no `None` terminator
    (`upackage`/`uprops._decode_struct_bin_at` is the inverse). `members` are `Prop`s used for their
    (ptype, value, struct_name) only -- a member's own name/array_index carry no bytes (position is
    the identity). An atomic struct (Vector/Rotator/Scale/Color) stays raw bytes, not a StructValue."""

    def __init__(self, struct_name: str, members: list[Prop]):
        self.struct_name = struct_name
        self.members = members


class ArrayValue:
    """A dynamic-array (`TArray`) value: a compact-index element COUNT, then each element's value
    bytes in the inner element's `SerializeBin` form (same per-kind forms as a struct member).
    `elements` are `Prop`s whose ptype is the inner element kind. (Static `T foo[N]` arrays are NOT
    this -- each element is a separate tag with an array index.)"""

    def __init__(self, elements: list[Prop]):
        self.elements = elements


def _member_bytes(name_index, m: Prop) -> bytes:
    """One struct-member / array-element value in `SerializeBin` form -- NO tag, NO name. Note the
    in-struct BOOL is a full 0/1 byte (a top-level bool tag instead carries its value in info bit7
    with no payload)."""
    t = m.ptype
    if t == PT_BYTE:
        return bytes([int(m.value) & 0xFF])
    if t == PT_INT:
        return enc_i32(int(m.value))
    if t == PT_FLOAT:
        return enc_f32(float(m.value))
    if t == PT_BOOL:
        return bytes([1 if m.value else 0])
    if t == PT_NAME:
        return write_ci(name_index(m.value))
    if t == PT_OBJECT:
        return write_ci(int(m.value))                    # resolved to an int by the assembler
    if t == PT_STR:
        from .codec import write_fstring
        return write_fstring(m.value)
    if t == PT_STRUCT:
        return _struct_body(name_index, m.value) if isinstance(m.value, StructValue) else m.value
    if t == PT_ARRAY:
        return _array_body(name_index, m.value)
    raise ValueError(f"unsupported struct-member type {t}")


def _struct_body(name_index, sv: StructValue) -> bytes:
    return b"".join(_member_bytes(name_index, m) for m in sv.members)


def _array_body(name_index, av: ArrayValue) -> bytes:
    out = bytearray(write_ci(len(av.elements)))
    for e in av.elements:
        out += _member_bytes(name_index, e)
    return bytes(out)


def _size_code_and_bytes(n: int) -> tuple[int, bytes]:
    """Explicit-size encoding for a variable-length value: (size_code, size bytes), matching the
    reader's `size_code == 5/6/7` branches (1/2/4-byte little-endian length). A struct/array value
    routinely exceeds 255 bytes, so this is not optional."""
    if n < 0x100:
        return 5, bytes([n])
    if n < 0x10000:
        return 6, struct.pack("<H", n)
    return 7, struct.pack("<I", n)


def _value_body(name_index, p: Prop) -> bytes:
    """The value bytes of a variable-size tag (everything after the size + array index).
    Struct/array values arrive already serialized from `props.py` (which owns the schema)."""
    if p.ptype == PT_NAME:
        return write_ci(name_index(p.value))
    if p.ptype == PT_OBJECT:
        return write_ci(int(p.value))
    if p.ptype == PT_STR:
        from .codec import write_fstring
        return write_fstring(p.value)
    if p.ptype == PT_STRUCT:
        return _struct_body(name_index, p.value) if isinstance(p.value, StructValue) else p.value
    if p.ptype == PT_ARRAY:
        return _array_body(name_index, p.value) if isinstance(p.value, ArrayValue) else p.value
    raise ValueError(f"unsupported property type {p.ptype} for {p.name!r}")


def write_prop(name_index, p: Prop) -> bytes:
    """Encode one FPropertyTag, the exact byte-inverse of `upackage.read_property_tags`:
    name · info · [struct name if Struct] · size · [array index if set] · value.
    `name_index(str)->int` resolves names; Object values are already integer object-refs, Name
    values are strings resolved via name_index."""
    out = bytearray(write_ci(name_index(p.name)))
    arr = p.array_index is not None
    if p.ptype == PT_BOOL:
        out.append(_info(PT_BOOL, 0, bool(p.value)))
        return bytes(out)
    # Fixed-size types carry no explicit size byte (reader: size_code 0..4 -> _SIZE_FIXED), and the
    # array index (when present) follows the info byte directly.
    if p.ptype == PT_BYTE:
        out.append(_info(PT_BYTE, 0, arr)); _emit_array_index(out, p.array_index)
        out.append(p.value & 0xFF)
        return bytes(out)
    if p.ptype == PT_INT:
        out.append(_info(PT_INT, 2, arr)); _emit_array_index(out, p.array_index)
        out += enc_i32(p.value)
        return bytes(out)
    if p.ptype == PT_FLOAT:
        out.append(_info(PT_FLOAT, 2, arr)); _emit_array_index(out, p.array_index)
        out += enc_f32(p.value)
        return bytes(out)
    # Variable-size types: info · [struct name] · SIZE · [array index] · value, in THAT order. The
    # reader reads the size before the array index; emitting them backwards makes the engine read
    # the size byte as the element index and abort the load (a 12-byte `KeyPos` at index 1 ->
    # "Array bounds in KeyPos of Mover: 12/8").
    body = _value_body(name_index, p)
    size_code, size_bytes = _size_code_and_bytes(len(body))
    out.append(_info(p.ptype, size_code, arr))
    if p.ptype == PT_STRUCT:
        # the struct type name lives on the Prop (atomic, raw bytes) or the StructValue itself
        sname = p.struct_name or (p.value.struct_name if isinstance(p.value, StructValue) else None)
        out += write_ci(name_index(sname))
    out += size_bytes
    _emit_array_index(out, p.array_index)
    out += body
    return bytes(out)


def _emit_array_index(out: bytearray, idx) -> None:
    """Static-array element index byte(s).  For idx < 0x80 a single byte; the reader
    accepts 1 or 3 further bytes for larger indices (we keep indices small)."""
    if idx is None:
        return
    if idx < 0x80:
        out.append(idx)
    else:
        # two-byte form: 0x80 | (idx>>8), idx&0xff  (reader's (b&0xC0)==0x80 branch)
        out.append(0x80 | ((idx >> 8) & 0x3F))
        out.append(idx & 0xFF)


def write_props(name_index, props) -> bytes:
    out = bytearray()
    for p in props:
        out += write_prop(name_index, p)
    out += write_ci(name_index("None"))
    return bytes(out)


# --- struct value layouts (§2.2) -------------------------------------------

def struct_vector(x, y, z) -> bytes:
    return struct.pack("<fff", x, y, z)


def struct_rotator(pitch, yaw, roll) -> bytes:
    return struct.pack("<iii", pitch, yaw, roll)


def struct_scale(sx, sy, sz, sheer_rate=0.0, sheer_axis=5) -> bytes:
    return struct.pack("<ffff", sx, sy, sz, sheer_rate) + bytes([sheer_axis])


def struct_pointregion(zone_ref=0, i_leaf=-1, zone_number=0) -> bytes:
    return write_ci(zone_ref) + struct.pack("<i", i_leaf) + bytes([zone_number])


def struct_color(r, g, b, a=0) -> bytes:
    return bytes([r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF])


# --- UPolys / FPoly (§30.2, 10-native-upolys-fpoly) ------------------------

class FPoly:
    def __init__(self, verts, base=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 0.0),
                 texture_u=(0.0, 0.0, 0.0), texture_v=(0.0, 0.0, 0.0),
                 poly_flags=0, actor_ref=0, texture_ref=0, item_index=0,
                 i_link=-1, i_brush_poly=-1, pan_u=0, pan_v=0, item=None):
        self.verts = verts
        self.base = base
        self.normal = normal
        self.texture_u = texture_u
        self.texture_v = texture_v
        self.poly_flags = poly_flags
        self.actor_ref = actor_ref
        self.texture_ref = texture_ref
        self.item_index = item_index
        self.item = item                        # the poly's `Item=` name label, resolved at write
        self.i_link = i_link
        self.i_brush_poly = i_brush_poly
        self.pan_u = pan_u
        self.pan_v = pan_v


def write_fpoly(fp: FPoly) -> bytes:
    out = bytearray(write_ci(len(fp.verts)))
    out += struct.pack("<3f", *fp.base)
    out += struct.pack("<3f", *fp.normal)
    out += struct.pack("<3f", *fp.texture_u)
    out += struct.pack("<3f", *fp.texture_v)
    for v in fp.verts:
        out += struct.pack("<3f", *v)
    out += struct.pack("<i", fp.poly_flags)
    out += write_ci(fp.actor_ref)
    out += write_ci(fp.texture_ref)
    out += write_ci(fp.item_index)
    out += write_ci(fp.i_link)
    out += write_ci(fp.i_brush_poly)
    out += enc_u16(fp.pan_u)
    out += enc_u16(fp.pan_v)
    return bytes(out)


def write_upolys_body(name_index, polys) -> bytes:
    """UPolys body = property-None + INT Num + INT Max + Num * FPoly. Resolves each poly's `Item=`
    name label to its name-table index here, where the name table is available."""
    out = bytearray(write_ci(name_index("None")))
    out += struct.pack("<ii", len(polys), len(polys))
    for fp in polys:
        if fp.item is not None:
            fp.item_index = name_index(fp.item)
        out += write_fpoly(fp)
    return bytes(out)
