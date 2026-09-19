"""Disassemble a byte range of a PE's .text, printing VA + mnemonic.

Usage: disfn.py <dll> <start_rva_hex> <length_hex> [grep-substr]
"""
import sys
import pefile
import capstone


def main():
    path, start, length = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    needle = sys.argv[4] if len(sys.argv) > 4 else None
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = False
    for ins in md.disasm(data[start:start + length], base + start):
        line = f"{ins.address:#010x}  {ins.mnemonic} {ins.op_str}"
        if needle is None or needle in line:
            print(line)


main()
