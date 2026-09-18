"""Find `lea ecx, [reg+disp]` immediately followed by `call [0x100cede4]` (FColor::Plane)
inside Editor.dll, and report the displacement + containing export. Used to map which
UEditorEngine C_* color member (a contiguous FColor block) each draw site uses."""
import sys, re, struct
from collections import Counter
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


# The FColor::Plane thunk import slot, as seen at 0x1003e8b7: call dword ptr [0x100cede4]
CALL = bytes.fromhex("ff15") + struct.pack("<I", 0x100CEDE4)
hits = []
for m in re.finditer(re.escape(CALL), code):
    # decode backwards: the preceding instruction should be `lea ecx, [reg+disp32]` (8d 89/8e/8f/88 disp32)
    i = m.start()
    for back in (6, 3, 2):
        j = i - back
        if j < 0:
            continue
        ins = next(md.disasm(code[j:i], start + j), None)
        if ins and ins.mnemonic == "lea" and ins.op_str.startswith("ecx,"):
            op = ins.operands[1]
            hits.append((start + i, op.mem.disp, ins.op_str, owner(start + i)))
            break
    else:
        hits.append((start + i, None, "?", owner(start + i)))

for va, disp, ops, own in hits:
    d = f"{disp:#x}" if disp is not None else "?"
    print(f"{va:#x}  disp={d:<8} lea {ops:<26} {own}")
print()
print(Counter(d for _, d, _, _ in hits).most_common())
