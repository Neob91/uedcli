#!/usr/bin/env python3
"""Disassemble an RVA range out of ANY PE, resolving IAT call targets and const-pool f32 loads.

The same job as the sibling `dll_disasm.py`/`disx.py`, but it takes the DLL as a PATH argument
instead of hard-coding one host's UED22 directory — so it works from any checkout, and it reads the
GAME binaries (`dev/games/deusex/system/*.dll`) as readily as the editor's.

    dll_disasm_path.py <dll-path> <start-rva-hex> [instruction-count]

Used to decode `bspAddNode`'s parent zone/leaf seeding (`Editor.dll 0x3524a`, `0x3535b`),
`FPlane::operator|` (`Core.dll 0x17d60`) and `FLightManager::SetupForActor` (Deus Ex `Render.dll
0x8c70`).
"""
import struct
import sys

import capstone
import pefile

FP_MNEMONICS = (
    "fld", "movss", "comiss", "ucomiss", "mulss", "addss", "subss", "divss", "fcomp",
)


def main() -> None:
    path = sys.argv[1]
    rva = int(sys.argv[2], 16)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
    )
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    iat = {}
    for mod in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dll = mod.dll.decode(errors="replace")
        for imp in mod.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode(errors='replace')}"

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for i, insn in enumerate(md.disasm(data[rva : rva + count * 10], base + rva)):
        if i >= count:
            break
        note = ""
        if insn.mnemonic in ("call", "jmp") and insn.op_str.startswith("dword ptr ["):
            try:
                note = "  ; " + iat.get(int(insn.op_str.split("[")[1].rstrip("]"), 16), "")
            except ValueError:
                pass
        elif insn.mnemonic in FP_MNEMONICS and "[0x" in insn.op_str:
            try:
                off = int(insn.op_str.split("[")[1].split("]")[0], 16) - base
                note = "  ; f32=" + repr(struct.unpack("<f", data[off : off + 4])[0])
            except (ValueError, struct.error):
                pass
        print(f"0x{insn.address:08x}: {insn.mnemonic:9s} {insn.op_str}{note}")


main()
