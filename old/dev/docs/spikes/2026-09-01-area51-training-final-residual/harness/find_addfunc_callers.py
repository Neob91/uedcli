#!/usr/bin/env python3
"""Static: find every call site in Editor.dll's .text that targets AddBrushToWorldFunc
(VA 0x100031770, RVA 0x31770 -- disassembly-confirmed 2026-09-01, see
area51_addfunc_oracle.py). One caller is expected to be FilterEdPoly (the classify/split
descent function this round is trying to locate -- no exported/string symbol in this DLL).

Method: capstone linear disassembly over .text, collect every `call rel32` whose resolved
target == ADDFUNC_VA. Then, for each hit, walk backward from the call site to find the
enclosing function's entry (heuristic: nearest preceding `push ebp; mov ebp, esp` prologue,
or nearest preceding `int3`/`nop` padding run -- MSVC pads functions to a boundary).

Usage: find_addfunc_callers.py
"""
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from capstone.x86 import X86_OP_IMM

DLL = Path(__file__).resolve().parents[5] / "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000
ADDFUNC_VA = 0x10031770


def load_text():
    pe = pefile.PE(str(DLL), fast_load=True)
    sec = next(s for s in pe.sections if s.Name.startswith(b".text"))
    va = IMAGE_BASE + sec.VirtualAddress
    data = sec.get_data()[: sec.Misc_VirtualSize]
    return va, data


def find_prologue_before(data, text_va, addr):
    """Scan backward from addr for the nearest `55 8b ec` (push ebp; mov ebp,esp) --
    the standard MSVC non-optimized prologue -- or `83 ec` (sub esp, imm8) frame-less
    entry preceded by an int3/nop pad run (function-alignment filler)."""
    off = addr - text_va
    # Look back up to 4KB for a push-ebp/mov-ebp,esp prologue.
    lo = max(0, off - 4096)
    window = data[lo:off]
    best = None
    idx = window.rfind(b"\x55\x8b\xec")
    if idx != -1:
        best = lo + idx
    return (text_va + best) if best is not None else None


def main():
    text_va, data = load_text()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False

    hits = []
    for insn in md.disasm(data, text_va):
        if insn.mnemonic != "call":
            continue
        op = insn.op_str
        if not op.startswith("0x"):
            continue
        try:
            target = int(op, 16)
        except ValueError:
            continue
        if target == ADDFUNC_VA:
            hits.append(insn.address)

    print(f".text VA={hex(text_va)} size={len(data):#x}")
    print(f"call sites targeting AddBrushToWorldFunc ({hex(ADDFUNC_VA)}): {len(hits)}")
    for h in hits:
        fn = find_prologue_before(data, text_va, h)
        print(f"  call site {hex(h)}  (rva {hex(h - IMAGE_BASE)})  "
              f"nearest-prologue {hex(fn) if fn else '?'} "
              f"(rva {hex(fn - IMAGE_BASE) if fn else '?'})")


if __name__ == "__main__":
    main()
