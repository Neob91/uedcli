"""Dump a dword table from a PE, resolving each entry to an exported symbol when possible."""
import struct
import sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
names = {}
exp = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
if exp:
    for s in exp.symbols:
        if s.name:
            names[base + s.address] = s.name.decode()

start = int(sys.argv[2], 16) - base
count = int(sys.argv[3])
for i in range(count):
    off = start + 4 * i
    val = struct.unpack('<I', data[off:off + 4])[0]
    print(f"+0x{4 * i:03x}  VA 0x{base + off:x} -> 0x{val:08x}  {names.get(val, '')}")
