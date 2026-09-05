"""Byte-exact codec for UED22 (package v69) UnrealScript compiled bytecode.

A `UStruct` subclass (`UFunction`, `UState`, `UClass`) stores its compiled body as a stream of
`EExprToken` tokens: an opcode byte followed by operands whose shape the opcode fixes. There is NO
stored on-disk byte length for the stream — you walk it token by token. The engine keeps TWO cursors:
the on-disk byte position (object/name refs are variable-width `FCompactIndex`) and the in-memory
`ScriptSize` (those refs are 4 bytes in memory). `ScriptSize` counts the memory stream, so the walk
stops when the memory cursor reaches it.

This module extends the read-only skip walker (`uprops.ufield._walk_expr`, corpus-validated on 1914
UClass scripts) into a full DECODE + ENCODE that round-trips every real function/state byte-for-byte.

Token model (`Tok`): an opcode plus an ordered tuple of typed operand parts. Object refs and FName
refs are stored index-INDEPENDENTLY via a `resolve` callback so the same decoded tokens can be
re-emitted against any package's tables:

    resolve(kind, index) -> str            # decode side; kind in {"obj","name"}
    resolve_inv(kind, identity) -> index   # encode side; the exact inverse

Everything else (ints, floats, string/vector/rotator consts, jump offsets, native-call bytes) is kept
as verbatim bytes, so the encode is the exact inverse of the decode.

## `EExprToken` opcode table (v69) — operand shape per opcode

    0x00 LocalVariable      obj
    0x01 InstanceVariable   obj
    0x02 DefaultVariable    obj
    0x04 Return             expr
    0x05 Switch             u8(size) expr
    0x06 Jump               u16
    0x07 JumpIfNot          u16 expr
    0x08 Stop               -
    0x09 Assert             u16 expr
    0x0A Case               u16(nextOff; 0xFFFF=default) expr?   (no expr when default)
    0x0B Nothing            -
    0x0C LabelTable         {name u32}...  until name=="None"
    0x0D GotoLabel          expr
    0x0E EatString          expr
    0x0F Let                expr expr
    0x11 New                expr expr expr expr
    0x12 ClassContext       expr u16 u8 expr
    0x13 MetaCast           obj(class) expr
    0x14 LetBool            expr expr
    0x16 EndFunctionParms   -                (terminates a parm list)
    0x17 Self               -
    0x18 Skip               u16 expr
    0x19 Context            expr u16 u8 expr
    0x1A ArrayElement       expr(index) expr(base)
    0x1B VirtualFunction    name parms
    0x1C FinalFunction      obj(func) parms
    0x1D IntConst           i32
    0x1E FloatConst         f32
    0x1F StringConst        cstring (NUL-terminated latin-1)
    0x20 ObjectConst        obj
    0x21 NameConst          name
    0x22 RotationConst      3xi32 (12 bytes)
    0x23 VectorConst        3xf32 (12 bytes)
    0x24 ByteConst          u8
    0x25 IntZero            -
    0x26 IntOne             -
    0x27 True               -
    0x28 False              -
    0x29 NativeParm         obj
    0x2A NoObject           -
    0x2C IntConstByte       u8
    0x2D BoolVariable       expr
    0x2E DynamicCast        obj(class) expr
    0x2F Iterator           expr u16
    0x30 IteratorPop        -
    0x31 IteratorNext       -
    0x32 StructCmpEq        obj(struct) expr expr
    0x33 StructCmpNe        obj(struct) expr expr
    0x34 UnicodeStringConst u16 units until 0x0000
    0x36 StructMember       obj(property) expr
    0x38 GlobalFunction     name parms
    0x39..0x5F conversions  expr                 (one operand each)
    0x60..0x6F ExtendedNative  u8(low) parms     (native index = ((op-0x60)<<8)|low)
    0x70..0xFF native call     parms             (native index = op)

`parms` = a run of expressions terminated by (and including) an `EndFunctionParms` (0x16) token.

Native calls: a token byte >= 0x70 is a single-byte native call whose native index IS the byte. A
byte in 0x60..0x6F (`EX_ExtendedNative`) is followed by one more byte; the native index is
`((byte - 0x60) << 8) | next`. In both cases the arguments follow as expressions up to
`EX_EndFunctionParms`. The op byte(s) are kept verbatim, so the native index need not be recomputed
to re-emit.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Callable

from ..upackage import SchemaError, read_compact_index as _rci

EX_END_FUNCTION_PARMS = 0x16
EX_EXTENDED_NATIVE = 0x60
EX_FIRST_NATIVE = 0x70

_NONE_SUFFIX = re.compile(r"#\d+$")


def _is_none_name(ident: str) -> bool:
    """Whether a name identity denotes the null FName `None` (which terminates a LabelTable).
    `FName` is case-insensitive. Some packages carry many duplicate `None` name-table slots (e.g.
    `ubrowser.u` has 26), so a bijective resolver disambiguates them with a `#<index>` suffix; that
    suffix is stripped here. Reserved-name contract: a resolver must spell every null-FName slot as
    `None` (optionally `None#<n>`) and no real name may take that form."""
    return _NONE_SUFFIX.sub("", ident).casefold() == "none"

# resolve(kind, index) -> identity str ; resolve_inv(kind, identity) -> index
Resolve = Callable[[str, int], str]
ResolveInv = Callable[[str, str], int]


@dataclass(frozen=True)
class Tok:
    """One decoded token: its opcode byte and an ordered tuple of operand parts. Each part is a
    tuple whose first element tags it:
        ("raw", bytes)       verbatim bytes (const payloads, jump offsets, native low byte)
        ("obj", str)         object ref, as a resolve("obj", idx) identity
        ("name", str)        FName ref, as a resolve("name", idx) identity
        ("sub", Tok)         one nested expression
        ("parms", (Tok,...)) an argument run incl. its terminating EndFunctionParms token
    Parts are hashable/comparable, so two `Tok`s compare equal iff they encode identically."""
    op: int
    parts: tuple = ()


def write_compact_index(value: int) -> bytes:
    """UE1 `FCompactIndex` (signed, variable length), canonical minimal form — the exact inverse of
    `upackage.read_compact_index`. First byte: sign (0x80) + continue (0x40) + low 6 bits; each
    following byte: continue (0x80) + next 7 bits."""
    negative = value < 0
    n = -value if negative else value
    first = (0x80 if negative else 0) | (n & 0x3F)
    n >>= 6
    if n:
        first |= 0x40
    out = bytearray((first,))
    while n:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        out.append(b)
    return bytes(out)


def decode_script(buf: bytes, pos: int, script_size: int,
                  resolve: Resolve) -> tuple[list[Tok], int]:
    """Decode one function/state script stream. `pos` is the disk offset of the first token;
    `script_size` is the stored in-memory `ScriptSize`. Walks tokens until the memory cursor reaches
    `script_size` and returns (top-level tokens, disk position after the stream). `resolve(kind,
    index)` maps object/name compact refs to stable identities. Any unknown opcode or a memory-cursor
    overshoot raises `SchemaError` (no-fallback)."""
    toks: list[Tok] = []
    mem = 0
    while mem < script_size:
        tok, pos, mem = _decode_tok(buf, pos, mem, resolve)
        toks.append(tok)
    if mem != script_size:
        raise SchemaError(f"script decode desync: memory cursor {mem} != ScriptSize {script_size}")
    return toks, pos


def encode_script(toks: list[Tok], resolve_inv: ResolveInv) -> bytes:
    """Re-emit the on-disk bytes for a decoded script — the exact inverse of `decode_script`.
    `resolve_inv(kind, identity)` maps an identity back to its compact index."""
    return b"".join(_encode_tok(t, resolve_inv) for t in toks)


def _decode_tok(buf: bytes, pos: int, mem: int,
                resolve: Resolve) -> tuple[Tok, int, int]:
    op = buf[pos]; pos += 1; mem += 1
    parts: list[tuple] = []

    def raw(n: int) -> None:
        nonlocal pos, mem
        parts.append(("raw", bytes(buf[pos:pos + n]))); pos += n; mem += n

    def obj() -> None:
        nonlocal pos, mem
        v, pos = _rci(buf, pos); mem += 4
        parts.append(("obj", resolve("obj", v)))

    def name() -> None:
        nonlocal pos, mem
        v, pos = _rci(buf, pos); mem += 4
        parts.append(("name", resolve("name", v)))

    def sub() -> int:
        nonlocal pos, mem
        t, pos, mem = _decode_tok(buf, pos, mem, resolve)
        parts.append(("sub", t))
        return t.op

    def parms() -> None:
        nonlocal pos, mem
        run: list[Tok] = []
        while True:
            t, pos, mem = _decode_tok(buf, pos, mem, resolve)
            run.append(t)
            if t.op == EX_END_FUNCTION_PARMS:
                break
        parts.append(("parms", tuple(run)))

    if op >= EX_FIRST_NATIVE:                         # single-byte native call
        parms()
    elif op >= EX_EXTENDED_NATIVE:                    # extended native: one low byte, then parms
        raw(1); parms()
    elif 0x39 <= op <= 0x5F:                          # conversions: one operand
        sub()
    elif op in (0x00, 0x01, 0x02):                    # Local/Instance/Default Variable
        obj()
    elif op == 0x04:                                  # Return
        sub()
    elif op == 0x05:                                  # Switch: size byte + expr
        raw(1); sub()
    elif op == 0x06:                                  # Jump: u16
        raw(2)
    elif op == 0x07:                                  # JumpIfNot: u16 + expr
        raw(2); sub()
    elif op == 0x08:                                  # Stop
        pass
    elif op == 0x09:                                  # Assert: u16 + expr
        raw(2); sub()
    elif op == 0x0A:                                  # Case: u16; expr unless 0xFFFF (default)
        w = struct.unpack_from("<H", buf, pos)[0]
        raw(2)
        if w != 0xFFFF:
            sub()
    elif op == 0x0B:                                  # Nothing
        pass
    elif op == 0x0C:                                  # LabelTable: {name,u32} until "None"
        while True:
            v, pos = _rci(buf, pos); mem += 4
            ident = resolve("name", v)
            parts.append(("name", ident))
            parts.append(("raw", bytes(buf[pos:pos + 4]))); pos += 4; mem += 4
            if _is_none_name(ident):
                break
    elif op == 0x0D:                                  # GotoLabel
        sub()
    elif op == 0x0E:                                  # EatString
        sub()
    elif op in (0x0F, 0x14):                          # Let / LetBool
        sub(); sub()
    elif op == 0x11:                                  # New: 4 exprs
        sub(); sub(); sub(); sub()
    elif op in (0x12, 0x19):                          # ClassContext / Context: expr u16 u8 expr
        sub(); raw(3); sub()
    elif op == 0x13:                                  # MetaCast: class + expr
        obj(); sub()
    elif op == 0x16:                                  # EndFunctionParms
        pass
    elif op == 0x17:                                  # Self
        pass
    elif op == 0x18:                                  # Skip: u16 + expr
        raw(2); sub()
    elif op == 0x1A:                                  # ArrayElement: index + base
        sub(); sub()
    elif op == 0x1B:                                  # VirtualFunction: name + parms
        name(); parms()
    elif op == 0x1C:                                  # FinalFunction: func + parms
        obj(); parms()
    elif op in (0x1D, 0x1E):                          # IntConst / FloatConst
        raw(4)
    elif op == 0x1F:                                  # StringConst: NUL-terminated
        end = buf.index(b"\x00", pos)
        raw(end - pos + 1)
    elif op == 0x20:                                  # ObjectConst
        obj()
    elif op == 0x21:                                  # NameConst
        name()
    elif op in (0x22, 0x23):                          # RotationConst / VectorConst: 12 bytes
        raw(12)
    elif op == 0x24:                                  # ByteConst
        raw(1)
    elif op in (0x25, 0x26, 0x27, 0x28):             # IntZero/IntOne/True/False
        pass
    elif op == 0x29:                                  # NativeParm
        obj()
    elif op == 0x2A:                                  # NoObject
        pass
    elif op == 0x2C:                                  # IntConstByte
        raw(1)
    elif op == 0x2D:                                  # BoolVariable
        sub()
    elif op == 0x2E:                                  # DynamicCast: class + expr
        obj(); sub()
    elif op == 0x2F:                                  # Iterator: expr + u16
        sub(); raw(2)
    elif op in (0x30, 0x31):                          # IteratorPop / IteratorNext
        pass
    elif op in (0x32, 0x33):                          # StructCmpEq / StructCmpNe
        obj(); sub(); sub()
    elif op == 0x34:                                  # UnicodeStringConst: u16 units until 0
        start = pos
        while struct.unpack_from("<H", buf, pos)[0] != 0:
            pos += 2
        pos += 2
        n = pos - start
        parts.append(("raw", bytes(buf[start:pos]))); mem += n
    elif op == 0x36:                                  # StructMember: property + expr
        obj(); sub()
    elif op == 0x38:                                  # GlobalFunction: name + parms
        name(); parms()
    else:
        raise SchemaError(f"unknown script opcode {op:#04x} at disk offset {pos - 1}")
    return Tok(op=op, parts=tuple(parts)), pos, mem


def _encode_tok(tok: Tok, resolve_inv: ResolveInv) -> bytes:
    out = bytearray((tok.op,))
    for part in tok.parts:
        match part:
            case ("raw", b):
                out += b
            case ("obj", ident):
                out += write_compact_index(resolve_inv("obj", ident))
            case ("name", ident):
                out += write_compact_index(resolve_inv("name", ident))
            case ("sub", t):
                out += _encode_tok(t, resolve_inv)
            case ("parms", run):
                for t in run:
                    out += _encode_tok(t, resolve_inv)
            case _:
                raise SchemaError(f"bad token part {part!r}")
    return bytes(out)
