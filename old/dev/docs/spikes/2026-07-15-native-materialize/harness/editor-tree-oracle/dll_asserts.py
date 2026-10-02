#!/usr/bin/env python3
"""List every `appFailAssert`/`appErrorf` call in an RVA range, with its literal string arguments.

Answers "what can throw inside this function, and on what condition" without reading the whole
disassembly — each call's pushed literals are the original source file, line and expression. Used to
establish that `FLightManager::SetupForActor` (Deus Ex `Render.dll`) contains only
two asserts, both near its entry, so its per-frame "Critical:" stack is a memory fault rather than a
checked condition (board `native-build-has-no-lighting-so-no-mesh-actor`).

    dll_asserts.py <dll-path> <start-rva-hex> <end-rva-hex>

Any PE works; unlike `dll_disasm.py` this takes a path, so it reads the GAME binaries
(`dev/games/deusex/system/*.dll`) as readily as the editor's.
"""
import sys

import capstone
import pefile


def load(path: str):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
    )
    iat = {}
    for mod in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dll = mod.dll.decode(errors="replace")
        for imp in mod.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode(errors='replace')}"
    return pe.OPTIONAL_HEADER.ImageBase, pe.get_memory_mapped_image(), iat


def cstr(data: bytes, base: int, va: int) -> str:
    """The ASCII or UTF-16LE string at `va`, or "" if that is not a printable string."""
    off = va - base
    if not 0 <= off < len(data):
        return ""
    for enc, step in (("ascii", 1), ("utf-16-le", 2)):
        end = off
        while end < len(data) and data[end : end + step] != b"\0" * step:
            end += step
        try:
            s = data[off:end].decode(enc)
        except UnicodeDecodeError:
            continue
        if len(s) > 2 and s.isprintable():
            return s
    return ""


def main() -> None:
    path, lo, hi = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    base, data, iat = load(path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    pending: list[str] = []
    for insn in md.disasm(data[lo:hi], base + lo):
        if insn.mnemonic == "push":
            pending = (pending + [insn.op_str])[-6:]
            continue
        if insn.mnemonic == "call":
            name = ""
            if insn.op_str.startswith("dword ptr ["):
                try:
                    name = iat.get(int(insn.op_str.split("[")[1].rstrip("]"), 16), "")
                except ValueError:
                    name = ""
            if any(k in name for k in ("FailAssert", "Errorf", "appError")):
                print(f"0x{insn.address:08x} {name}")
                for op in pending:
                    try:
                        print(f"    arg: {cstr(data, base, int(op, 16)) or op}")
                    except ValueError:
                        print(f"    arg: {op}")
        pending = []


main()
