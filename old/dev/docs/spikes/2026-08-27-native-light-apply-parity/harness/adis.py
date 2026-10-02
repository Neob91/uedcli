"""Annotated disassembler for the UED22 DLLs (repo-relative paths).

Same idea as the 2026-07-15 spike's adis.py, but resolves the DLL directory from
this file's location instead of a hardcoded absolute path, and never stops at the
first `ret` (a compiled function has many).

Usage:
    python adis.py <Editor|Engine|Core|Render> <rva-or-va-hex> [len-hex]
"""
import os
import re
import struct
import sys

import pe

UED = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", "uned", "UED22")
)
DLLS = {
    "Engine": f"{UED}/Engine.dll",
    "Editor": f"{UED}/Editor.dll",
    "Core": f"{UED}/core.dll",
    "Render": f"{UED}/render.dll",
}


def resolve(name):
    return DLLS.get(name, name)


_rev = {}


def revmap(path):
    if path not in _rev:
        m = {}
        for n, rva in pe.exports(path).items():
            m.setdefault(rva, n)
        _rev[path] = m
    return _rev[path]


def read(path, va, n):
    try:
        return pe.read_at_va(path, va, n)
    except Exception:
        return None


def ann_mem(path, va):
    base = pe.image_base(path)
    if not (base <= va < base + 0x400000):
        return ""
    b = read(path, va, 16)
    if not b:
        return ""
    out = []
    f = struct.unpack("<f", b[:4])[0]
    if abs(f) < 1e7 and (abs(f) > 1e-6 or f == 0.0):
        out.append(f"f32={f:g}")
    d = struct.unpack("<d", b[:8])[0]
    if abs(d) < 1e7 and (abs(d) > 1e-6 or d == 0.0):
        out.append(f"f64={d:g}")
    m = re.match(rb"(?:[\x20-\x7e]\x00){3,}", b + (read(path, va + 16, 48) or b""))
    if m:
        try:
            out.append('w"%s"' % m.group().decode("utf-16le"))
        except Exception:
            pass
    ma = re.match(rb"[\x20-\x7e]{4,}", b + (read(path, va + 16, 48) or b""))
    if ma:
        out.append('a"%s"' % ma.group().decode("latin1"))
    return ("  ; " + " ".join(out)) if out else ""


def disone(path, rva, length):
    base = pe.image_base(path)
    rv = revmap(path)
    for ins in pe.disasm(path, rva, length):
        line = f"{ins.address:#010x}  {ins.mnemonic:<10}{ins.op_str}"
        ann = ""
        if ins.mnemonic.startswith(("call", "jmp", "j")):
            for op in ins.operands:
                if op.type == 1:
                    tr = op.imm - base
                    if tr in rv:
                        ann = f"   ; -> {rv[tr]}"
        for op in ins.operands:
            if op.type == 3:
                m = op.mem
                if m.base == 0 and m.index == 0 and m.disp:
                    a = ann_mem(path, m.disp & 0xFFFFFFFF)
                    if a:
                        ann += a
        print(line + ann)


if __name__ == "__main__":
    path = resolve(sys.argv[1])
    rva = int(sys.argv[2], 16)
    b = pe.image_base(path)
    if rva >= b:
        rva -= b
    length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x600
    disone(path, rva, length)
