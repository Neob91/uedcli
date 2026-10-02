"""Robust linear sweep of a PE's .text; print instructions whose op_str matches a substring."""
import sys

import capstone
import pefile

path, needle = sys.argv[1], sys.argv[2]
pe = pefile.PE(path, fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
sec = next(s for s in pe.sections if s.Name.rstrip(b"\x00") == b".text")
data = sec.get_data()
start = base + sec.VirtualAddress
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
seen = {}
pos = 0
while pos < len(data):
    n = 0
    for ins in md.disasm(data[pos:], start + pos):
        n += ins.size
        if needle in ins.op_str:
            seen.setdefault(ins.address, f"{ins.mnemonic} {ins.op_str}")
    pos += max(n, 1)
for a in sorted(seen):
    print(hex(a), seen[a])
print(len(seen), "hits", file=sys.stderr)
