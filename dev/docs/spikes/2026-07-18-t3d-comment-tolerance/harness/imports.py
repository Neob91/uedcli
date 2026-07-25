#!/usr/bin/env python3
"""Map an IAT slot VA -> imported symbol name for an UnrealEd DLL.
Usage: imports.py <dll> [va_hex ...]   (no VAs => dump all)"""
import sys, pefile
pe=pefile.PE(sys.argv[1])
base=pe.OPTIONAL_HEADER.ImageBase
m={}
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
for imp in pe.DIRECTORY_ENTRY_IMPORT:
    dll=imp.dll.decode('latin1')
    for f in imp.imports:
        name=f.name.decode('latin1') if f.name else f'ord#{f.ordinal}'
        m[f.address]=(dll,name)   # f.address is the VA of the IAT slot
vas=[int(x,16) for x in sys.argv[2:]]
if vas:
    for va in vas:
        d=m.get(va)
        print(f'{va:#010x} -> {d}')
else:
    for va in sorted(m):
        print(f'{va:#010x}  {m[va][0]:12} {m[va][1]}')
