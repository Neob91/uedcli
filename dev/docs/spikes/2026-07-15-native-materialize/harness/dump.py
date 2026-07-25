"""Disassemble a function, annotate call targets (export/import), float mem operands,
and immediate constants that look like float32 when reinterpreted. Static only.

Usage: dump.py <dll> <rva-hex> [len-hex] [--nostop]
"""
import sys, struct
import pe

p = sys.argv[1]
rva = int(sys.argv[2], 16)
length = int(sys.argv[3], 16) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 0x400
base = pe.image_base(p)
nostop = "--nostop" in sys.argv

exp = {base + r: n for n, r in pe.exports(p).items()}
iat = {}
pp = pe.load(p)
if hasattr(pp, "DIRECTORY_ENTRY_IMPORT"):
    for entry in pp.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode("latin1")
        for imp in entry.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode('latin1')}"

def short(n):
    if n.startswith("?"):
        parts = n[1:].split("@@")[0].split("@")
        return "::".join(reversed([x for x in parts if x]))
    return n

def tryf(va):
    try:
        return struct.unpack("<f", pe.read_at_va(p, va, 4))[0]
    except Exception:
        return None

insns = pe.disasm(p, rva, length)
depth = 0
for ins in insns:
    line = f"{ins.address:#010x}  {ins.mnemonic:<8} {ins.op_str}"
    ann = ""
    if ins.mnemonic == "call":
        op = ins.operands[0]
        if op.type == 2:
            tgt = op.imm & 0xffffffff
            if tgt in exp: ann = "   ; -> " + short(exp[tgt])
        elif op.type == 3 and op.mem.base == 0 and op.mem.disp:
            va = op.mem.disp & 0xffffffff
            if va in iat: ann = "   ; -> " + iat[va]
        elif op.type == 3:
            ann = "   ; [vtable/indirect]"
    else:
        for op in ins.operands:
            if op.type == 3 and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp:
                va = op.mem.disp & 0xffffffff
                if base <= va < base + 0x1000000:
                    f = tryf(va)
                    if f is not None and (f == 0.0 or 1e-12 < abs(f) < 1e12):
                        ann = f"   ; [{va:#x}] f32={f!r}"
            if op.type == 2:  # imm
                iv = op.imm & 0xffffffff
                f = struct.unpack("<f", struct.pack("<I", iv))[0]
                if 1e-6 < abs(f) < 1e6:
                    ann += f"   ; imm={iv:#x} asf32={f!r}"
    print(line + ann)
    if ins.mnemonic in ("ret", "retn") and not nostop:
        break
