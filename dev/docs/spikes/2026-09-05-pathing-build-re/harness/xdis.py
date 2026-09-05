#!/usr/bin/env python3
"""Annotated x86 disassembler for the UED22 (UT/469 lineage) and Deus Ex 1112fm engine DLLs.

Static only. Resolves CALL/JMP targets to export names (following the game DLL's `jmp rel32`
export thunks), IAT imports, vtable-slot calls; annotates memory/imm operands with float
constants and wide/ASCII string literals; prints the MSVC name demangled to `Class::method`.

Usage:
  xdis.py <dll> <target> [len-hex] [--nostop] [--raw]
    <dll>     ued-engine | ued-editor | ued-core | dx-engine | dx-editor | dx-core | dx-deusex | <path>
    <target>  hex RVA / VA, or an export-name substring (unique match required)
  xdis.py <dll> --exports <regex>          list matching exports (RVA, resolved thunk target)
  xdis.py <dll> --strings <regex> [ctx]    wide+ascii string table hits with ±ctx neighbours
  xdis.py <dll> --callers <target>         exports whose body (first 0x1000 bytes) CALLs target
  xdis.py <dll> --floats <rva> <n>         dump n floats at rva
"""
from __future__ import annotations

import re
from pathlib import Path
import struct
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ASSET_ROOT  # noqa: E402
MAIN = str(ASSET_ROOT)
DLLS = {
    "ued-engine": f"{MAIN}/uned/UED22/Engine.dll",
    "ued-editor": f"{MAIN}/uned/UED22/Editor.dll",
    "ued-core": f"{MAIN}/uned/UED22/core.dll",
    "dx-engine": f"{MAIN}/dev/games/deusex/System/Engine.dll",
    "dx-editor": f"{MAIN}/dev/games/deusex/System/Editor.dll",
    "dx-core": f"{MAIN}/dev/games/deusex/System/Core.dll",
    "dx-deusex": f"{MAIN}/dev/games/deusex/System/DeusEx.dll",
}

_cache: dict[str, pefile.PE] = {}


def load(path: str) -> pefile.PE:
    if path not in _cache:
        _cache[path] = pefile.PE(path, fast_load=False)
    return _cache[path]


def base(path: str) -> int:
    return load(path).OPTIONAL_HEADER.ImageBase


def read(path: str, va: int, n: int) -> bytes | None:
    pe = load(path)
    try:
        return pe.get_data(va - base(path), n)
    except Exception:
        return None


def demangle(n: str) -> str:
    if not n.startswith("?"):
        return n
    body = n[1:].split("@@")[0]
    parts = [p for p in body.split("@") if p]
    return "::".join(reversed(parts))


def follow_thunk(path: str, rva: int) -> int:
    """The DX DLLs export `jmp rel32` thunks (incremental-link ILT); return the real RVA."""
    b = read(path, base(path) + rva, 5)
    if b and b[0] == 0xE9:
        rel = struct.unpack("<i", b[1:5])[0]
        return rva + 5 + rel
    return rva


def exports(path: str) -> dict[str, int]:
    """name -> RVA of the real body (thunks followed)."""
    pe = load(path)
    out = {}
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if e.name:
                out[e.name.decode("latin1")] = follow_thunk(path, e.address)
    return out


def rev_exports(path: str) -> dict[int, str]:
    m: dict[int, str] = {}
    for n, r in exports(path).items():
        m.setdefault(base(path) + r, n)
    # also map the thunk addresses themselves
    pe = load(path)
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if e.name:
                m.setdefault(base(path) + e.address, e.name.decode("latin1"))
    return m


def iat(path: str) -> dict[int, str]:
    pe = load(path)
    out = {}
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode("latin1")
            for imp in entry.imports:
                if imp.name:
                    out[imp.address] = f"{dll}!{demangle(imp.name.decode('latin1'))}"
    return out


def string_at(path: str, va: int) -> str | None:
    b = read(path, va, 96)
    if not b:
        return None
    m = re.match(rb"(?:[\x20-\x7e]\x00){3,}", b)
    if m:
        return 'w"' + m.group().decode("utf-16le") + '"'
    m = re.match(rb"[\x20-\x7e]{4,}", b)
    if m:
        return 'a"' + m.group().decode("latin1") + '"'
    return None


def ann_addr(path: str, va: int) -> str:
    b0 = base(path)
    if not (b0 <= va < b0 + 0x1000000):
        return ""
    out = []
    b = read(path, va, 8)
    if b and len(b) >= 4:
        f = struct.unpack("<f", b[:4])[0]
        if f == 0.0 or 1e-6 < abs(f) < 1e7:
            out.append(f"f32={f!r}")
        if len(b) == 8:
            d = struct.unpack("<d", b)[0]
            if 1e-6 < abs(d) < 1e7:
                out.append(f"f64={d!r}")
        i = struct.unpack("<i", b[:4])[0]
        if -100000 < i < 100000:
            out.append(f"i32={i}")
    s = string_at(path, va)
    if s:
        out.append(s)
    return " ".join(out)


