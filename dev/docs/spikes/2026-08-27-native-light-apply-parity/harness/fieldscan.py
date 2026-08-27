"""Scan a DLL's .text for instructions touching [reg+disp] with a given disp.

Usage: python3 fieldscan.py <dll> <disp-hex> [more-disp...]
Prints VA, the nearest preceding export, and the instruction.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pe, rdis
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

path = rdis.resolve(sys.argv[1])
disps = {int(a, 16) for a in sys.argv[2:]}
p = pe.load(path)
base = p.OPTIONAL_HEADER.ImageBase
exp = sorted((rva + base, n) for n, rva in pe.exports(path).items())


def nearest(va):
    lo, hi = 0, len(exp)
    while lo < hi:
        mid = (lo + hi) // 2
        if exp[mid][0] <= va:
            lo = mid + 1
        else:
            hi = mid
    return exp[lo - 1][1] if lo else "?"


md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
for sec in p.sections:
    if sec.Name.rstrip(b"\0") != b".text":
        continue
    code = bytes(p.__data__[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData])
    for ins in md.disasm(code, base + sec.VirtualAddress):
        for op in ins.operands:
            if op.type == 3 and op.mem.base != 0 and (op.mem.disp & 0xffffffff) in disps:
                print(f"{ins.address:#010x}  {nearest(ins.address):<60} {ins.mnemonic} {ins.op_str}")
                break
