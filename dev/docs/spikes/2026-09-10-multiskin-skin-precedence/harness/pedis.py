"""Static-disassembly toolkit for the Skin / MultiSkins precedence spike.

Usage:
    python3 dis.py exports <dll> [regex]      # list matching exports with RVA
    python3 dis.py dis <dll> <rva> [n]        # disassemble n instructions at RVA
    python3 dis.py xrefs <dll> <rva>          # find direct E8/E9 rel32 calls/jmps to RVA
    python3 dis.py vtxrefs <dll> <rva>        # find the RVA in .rdata (vtable slots), then
                                              # find code referencing that vtable address
    python3 dis.py disp <dll> <disp>          # find `call [reg+disp]` indirect calls
"""

from __future__ import annotations

import re
import sys

import capstone
import pefile


def load(path: str):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(
        directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
        ]
    )
    return pe


def rva_to_off(pe, rva: int) -> int | None:
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None


def section_of(pe, rva: int) -> str | None:
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.Name.rstrip(b"\0").decode()
    return None


def exports(pe):
    out = []
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if e.name:
                out.append((e.name.decode(), e.address))
    return out


def md():
    m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    m.detail = False
    return m


def disasm(pe, path: str, rva: int, n: int = 80):
    data = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    lines = []
    for i in md().disasm(data[rva : rva + n * 8], base + rva, count=n):
        lines.append(f"{i.address:#010x}  {i.bytes.hex():<20} {i.mnemonic} {i.op_str}")
    return lines


def direct_xrefs(pe, target_rva: int):
    """Every E8 (call rel32) / E9 (jmp rel32) whose destination is target_rva."""
    hits = []
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):  # MEM_EXECUTE
            continue
        raw = s.get_data()
        va = s.VirtualAddress
        for m in re.finditer(rb"[\xe8\xe9]", raw):
            off = m.start()
            if off + 5 > len(raw):
                continue
            rel = int.from_bytes(raw[off + 1 : off + 5], "little", signed=True)
            dest = va + off + 5 + rel
            if dest == target_rva:
                hits.append((va + off, raw[off]))
    return hits


def data_refs(pe, value_rva: int):
    """Find absolute addresses (ImageBase+value_rva) stored anywhere in the image."""
    base = pe.OPTIONAL_HEADER.ImageBase
    needle = (base + value_rva).to_bytes(4, "little")
    hits = []
    for s in pe.sections:
        raw = s.get_data()
        for m in re.finditer(re.escape(needle), raw):
            hits.append(s.VirtualAddress + m.start())
    return hits


def main():
    cmd = sys.argv[1]
    path = sys.argv[2]
    pe = load(path)
    if cmd == "exports":
        pat = sys.argv[3] if len(sys.argv) > 3 else "."
        for name, rva in sorted(exports(pe), key=lambda t: t[1]):
            if re.search(pat, name):
                print(f"{rva:#010x}  {name}")
    elif cmd == "dis":
        rva = int(sys.argv[3], 0) - (pe.OPTIONAL_HEADER.ImageBase if int(sys.argv[3], 0) > 0x1000000 else 0)
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 80
        print("\n".join(disasm(pe, path, rva, n)))
    elif cmd == "xrefs":
        rva = int(sys.argv[3], 0)
        if rva > 0x1000000:
            rva -= pe.OPTIONAL_HEADER.ImageBase
        for at, op in direct_xrefs(pe, rva):
            print(f"{pe.OPTIONAL_HEADER.ImageBase + at:#010x}  {'call' if op == 0xE8 else 'jmp'} -> {rva:#x}")
    elif cmd == "datarefs":
        rva = int(sys.argv[3], 0)
        if rva > 0x1000000:
            rva -= pe.OPTIONAL_HEADER.ImageBase
        for at in data_refs(pe, rva):
            print(f"{pe.OPTIONAL_HEADER.ImageBase + at:#010x}  [{section_of(pe, at)}]")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
