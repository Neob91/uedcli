#!/usr/bin/env python3
"""Linear disasm of Editor.dll's .text section; find every `call 0x10034e80` (bspAddNode) and
dump the preceding push sequence to see how the NodeFlags argument (4th push, esp+0x10 at the
call) is computed at each call site."""
import capstone
import pefile

DLL = "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000
TARGET = 0x10034e80

pe = pefile.PE(DLL, fast_load=True)
text = None
for s in pe.sections:
    if s.Name.startswith(b".text"):
        text = s
        break
data = text.get_data()
va_start = text.VirtualAddress + IMAGE_BASE

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

insns = list(md.disasm(data, va_start))
print(f"disassembled {len(insns)} instructions in .text ({va_start:#x}..{va_start+len(data):#x})")

calls = [i for i, ins in enumerate(insns)
         if ins.mnemonic == "call" and ins.op_str == hex(TARGET)]
print(f"found {len(calls)} direct call sites to bspAddNode ({TARGET:#x})\n")

for idx in calls:
    call_insn = insns[idx]
    print(f"=== call site at {call_insn.address:#x} ===")
    # print the preceding ~18 instructions (the 5-arg push sequence + how each is computed)
    lo = max(0, idx - 18)
    for ins in insns[lo:idx + 1]:
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    print()
