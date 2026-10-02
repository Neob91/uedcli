"""Scan any PE's .text for `call dword ptr [reg+disp32]` with a given displacement."""
import sys, re
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = sys.argv[1]
disp = int(sys.argv[2], 16)
pef = pe.load(P)
base = pe.image_base(P)
exp = sorted((rva, n) for n, rva in pe.exports(P).items())
md = Cs(CS_ARCH_X86, CS_MODE_32)
REGS = {0x90: "eax", 0x91: "ecx", 0x92: "edx", 0x93: "ebx", 0x95: "ebp", 0x96: "esi", 0x97: "edi"}


def owner(va):
    rva = va - base
    best = (0, "<none>")
    for r, n in exp:
        if r <= rva:
            best = (r, n)
        else:
            break
    return best[1]


for s in pef.sections:
    if s.Name.rstrip(b"\x00") != b".text":
        continue
    code = s.get_data()
    start = base + s.VirtualAddress
    for modrm in REGS:
        pat = bytes([0xFF, modrm, disp & 0xFF, (disp >> 8) & 0xFF, (disp >> 16) & 0xFF, (disp >> 24) & 0xFF])
        for m in re.finditer(re.escape(pat), code):
            va = start + m.start()
            ins = next(md.disasm(code[m.start():m.start() + 8], va), None)
            print(f"{va:#x}  {ins.mnemonic} {ins.op_str}   {owner(va)}")
