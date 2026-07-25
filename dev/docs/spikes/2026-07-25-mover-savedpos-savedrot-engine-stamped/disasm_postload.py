#!/usr/bin/env python3
"""Disassemble `AMover::PostLoad()` out of a UE1 `Engine.dll` — the function that stamps the mover
`SavedPos`/`SavedRot` sentinels.

`PostLoad` is an exported virtual (`?PostLoad@AMover@@UAEXXZ`), so it can be located by NAME rather
than by a guessed address. The DX-shipped `Engine.dll` routes its exports through a `jmp` thunk
table; `--follow-thunk` chases the first `jmp rel32`.

Requires `pefile` + `capstone` (`pip install pefile capstone`) — see
`dev/docs/unrealed/extracting-from-dll.md` "Beyond strings: disassembly".

Usage:
    python3 disasm_postload.py Tools/uedctl/uned/UED22/Engine.dll
    python3 disasm_postload.py --follow-thunk /path/to/DX/System/Engine.dll
"""
from __future__ import annotations

import argparse

import capstone
import pefile

SYMBOL = "?PostLoad@AMover@@UAEXXZ"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dll")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--count", type=int, default=48, help="instructions to print")
    ap.add_argument("--follow-thunk", action="store_true",
                    help="the export is a `jmp rel32` thunk (the DX-shipped Engine.dll) — chase it")
    args = ap.parse_args()

    pe = pefile.PE(args.dll, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    data = open(args.dll, "rb").read()

    def rva2off(rva: int) -> int:
        for s in pe.sections:
            size = max(s.Misc_VirtualSize, s.SizeOfRawData)
            if s.VirtualAddress <= rva < s.VirtualAddress + size:
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"RVA {rva:#x} outside every section")

    hits = [e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols
            if e.name and e.name.decode("latin-1") == args.symbol]
    if not hits:
        raise SystemExit(f"export {args.symbol!r} not found in {args.dll}")
    rva = hits[0]
    print(f"{args.symbol} @ RVA {rva:#x}")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    if args.follow_thunk:
        first = next(md.disasm(data[rva2off(rva):rva2off(rva) + 8], rva))
        if first.mnemonic != "jmp":
            raise SystemExit(f"expected a jmp thunk, got {first.mnemonic} {first.op_str}")
        rva = int(first.op_str, 16)
        print(f"  thunk -> {rva:#x}")

    off = rva2off(rva)
    for i, insn in enumerate(md.disasm(data[off:off + 0x200], rva)):
        note = ""
        if "0xc640e400" in insn.op_str:
            note = "   <-- -12345.0f  (SavedPos component)"
        elif insn.op_str.endswith(("0x7b", "0x1c8", "0x315")):
            note = "   <-- 123 / 456 / 789  (SavedRot component)"
        print(f"0x{insn.address:x}\t{insn.mnemonic}\t{insn.op_str}{note}")
        if insn.mnemonic == "ret" or i >= args.count:
            break


if __name__ == "__main__":
    main()
