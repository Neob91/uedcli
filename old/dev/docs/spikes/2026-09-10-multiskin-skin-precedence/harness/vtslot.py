"""Find the vtable slot index of a virtual function: for each .rdata occurrence of the
function pointer, walk backwards over the contiguous run of code pointers to the vtable start.

    python3 vtslot.py <dll> <func_rva>
"""

import sys

from pedis import data_refs, load

pe = load(sys.argv[1])
target = int(sys.argv[2], 0)
base = pe.OPTIONAL_HEADER.ImageBase
if target > 0x1000000:
    target -= base
img = pe.get_memory_mapped_image()
text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
tlo, thi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize


def is_code_ptr(rva: int) -> bool:
    v = int.from_bytes(img[rva : rva + 4], "little")
    return bool(v) and tlo <= v - base < thi


for at in data_refs(pe, target):
    start = at
    while start >= 4 and is_code_ptr(start - 4):
        start -= 4
    print(f"vtable={base + start:#010x} slot={(at - start) // 4} disp={at - start:#x}")
