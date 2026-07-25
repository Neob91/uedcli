#!/usr/bin/env python3
"""Flexible cross-DLL disassembler with import/const resolution.

Usage: disx.py <dll> <rva-hex> [n] [--detail]
  <dll> = editor|engine|core (or a path)
Resolves call targets against the module's imports (IAT) and prints const-pool
f32/f64 loads inline so FP compares are legible.
"""
import sys, struct, pefile, capstone

DLLS = {
    "editor": "uned/UED22/Editor.dll",
    "engine": "uned/UED22/Engine.dll",
    "core":   "uned/UED22/core.dll",
}
ROOT = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/"

def load(which):
    path = DLLS.get(which, which)
    if not path.startswith("/"):
        path = ROOT + path
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    # IAT map: address(va) -> symbol name
    iat = {}
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for mod in pe.DIRECTORY_ENTRY_IMPORT:
            dll = mod.dll.decode(errors='replace')
            for imp in mod.imports:
                if imp.name:
                    iat[imp.address] = f"{dll}!{imp.name.decode(errors='replace')}"
    return pe, base, data, iat

def main():
    which = sys.argv[1]
    rva = int(sys.argv[2], 16)
    n = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 400
    pe, base, data, iat = load(which)
    code = data[rva:rva+n*10]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    cnt = 0
    for insn in md.disasm(code, base+rva):
        note = ""
        # resolve call [imm] / jmp [imm] against IAT
        if insn.mnemonic in ("call", "jmp") and insn.op_str.startswith("dword ptr ["):
            try:
                tgt = int(insn.op_str.split("[")[1].rstrip("]"), 16)
                if tgt in iat:
                    note = "  ; " + iat[tgt]
            except Exception:
                pass
        # resolve fld/movss/movsd const-pool loads
        if insn.mnemonic in ("fld", "movss", "movsd", "fldz", "comiss", "comisd", "ucomiss", "mulss", "addss", "subss") and "[0x" in insn.op_str:
            try:
                addr = int(insn.op_str.split("[")[1].split("]")[0], 16)
                off = addr - base
                if 0 <= off < len(data)-8:
                    f4 = struct.unpack("<f", data[off:off+4])[0]
                    f8 = struct.unpack("<d", data[off:off+8])[0]
                    note = f"  ; f32={f4:.6g} f64={f8:.6g}"
            except Exception:
                pass
        print(f"0x{insn.address:08x}: {insn.mnemonic:8s} {insn.op_str}{note}")
        cnt += 1
        if cnt >= n:
            break
        if insn.mnemonic == 'ret':
            break

if __name__ == "__main__":
    main()
