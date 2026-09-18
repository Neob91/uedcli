"""Find every instruction in Editor.dll whose memory operand is [reg+0x11c] (AActor::ObjectFlags-
adjacent dword this campaign reads the selected bit from), and print it with its owner export.
Robust against data-in-text: brute-force decode at every offset where the disp32 0x0000011c
byte pattern appears, then keep decodes whose length spans the pattern.
"""
import sys, re, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = "uned/UED22/Editor.dll"
pef = pe.load(P)
base = pe.image_base(P)
exp = sorted((rva, n) for n, rva in pe.exports(P).items())
sec = [s for s in pef.sections if s.Name.rstrip(b"\x00") == b".text"][0]
code = sec.get_data()
start = base + sec.VirtualAddress
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


want = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x11C
needle = struct.pack("<I", want)
seen = set()
for m in re.finditer(re.escape(needle), code):
    p = m.start()
    for back in range(2, 9):
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
            print(f"{ins.address:#x}  {ins.mnemonic:<7} {ins.op_str:<44} {owner(ins.address)}")
            break
