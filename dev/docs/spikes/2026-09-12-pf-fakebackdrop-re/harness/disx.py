"""Disassemble a range/function in a UED22 DLL, annotating call targets and immediates.

Usage: dis.py <dll> <rva-hex> [len-hex] [--nostop]
"""
import struct
import sys

sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe  # noqa: E402

PF = {
    0x1: "PF_Invisible", 0x2: "PF_Masked", 0x4: "PF_Translucent", 0x8: "PF_NotSolid",
    0x10: "PF_Environment", 0x20: "PF_Semisolid", 0x40: "PF_Modulated",
    0x80: "PF_FakeBackdrop", 0x100: "PF_TwoSided", 0x200: "PF_AutoUPan",
    0x400: "PF_AutoVPan", 0x800: "PF_NoSmooth", 0x1000: "PF_BigWavy",
    0x2000: "PF_SmallWavy", 0x4000: "PF_Flat", 0x8000: "PF_LowShadowDetail",
    0x10000: "PF_NoMerge", 0x20000: "PF_CloudWavy", 0x40000: "PF_DirtyShadows",
    0x80000: "PF_BrightCorners", 0x100000: "PF_SpecialLit", 0x200000: "PF_Gouraud",
    0x400000: "PF_Unlit", 0x800000: "PF_HighShadowDetail", 0x1000000: "PF_Portal?",
    0x2000000: "PF_?", 0x4000000: "PF_Portal", 0x8000000: "PF_Mirror",
}


def decode_pf(v):
    if v == 0 or v > 0xFFFFFFFF:
        return None
    names = [n for b, n in PF.items() if v & b]
    known = sum(b for b in PF if v & b)
    if v & ~known:
        return None
    return "|".join(names)


def run(path, rva, length=0x400, stop=True, out=sys.stdout):
    base = pe.image_base(path)
    exp = {base + r: n for n, r in pe.exports(path).items()}
    iat = {}
    pp = pe.load(path)
    if hasattr(pp, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pp.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode("latin1")
            for imp in entry.imports:
                if imp.name:
                    iat[imp.address] = f"{dll}!{imp.name.decode('latin1')}"

    def fl(va):
        try:
            return struct.unpack("<f", pe.read_at_va(path, va, 4))[0]
        except Exception:
            return None

    for ins in pe.disasm(path, rva, length):
        line = f"{ins.address:#010x} +{ins.address - base - rva:<5x} {' '.join(f'{b:02x}' for b in ins.bytes):<24} {ins.mnemonic:<8} {ins.op_str}"
        ann = []
        if ins.mnemonic in ("call", "jmp"):
            op = ins.operands[0]
            if op.type == 2:
                t = op.imm & 0xFFFFFFFF
                if t in exp:
                    ann.append("-> " + exp[t])
                elif ins.mnemonic == "call":
                    ann.append(f"-> sub_{t - base:x}")
            elif op.type == 3 and op.mem.base == 0 and op.mem.disp:
                va = op.mem.disp & 0xFFFFFFFF
                if va in iat:
                    ann.append("-> " + iat[va])
        for op in ins.operands:
            if op.type == 2:
                d = decode_pf(op.imm & 0xFFFFFFFF)
                if d and ins.mnemonic in ("test", "and", "cmp", "or", "xor", "mov", "push"):
                    ann.append("PF: " + d)
            if op.type == 3 and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp:
                va = op.mem.disp & 0xFFFFFFFF
                if base <= va < base + 0x400000:
                    f = fl(va)
                    if f is not None and (f == 0.0 or 1e-9 < abs(f) < 1e9):
                        ann.append(f"[{va:#x}] f32={f!r}")
                    if va in exp:
                        ann.append("data " + exp[va])
        print(line + ("   ; " + "  ".join(ann) if ann else ""), file=out)
        if stop and ins.mnemonic in ("ret", "retn"):
            break


if __name__ == "__main__":
    p = sys.argv[1]
    rva = int(sys.argv[2], 16)
    ln = int(sys.argv[3], 16) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 0x400
    run(p, rva, ln, stop="--nostop" not in sys.argv)
