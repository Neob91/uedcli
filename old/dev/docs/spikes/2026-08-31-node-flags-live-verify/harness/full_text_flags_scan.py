#!/usr/bin/env python3
"""Comprehensive linear scan of Editor.dll's ENTIRE .text section (not just exported functions --
that was the original board-item scan's blind spot, which is how it missed bspAddNode) for any
instruction whose memory-write operand's byte range [disp, disp+width) covers offset 0x37 (any
base register) -- the FBspNode.NodeFlags byte. Also separately lists ALL such write instructions
regardless of disp, restricted to disp in [0x30,0x3f], to catch any node-flags-ADJACENT write
too (e.g. a word/dword write starting at 0x36 or 0x34 that would side-effect 0x37)."""
import capstone
import pefile

DLL = "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000

pe = pefile.PE(DLL, fast_load=True)
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
data = text.get_data()
va_start = text.VirtualAddress + IMAGE_BASE

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True
insns = list(md.disasm(data, va_start))
print(f"{len(insns)} instructions in .text ({va_start:#x}..{va_start+len(data):#x})")

exact37 = []
near = []
for insn in insns:
    if not insn.operands:
        continue
    dst = insn.operands[0]
    if dst.type != capstone.x86.X86_OP_MEM:
        continue
    disp = dst.mem.disp
    width = dst.size or 0
    if insn.mnemonic in ("lea", "cmp", "test", "nop"):
        continue
    if 0 <= disp <= 0x37 < disp + max(width, 1):
        exact37.append(insn)
    elif 0x2c <= disp <= 0x3f:
        near.append(insn)

print(f"\n=== {len(exact37)} writes whose range covers +0x37 exactly ===")
for insn in exact37:
    print(f"  {insn.address:#x}: {insn.mnemonic} {insn.op_str}")

print(f"\n=== {len(near)} writes with disp in [0x2c,0x3f] (context, not necessarily covering 0x37) ===")
for insn in near[:60]:
    print(f"  {insn.address:#x}: {insn.mnemonic} {insn.op_str}")
if len(near) > 60:
    print(f"  ... ({len(near)-60} more)")
