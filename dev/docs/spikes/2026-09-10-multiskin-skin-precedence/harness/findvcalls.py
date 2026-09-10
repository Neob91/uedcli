"""Find `call dword ptr [reg + disp32]` sites — i.e. candidate virtual calls through a known
vtable slot — across a set of PE files.

    python3 findvcalls.py <disp> <pe> [<pe> ...]
"""

import re
import sys

from pedis import load

disp = int(sys.argv[1], 0)
needle = re.compile(rb"\xff[\x90-\x97]" + re.escape(disp.to_bytes(4, "little")))

for path in sys.argv[2:]:
    pe = load(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        raw = s.get_data()
        for m in needle.finditer(raw):
            rva = s.VirtualAddress + m.start()
            print(f"{path}  {base + rva:#010x}  rva={rva:#x}  {m.group().hex()}")
