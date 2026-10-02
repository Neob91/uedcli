#!/usr/bin/env python3
"""Full linear disassembly of bspAddNode (Editor.dll VA 0x10034e80) looking for ANY write that
could touch FBspNode.NodeFlags at struct offset +0x37 -- including ones a bare "+0x37" operand-
string scan would MISS: a wider (word/dword) MOV/OR/AND at offset 0x34/0x35/0x36 whose write WIDTH
spans byte 0x37, or a rep movs/memcpy-style bulk copy of the whole 0x40-byte FBspNode struct.
"""
import capstone
import pefile

DLL = "/workspace/uedcli/.claude/worktrees/node-flags-live-verify/uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000
VA_START = 0x10034e80

pe = pefile.PE(DLL, fast_load=True)
rva_start = VA_START - IMAGE_BASE
# read a generous chunk; bspAddNode is a real function, likely a few hundred bytes to ~1-2KB
data = pe.get_memory_mapped_image()[rva_start:rva_start + 0x1200]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

WIDTH = {"byte ptr": 1, "word ptr": 2, "dword ptr": 4, "qword ptr": 8}


def mem_write_width(insn):
    """If insn's first (destination) operand is a memory write, return its byte width, else None."""
    if not insn.operands:
        return None
    dst = insn.operands[0]
    if dst.type != capstone.x86.X86_OP_MEM:
        return None
    # capstone gives operand size directly
    return dst.size


insns = list(md.disasm(data, VA_START))
print(f"disassembled {len(insns)} instructions from {VA_START:#x}")

ret_seen_at = None
flagged = []
rep_movs = []
calls = []
for i, insn in enumerate(insns):
    mnem = insn.mnemonic
    ops = insn.op_str
    # Track first top-level ret (end of function, ignoring the fact that jumps could skip past it --
    # good enough for a bounded linear scan; we print everything up to a generous margin anyway)
    if mnem == "ret" and ret_seen_at is None:
        ret_seen_at = i
    if mnem in ("movsb", "movsd", "movsw", "rep movsb", "rep movsd"):
        rep_movs.append((insn.address, mnem, ops))
    if mnem == "call":
        calls.append((insn.address, mnem, ops))
    # look for "+ 0x2" through "+ 0x3f" style displacement, then check if the WRITE WIDTH covers 0x37
    if insn.operands:
        dst = insn.operands[0]
        if dst.type == capstone.x86.X86_OP_MEM and dst.mem.disp != 0:
            disp = dst.mem.disp
            width = dst.size or 0
            # is this a WRITE (dest is mem) whose byte range [disp, disp+width) includes 0x37?
            if 0 <= disp <= 0x37 < disp + max(width, 1) and mnem not in ("lea", "cmp", "test"):
                flagged.append((insn.address, mnem, ops, disp, width))

print(f"\n=== instructions whose write range could cover offset +0x37 (mnemonic, disp, width) ===")
for addr, mnem, ops, disp, width in flagged:
    print(f"  {addr:#x}: {mnem} {ops}   disp={disp:#x} width={width}")
if not flagged:
    print("  none found")

print(f"\n=== rep movs / string-copy instructions (potential block-copy) ===")
for addr, mnem, ops in rep_movs:
    print(f"  {addr:#x}: {mnem} {ops}")
if not rep_movs:
    print("  none found")

print(f"\n=== calls (potential memcpy/appMemcpy or FArray helper) ===")
for addr, mnem, ops in calls[:40]:
    print(f"  {addr:#x}: {mnem} {ops}")

print(f"\n=== full listing up to first top-level ret (+20 margin) ===")
end = (ret_seen_at + 20) if ret_seen_at is not None else len(insns)
for insn in insns[:end]:
    print(f"  {insn.address:#x}: {insn.mnemonic} {insn.op_str}")

print("\n=== context around the +0x37 write (0x100351c2) ===")
target = 0x100351c2
for insn in insns:
    if target - 0x120 <= insn.address <= target + 0x60:
        marker = "  >>> " if insn.address == target else "      "
        print(f"{marker}{insn.address:#x}: {insn.mnemonic} {insn.op_str}")
