"""Find two-step vtable calls in Editor.dll: `mov REG, [base+disp32]` immediately followed by
`call REG`. The one-instruction form (`call dword ptr [base+disp]`) is scanned separately;
together the two forms cover every vtable dispatch the compiler emits."""
import sys, re
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86_const

P = "uned/UED22/Editor.dll"
pef = pe.load(P)
base = pe.image_base(P)
exp = sorted((rva, n) for n, rva in pe.exports(P).items())
sec = [s for s in pef.sections if s.Name.rstrip(b"\x00") == b".text"][0]
code = sec.get_data()
start = base + sec.VirtualAddress
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

WANT = {int(a, 16) for a in sys.argv[1:]} or {0xC4, 0xC8, 0xCC, 0xD0}


def owner(va):
    rva = va - base
    best = (0, "<none>")
    for r, n in exp:
        if r <= rva:
            best = (r, n)
        else:
            break
    return best[1]


# `call reg` = FF D0..D7
for m in re.finditer(rb"\xff[\xd0-\xd7]", code):
    p = m.start()
    callreg = next(md.disasm(code[p:p + 2], start + p), None)
    if not callreg or callreg.mnemonic != "call":
        continue
    tgt = callreg.operands[0].reg
    for back in (6, 5, 3, 2):
        j = p - back
        if j < 0:
            continue
        ins = next(md.disasm(code[j:j + 16], start + j), None)
        if not ins or ins.address + ins.size != start + p:
            continue
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            break
        d, s = ins.operands
        if d.type != x86_const.X86_OP_REG or d.reg != tgt:
            break
        if s.type != 3 or s.mem.base == 0:
            break
        disp = s.mem.disp & 0xFFFFFFFF
        if disp in WANT:
            print(f"{start + p:#x}  {ins.mnemonic} {ins.op_str} ; call  -> vtbl+{disp:#x}"
                  f"   {owner(start + p)}")
        break