def disasm(path: str, rva: int, length: int, nostop: bool = False, raw: bool = False) -> None:
    pe = load(path)
    b0 = base(path)
    code = pe.get_data(rva, length)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    rv = rev_exports(path)
    ia = iat(path)
    name = rv.get(b0 + rva)
    print(f"; {path.split('/')[-1]} rva={rva:#x} va={b0 + rva:#x} {demangle(name) if name else ''}")
    for ins in md.disasm(code, b0 + rva):
        line = f"{ins.address:#010x}  {ins.mnemonic:<7} {ins.op_str}"
        ann = []
        if ins.mnemonic in ("call", "jmp") or ins.mnemonic.startswith("j"):
            op = ins.operands[0]
            if op.type == 2:  # imm
                tgt = op.imm & 0xFFFFFFFF
                if tgt in rv:
                    ann.append("-> " + demangle(rv[tgt]))
                elif ins.mnemonic == "call":
                    # follow a thunk at the call target
                    t = follow_thunk(path, tgt - b0) + b0
                    if t in rv:
                        ann.append("-> " + demangle(rv[t]))
            elif op.type == 3:
                m = op.mem
                if m.base == 0 and m.disp in ia:
                    ann.append("-> " + ia[m.disp & 0xFFFFFFFF])
                elif m.base != 0 and ins.mnemonic == "call":
                    ann.append(f"[vcall slot {m.disp // 4}]")
        if not raw:
            for op in ins.operands:
                if op.type == 3 and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp:
                    va = op.mem.disp & 0xFFFFFFFF
                    if va in ia:
                        ann.append("iat:" + ia[va])
                    else:
                        a = ann_addr(path, va)
                        if a:
                            ann.append(f"[{va:#x}] {a}")
                elif op.type == 2 and ins.mnemonic not in ("call", "jmp") and not ins.mnemonic.startswith("j"):
                    iv = op.imm & 0xFFFFFFFF
                    if iv >= 0x10000:
                        f = struct.unpack("<f", struct.pack("<I", iv))[0]
                        if 1e-6 < abs(f) < 1e6:
                            ann.append(f"imm asf32={f!r}")
                        s = string_at(path, iv) if b0 <= iv < b0 + 0x1000000 else None
                        if s:
                            ann.append(s)
                        elif iv in rv:
                            ann.append("&" + demangle(rv[iv]))
        print(line + ("   ; " + "  ".join(ann) if ann else ""))
        if ins.mnemonic in ("ret", "retn") and not nostop:
            break


def resolve_target(path: str, tok: str) -> int:
    try:
        v = int(tok, 16)
        return v - base(path) if v >= base(path) else follow_thunk(path, v)
    except ValueError:
        pass
    ex = exports(path)
    hits = [(n, r) for n, r in ex.items() if tok in n or tok in demangle(n)]
    if len(hits) != 1:
        sys.exit(f"target {tok!r}: {len(hits)} export matches: " + ", ".join(demangle(n) for n, _ in hits[:20]))
    return hits[0][1]


def wide_strings(path: str):
    data = load(path).__data__
    runs = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){3,}", data):
        runs.append((m.start(), m.group().decode("utf-16le")))
    for m in re.finditer(rb"[\x20-\x7e]{5,}", data):
        runs.append((m.start(), "a:" + m.group().decode("latin1")))
    runs.sort()
    return runs


def main(argv: list[str]) -> None:
    path = DLLS.get(argv[0], argv[0])
    if argv[1] == "--exports":
        pat = re.compile(argv[2], re.I)
        pe = load(path)
        for e in sorted(pe.DIRECTORY_ENTRY_EXPORT.symbols, key=lambda e: e.address):
            if e.name and pat.search(e.name.decode("latin1")):
                n = e.name.decode("latin1")
                print(f"{e.address:#08x} -> {follow_thunk(path, e.address):#08x}  {demangle(n)}   {n}")
        return
    if argv[1] == "--strings":
        pat = re.compile(argv[2], re.I)
        ctx = int(argv[3]) if len(argv) > 3 else 0
        runs = wide_strings(path)
        for i, (off, s) in enumerate(runs):
            if pat.search(s):
                for j in range(max(0, i - ctx), min(len(runs), i + ctx + 1)):
                    print(f"{'>' if j == i else ' '} {runs[j][0]:#08x} {runs[j][1]}")
                if ctx:
                    print("--")
        return
    if argv[1] == "--callers":
        tgt = base(path) + resolve_target(path, argv[2])
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        pe = load(path)
        for n, r in sorted(exports(path).items(), key=lambda x: x[1]):
            try:
                code = pe.get_data(r, 0x1000)
            except Exception:
                continue
            for ins in md.disasm(code, base(path) + r):
                if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
                    t = int(ins.op_str, 16)
                    if t == tgt or follow_thunk(path, t - base(path)) + base(path) == tgt:
                        print(f"{r:#08x} {demangle(n)}  @ {ins.address:#x}")
                        break
                if ins.mnemonic in ("ret", "retn"):
                    break
        return
    if argv[1] == "--floats":
        rva = int(argv[2], 16)
        n = int(argv[3])
        b = read(path, base(path) + rva, 4 * n)
        for i in range(n):
            print(f"{rva + 4 * i:#x}: f32={struct.unpack('<f', b[4 * i:4 * i + 4])[0]!r} i32={struct.unpack('<i', b[4 * i:4 * i + 4])[0]}")
        return
    rva = resolve_target(path, argv[1])
    length = 0x800
    for a in argv[2:]:
        if not a.startswith("--"):
            length = int(a, 16)
    disasm(path, rva, length, nostop="--nostop" in argv, raw="--raw" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
