"""Disassemble a byte range of a PE and print it (linear sweep from `rva`).

    python3 ctx.py <pe> <rva> <nbytes>
"""

import sys

import capstone

from pedis import load

pe = load(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
rva = int(sys.argv[2], 0)
if rva > 0x1000000:
    rva -= base
n = int(sys.argv[3], 0)
img = pe.get_memory_mapped_image()
m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for i in m.disasm(img[rva : rva + n], base + rva):
    print(f"{i.address:#010x}  {i.bytes.hex():<20} {i.mnemonic} {i.op_str}")
