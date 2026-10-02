"""Enumerate every `call dword ptr [reg+0xCC]` (and siblings) in Editor.dll.

A linear capstone sweep desyncs on data-in-text, so this scans for the literal
instruction ENCODING instead: FF /2 with mod=10 (disp32) is `FF 90+r disp32`.
disp 0xCC cannot be encoded as a signed disp8, so the disp32 form is the only one.
Each hit is attributed to the nearest preceding exported symbol, then re-disassembled
to confirm capstone agrees it is that instruction.
"""
import sys, re
from collections import defaultdict

sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = "uned/UED22/Editor.dll"
pef = pe.load(P)
base = pe.image_base(P)
exp = pe.exports(P)
by_rva = sorted((rva, n) for n, rva in exp.items())

DISPS = {0xC4: "NoteSelectionChange?", 0xCC: "SetPivot", 0xD0: "ResetPivot"}
REGS = {0x90: "eax", 0x91: "ecx", 0x92: "edx", 0x93: "ebx", 0x95: "ebp", 0x96: "esi", 0x97: "edi"}


def owner(va):
    rva = va - base
    best = (0, "<below first export>")
    for r, n in by_rva:
        if r <= rva:
            best = (r, n)
        else:
            break
    return best


sec = [s for s in pef.sections if s.Name.rstrip(b"\x00") == b".text"][0]
code = sec.get_data()
start = base + sec.VirtualAddress
md = Cs(CS_ARCH_X86, CS_MODE_32)

groups = defaultdict(list)
total = 0
for disp, label in DISPS.items():
    for modrm, reg in REGS.items():
        pat = bytes([0xFF, modrm, disp, 0x00, 0x00, 0x00])
        for m in re.finditer(re.escape(pat), code):
            va = start + m.start()
            ins = next(md.disasm(code[m.start():m.start() + 8], va), None)
            txt = f"{ins.mnemonic} {ins.op_str}" if ins else "?"
            groups[owner(va)].append((va, disp, label, txt))
            total += 1

for (r, n), lst in sorted(groups.items()):
    print(f"\n=== {n}   export RVA {r:#x} / VA {base + r:#x}")
    for va, disp, label, txt in sorted(lst):
        print(f"   {va:#x}  vtbl+{disp:#x} ({label:<22}) {txt}")
print(f"\ntotal: {total}")

# direct (E8) calls to the three functions, in case any exist
print("\n--- direct E8 calls to SetPivot/ResetPivot/NoteSelectionChange ---")
targets = {base + 0x46060: "SetPivot", base + 0x45CC0: "ResetPivot", base + 0x45880: "NoteSelectionChange"}
import struct
n_direct = 0
for i in range(len(code) - 5):
    if code[i] != 0xE8:
        continue
    rel = struct.unpack("<i", code[i + 1:i + 5])[0]
    tgt = start + i + 5 + rel
    if tgt in targets:
        va = start + i
        print(f"   {va:#x} -> {targets[tgt]}   in {owner(va)[1]}")
        n_direct += 1
print(f"total direct: {n_direct}")
