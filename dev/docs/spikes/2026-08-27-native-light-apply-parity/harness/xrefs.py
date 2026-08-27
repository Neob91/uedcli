"""Find `call rel32` / `jmp rel32` sites in a DLL's .text that target a given VA.

Usage: python xrefs.py <Editor|Engine|Core|Render> <target-va-hex>
"""
import struct
import sys

import pefile

from adis import resolve

path = resolve(sys.argv[1])
target = int(sys.argv[2], 16)
pe = pefile.PE(path, fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
for sec in pe.sections:
    if not sec.Characteristics & 0x20000000:          # IMAGE_SCN_MEM_EXECUTE
        continue
    data = sec.get_data()
    start = base + sec.VirtualAddress
    for i in range(len(data) - 5):
        if data[i] in (0xE8, 0xE9):
            rel = struct.unpack_from("<i", data, i + 1)[0]
            if start + i + 5 + rel == target:
                print(f"{start + i:#010x}  {'call' if data[i] == 0xE8 else 'jmp'} {target:#x}")
