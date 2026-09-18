"""Like flagscan.py but takes the PE path as argv[1] and the displacement as argv[2]."""
import sys, re, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = sys.argv[1]
want = int(sys.argv[2], 16)
pef = pe.load(P)
base = pe.image_base(P)
exp = sorted((rva, n) for n, rva in pe.exports(P).items())
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True


def owner(va):
    rva = va - base
    best = (0, "<none>")
    for r, n in exp:
        if r <= rva:
            best = (r, n)
        else:
            break
    return best[1]


for sec in pef.sections:
    if sec.Name.rstrip(b"\x00") != b".text":
        continue
    code = sec.get_data()
    start = base + sec.VirtualAddress
    needle = struct.pack("<I", want)
    seen = set()
    for m in re.finditer(re.escape(needle), code):
        p = m.start()
        for back in range(2, 10):
            j = p - back
            if j < 0:
                continue
            ins = next(md.disasm(code[j:j + 16], start + j), None)
            if not ins or ins.address + ins.size <= start + p:
                continue
            ok = any(o.type == 3 and o.mem.base != 0 and (o.mem.disp & 0xFFFFFFFF) == want
                     for o in ins.operands)
            if ok and ins.address not in seen:
                seen.add(ins.address)
                print(f"{ins.address:#x}  {ins.mnemonic:<7} {ins.op_str:<46} {owner(ins.address)}")
                break
