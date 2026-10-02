"""Print bytes at a VA in a PE image, as raw hex and as 4 little-endian floats."""
import struct
import sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
va = int(sys.argv[2], 16)
n = int(sys.argv[3]) if len(sys.argv) > 3 else 16
buf = data[va - base:va - base + n]
print('hex   ', buf.hex(' '))
print('floats', [struct.unpack('<f', buf[i:i + 4])[0] for i in range(0, len(buf) - 3, 4)])
