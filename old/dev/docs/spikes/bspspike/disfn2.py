"""Disassemble a function, resolving call targets to export/import names."""
import sys, struct
import pe

p = sys.argv[1]
rva = int(sys.argv[2], 16)
length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400
base = pe.image_base(p)

# export VA -> name
exp = {base + r: n for n, r in pe.exports(p).items()}
# IAT VA -> name
iat = {}
pp = pe.load(p)
if hasattr(pp, "DIRECTORY_ENTRY_IMPORT"):
    for entry in pp.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode("latin1")
        for imp in entry.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode('latin1')}"

def demangle_short(n):
    # crude: pull Func@Class from ?Func@Class@@...
    if n.startswith("?"):
        parts = n[1:].split("@@")[0].split("@")
        return "::".join(reversed([x for x in parts if x]))
    return n

def try_float(va):
    try:
        b = pe.read_at_va(p, va, 4)
        return struct.unpack("<f", b)[0]
    except Exception:
        return None

insns = pe.disasm(p, rva, length)
for ins in insns:
    line = f"{ins.address:#08x}  {ins.mnemonic:<7} {ins.op_str}"
    ann = ""
    if ins.mnemonic == "call":
        op = ins.operands[0]
        if op.type == 1:  # reg
            pass
        elif op.type == 2:  # imm (direct call)
            tgt = op.imm & 0xffffffff
            if tgt in exp:
                ann = "   ; -> " + demangle_short(exp[tgt])
        elif op.type == 3 and op.mem.base == 0 and op.mem.disp:
            va = op.mem.disp & 0xffffffff
            if va in iat:
                ann = "   ; -> " + iat[va]
    else:
        for op in ins.operands:
            if op.type == 3 and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp:
                va = op.mem.disp & 0xffffffff
                if base <= va < base + 0x400000:
                    f = try_float(va)
                    if f is not None and abs(f) < 1e6 and (1e-9 < abs(f) or f == 0.0):
                        ann = f"   ; [{va:#x}] f32={f!r}"
    print(line + ann)
    if ins.mnemonic in ("ret", "retn") and "nostop" not in sys.argv:
        break
