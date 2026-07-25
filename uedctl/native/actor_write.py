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

PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STR, PT_STRUCT = \
    1, 2, 3, 4, 5, 6, 13, 10


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


def write_prop(name_index, p: Prop) -> bytes:
    """Encode a single tag.  `name_index(str)->int` resolves names; Object values are
    already integer object-refs, Name values are (name string) resolved via name_index."""
    out = bytearray(write_ci(name_index(p.name)))
    arr = p.array_index is not None
    if p.ptype == PT_BOOL:
        out.append(_info(PT_BOOL, 0, bool(p.value)))
        return bytes(out)
    if p.ptype == PT_BYTE:
        out.append(_info(PT_BYTE, 0, arr))
        _emit_array_index(out, p.array_index)
        out.append(p.value & 0xFF)
    elif p.ptype == PT_INT:
        out.append(_info(PT_INT, 2, arr)); _emit_array_index(out, p.array_index)
        out += enc_i32(p.value)
    elif p.ptype == PT_FLOAT:
        out.append(_info(PT_FLOAT, 2, arr)); _emit_array_index(out, p.array_index)
        out += enc_f32(p.value)
    elif p.ptype == PT_NAME:
        body = write_ci(name_index(p.value))
        out.append(_info(PT_NAME, 5, arr)); _emit_array_index(out, p.array_index)
        out.append(len(body)); out += body
    elif p.ptype == PT_OBJECT:
        body = write_ci(int(p.value))
        out.append(_info(PT_OBJECT, 5, arr)); _emit_array_index(out, p.array_index)
        out.append(len(body)); out += body
    elif p.ptype == PT_STR:
        from .codec import write_fstring
        body = write_fstring(p.value)
        out.append(_info(PT_STR, 5, arr)); _emit_array_index(out, p.array_index)
        out.append(len(body)); out += body
    elif p.ptype == PT_STRUCT:
        out.append(_info(PT_STRUCT, 5, arr))
        out += write_ci(name_index(p.struct_name))
        _emit_array_index(out, p.array_index)
        out.append(len(p.value)); out += p.value
    else:
        raise ValueError(f"unsupported property type {p.ptype} for {p.name!r}")
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
                 i_link=-1, i_brush_poly=-1, pan_u=0, pan_v=0):
        self.verts = verts
        self.base = base
        self.normal = normal
        self.texture_u = texture_u
        self.texture_v = texture_v
        self.poly_flags = poly_flags
        self.actor_ref = actor_ref
        self.texture_ref = texture_ref
        self.item_index = item_index
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
    """UPolys body = property-None + INT Num + INT Max + Num * FPoly."""
    out = bytearray(write_ci(name_index("None")))
    out += struct.pack("<ii", len(polys), len(polys))
    for fp in polys:
        out += write_fpoly(fp)
    return bytes(out)
