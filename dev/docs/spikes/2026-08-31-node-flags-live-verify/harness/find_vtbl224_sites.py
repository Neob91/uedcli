#!/usr/bin/env python3
"""Whole-.text scan for any access through vtbl offset +0x224 (bspAddNode's slot in the
UEditorEngine-ish vtable at 0x100cf5d4). Direct call-rel32 scan already found ZERO -- this
finds the INDIRECT (call [reg+0x224]) sites instead, wherever they occur."""
import capstone
import pefile

DLL = "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000

pe = pefile.PE(DLL, fast_load=True)
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
data = text.get_data()
va_start = text.VirtualAddress + IMAGE_BASE

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
insns = list(md.disasm(data, va_start))
print(f"{len(insns)} instructions in .text")

hits = [(i, ins) for i, ins in enumerate(insns)
        if ins.mnemonic == "call" and "+ 0x224]" in ins.op_str]
print(f"{len(hits)} `call [reg + 0x224]` sites\n")
for i, ins in hits:
    print(f"=== {ins.address:#x}: {ins.mnemonic} {ins.op_str} ===")
    lo = max(0, i - 20)
    for prev in insns[lo:i + 1]:
        print(f"  {prev.address:#x}: {prev.mnemonic} {prev.op_str}")
    print()
