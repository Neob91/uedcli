"""Find every 4-byte little-endian occurrence of a VA in a PE image, print its VA."""
import struct
import sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
target = struct.pack('<I', int(sys.argv[2], 16))
off = 0
while True:
    i = data.find(target, off)
    if i < 0:
        break
    print(f"at VA 0x{base + i:x} (rva 0x{i:x})")
    off = i + 1
