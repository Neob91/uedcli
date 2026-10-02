import sys, struct
import pe

p = sys.argv[1]
rva = int(sys.argv[2], 16)
length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400

base = pe.image_base(p)
insns = pe.disasm(p, rva, length)

def try_float(va):
    try:
        b = pe.read_at_va(p, va, 8)
    except Exception:
        return None
    f = struct.unpack("<f", b[:4])[0]
    d = struct.unpack("<d", b)[0]
    return f, d

depth = 0
for ins in insns:
    line = f"{ins.address:#08x}  {ins.mnemonic:<7} {ins.op_str}"
    # annotate absolute mem operands with float values from rdata
    ann = ""
    for op in ins.operands:
        if op.type == 3:  # X86_OP_MEM
            m = op.mem
            if m.base == 0 and m.index == 0 and m.disp:
                va = m.disp & 0xffffffff
                if base <= va < base + 0x400000:
                    fv = try_float(va)
                    if fv:
                        f, d = fv
                        if abs(f) < 1e6 and (abs(f) > 1e-9 or f == 0.0):
                            ann = f"   ; [{va:#x}] f32={f!r} f64={d!r}"
    print(line + ann)
    if ins.mnemonic in ("ret", "retn") and "nostop" not in sys.argv:
        break
