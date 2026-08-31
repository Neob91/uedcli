#!/usr/bin/env python3
"""Disassemble bspBuild (vtbl+0x1fc = VA 0x10035ef0, the top-level SplitPolyList-equivalent per
earlier findings) looking for calls through vtbl+0x224 (bspAddNode) and how the NodeFlags arg
(the push immediately preceding the call, 2nd-from-top of the 5-arg block) is computed --
literal constant, or read from a variable whose own initialization is traceable."""
import capstone
import pefile

DLL = "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000
VA_START = 0x10035ef0

pe = pefile.PE(DLL, fast_load=True)
rva_start = VA_START - IMAGE_BASE
data = pe.get_memory_mapped_image()[rva_start:rva_start + 0x2000]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True
insns = list(md.disasm(data, VA_START))
print(f"disassembled {len(insns)} instructions from {VA_START:#x}")

# find calls through [reg + 0x224]
for i, insn in enumerate(insns):
    if insn.mnemonic == "call" and "0x224" in insn.op_str:
        print(f"\n=== call-through-vtbl+0x224 at {insn.address:#x}: {insn.mnemonic} {insn.op_str} ===")
        lo = max(0, i - 20)
        for ins in insns[lo:i + 1]:
            print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
