"""Scan a DLL's .text for TEST/AND/CMP/OR against a given immediate; report RVAs.

Usage: scanflags.py <dll> <imm-hex> [<imm-hex> ...]
Linear-sweep disassembly (may mis-sync), so results are candidates to verify.
"""
import sys

sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe  # noqa: E402
from capstone import CS_ARCH_X86, CS_MODE_32, Cs  # noqa: E402


def text_section(path):
    p = pe.load(path)
    for s in p.sections:
        if s.Name.rstrip(b"\x00") in (b".text", b"CODE"):
            return s
    return p.sections[0]


def sweep(path, start_off=0):
    p = pe.load(path)
    s = text_section(path)
    base = pe.image_base(path)
    rva = s.VirtualAddress
    off = s.PointerToRawData
    size = min(s.Misc_VirtualSize, s.SizeOfRawData)
    code = p.__data__[off + start_off : off + size]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    return md.disasm(code, base + rva + start_off)


def main():
    path = sys.argv[1]
    imms = {int(a, 16) for a in sys.argv[2:]}
    base = pe.image_base(path)
    seen = set()
    # 4 sweep phases to mitigate mis-sync
    for phase in range(4):
        for ins in sweep(path, phase):
            if ins.mnemonic not in ("test", "and", "cmp", "or", "xor", "mov", "push", "sub", "add"):
                continue
            for op in ins.operands:
                if op.type == 2 and (op.imm & 0xFFFFFFFF) in imms:
                    key = (ins.address, ins.mnemonic, ins.op_str)
                    if key in seen:
                        continue
                    seen.add(key)
                    print(f"{ins.address - base:#08x}  {ins.mnemonic:<6} {ins.op_str}")
    print(f"-- {len(seen)} hits", file=sys.stderr)


main()
