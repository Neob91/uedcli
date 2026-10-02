"""Brute-force scan a PE's .text for any instruction whose memory operand carries a given disp32.

Decodes at every byte offset where the 4-byte little-endian disp appears, so data-in-text can't
desync the read (a linear sweep can and does).

Usage: scan_disp.py <dll> <disp_hex> [context_bytes]
"""
import struct
import sys
import capstone
import pefile

path, disp = sys.argv[1], int(sys.argv[2], 16)
ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 0

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
text = next(s for s in pe.sections if s.Name.rstrip(b'\x00') == b'.text')
lo, hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True
needle = struct.pack('<I', disp)
seen = set()
off = lo
while True:
    i = data.find(needle, off, hi)
    if i < 0:
        break
    off = i + 1
    for back in range(1, 12):
        start = i - back
        if start < lo:
            continue
        for ins in md.disasm(data[start:start + 16], base + start):
            if ins.address in seen:
                break
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.disp == disp and op.mem.base != 0:
                    seen.add(ins.address)
                    print(f"{ins.address:#010x}  {ins.mnemonic} {ins.op_str}")
                    if ctx:
                        for c in md.disasm(data[start - ctx:start + ctx], base + start - ctx):
                            print(f"    {c.address:#010x}  {c.mnemonic} {c.op_str}")
                        print()
            break
