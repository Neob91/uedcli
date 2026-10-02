"""UE1 wire primitives shared by every native serializer.

FCompactIndex (signed variable-length int) + fixed-width little-endian scalars +
FString.  Promoted from the proven spike harnesses (package_rw.py / umodel_serialize.py /
level_roundtrip.py) so the native package is self-contained (no sys.path into spikes/).

Object references are compact indices with the UE1 sign convention:
  v == 0  -> null / None
  v  > 0  -> export  index (v - 1), 0-based
  v  < 0  -> import  index (-v - 1), 0-based
`ref_export`/`ref_import` build them; `read_ci`/`write_ci` are the codec.
"""
from __future__ import annotations

import struct

MAGIC = 0x9E2A83C1


# --- FCompactIndex ---------------------------------------------------------

def read_ci(buf: bytes, pos: int) -> tuple[int, int]:
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


def write_ci(v: int) -> bytes:
    """Canonical-minimal FCompactIndex, matching the engine writer."""
    neg = v < 0
    v = -v if neg else v
    out = bytearray()
    b0 = (0x80 if neg else 0) | (v & 0x3F)
    v >>= 6
    if v:
        b0 |= 0x40
    out.append(b0)
    while v:
        b = v & 0x7F
        v >>= 7
        if v:
            b |= 0x80
        out.append(b)
    return bytes(out)


# --- object-ref helpers ----------------------------------------------------

def ref_export(idx0: int) -> int:
    """0-based export index -> object-ref value."""
    return idx0 + 1


def ref_import(idx0: int) -> int:
    """0-based import index -> object-ref value."""
    return -(idx0 + 1)


def deref(v: int) -> tuple[str, int] | None:
    """Object-ref value -> ('export'|'import', idx0) or None for null."""
    if v == 0:
        return None
    if v > 0:
        return ("export", v - 1)
    return ("import", -v - 1)


# --- fixed-width scalars ---------------------------------------------------

def enc_i32(v: int) -> bytes:
    return struct.pack("<i", v)


def enc_u32(v: int) -> bytes:
    return struct.pack("<I", v)


def enc_u16(v: int) -> bytes:
    return struct.pack("<H", v)


def enc_u8(v: int) -> bytes:
    return struct.pack("<B", v & 0xFF)


def enc_u64(v: int) -> bytes:
    return struct.pack("<Q", v)


def enc_f32(v: float) -> bytes:
    return struct.pack("<f", v)


def enc_f32x3(t) -> bytes:
    return struct.pack("<fff", *t)


def enc_f32x4(t) -> bytes:
    return struct.pack("<ffff", *t)


# --- FString (UE1) ---------------------------------------------------------

def write_fstring(s: str) -> bytes:
    """ANSI FString: ci(len incl NUL) + bytes + NUL.  Empty -> ci(0), no bytes."""
    if s == "":
        return write_ci(0)
    b = s.encode("latin-1") + b"\x00"
    return write_ci(len(b)) + b


def read_fstring(buf: bytes, pos: int) -> tuple[str, int]:
    length, pos = read_ci(buf, pos)
    if length < 0:
        n = (-length) * 2
        s = buf[pos:pos + n].decode("utf-16-le", "replace").split("\x00", 1)[0]
        return s, pos + n
    s = buf[pos:pos + length].split(b"\x00", 1)[0].decode("latin-1")
    return s, pos + length
