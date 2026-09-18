"""Locate a UTF-16LE literal in a PE image and print its VA."""
import sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
needle = sys.argv[2].encode('utf-16le')
off = 0
while True:
    i = data.find(needle, off)
    if i < 0:
        break
    print(f"VA 0x{base + i:x}")
    off = i + 1
