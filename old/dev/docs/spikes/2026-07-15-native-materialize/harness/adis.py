"""Annotated disassembler for the UED22 DLLs.

Resolves CALL targets to export/symbol names (across a set of DLLs by their own
image base — but note inter-DLL calls go through the IAT), annotates absolute
memory operands with float constants and wide-string literals from the same
image, and demangles nothing (MSVC names are printed raw).

Usage:
    python dis.py <dll> <rva-hex> [len-hex]
    python dis.py Engine 0x1a5730 0x800
"""
import sys, struct, re
import pe

UED = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/uned/UED22"
DLLS = {
    "Engine": f"{UED}/Engine.dll",
    "Editor": f"{UED}/Editor.dll",
    "Core":   f"{UED}/core.dll",
}

def resolve(name):
    return DLLS.get(name, name)

# reverse export maps: RVA -> name, per dll
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
    # float
    f = struct.unpack("<f", b[:4])[0]
    if abs(f) < 1e7 and (abs(f) > 1e-6 or f == 0.0):
        out.append(f"f32={f:g}")
    # wide string
    m = re.match(rb'(?:[\x20-\x7e]\x00){2,}', b + (read(path, va+16, 48) or b""))
    if m:
        try:
            s = m.group().decode("utf-16le")
            out.append(f'w"{s}"')
        except Exception:
            pass
    # ascii string
    ma = re.match(rb'[\x20-\x7e]{3,}', b + (read(path, va+16, 48) or b""))
    if ma:
        out.append(f'a"{ma.group().decode("latin1")}"')
    return ("  ; " + " ".join(out)) if out else ""

def disone(path, rva, length):
    base = pe.image_base(path)
    rv = revmap(path)
    insns = pe.disasm(path, rva, length)
    for ins in insns:
        line = f"{ins.address:#010x}  {ins.mnemonic:<8}{ins.op_str}"
        ann = ""
        # call/jmp target name
        if ins.mnemonic in ("call", "jmp"):
            for op in ins.operands:
                if op.type == 1:  # imm
                    tgt = op.imm
                    tr = tgt - base
                    if tr in rv:
                        ann = f"   ; -> {rv[tr]}"
        for op in ins.operands:
            if op.type == 3:
                m = op.mem
                if m.base == 0 and m.index == 0 and m.disp:
                    va = m.disp & 0xffffffff
                    a = ann_mem(path, va)
                    if a:
                        ann += a
                        # if it's a data ptr into IAT, try resolve name
        print(line + ann)
        if ins.mnemonic in ("ret", "retn") and "nostop" not in sys.argv:
            break

if __name__ == "__main__":
    path = resolve(sys.argv[1])
    rva = int(sys.argv[2], 16)
    _b = pe.image_base(path)
    if rva >= _b:            # accept VA too
        rva -= _b
    length = int(sys.argv[3], 16) if len(sys.argv) > 3 and sys.argv[3] != "nostop" else 0x600
    disone(path, rva, length)
