"""Find call sites of an IMPORTED function: locate its IAT slot, then every
`call dword ptr [<abs IAT addr>]` (FF 15 <abs>) or `jmp` thunk to it.

    python3 impxrefs.py <pe> <substring-of-import-name>
"""

import re
import sys

from pedis import load

pe = load(sys.argv[1])
want = sys.argv[2]
base = pe.OPTIONAL_HEADER.ImageBase

slots = []
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in entry.imports:
        if imp.name and want.encode() in imp.name:
            slots.append((imp.name.decode(), imp.address))  # imp.address is the VA of the IAT slot

for name, va in slots:
    print(f"IAT slot {va:#010x}  {name}")
    needle = b"\xff\x15" + (va).to_bytes(4, "little")
    thunk = b"\xff\x25" + (va).to_bytes(4, "little")
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        raw = s.get_data()
        for pat, kind in ((needle, "call"), (thunk, "jmpthunk")):
            for m in re.finditer(re.escape(pat), raw):
                print(f"  {kind} at {base + s.VirtualAddress + m.start():#010x}")
