"""Shared PE helpers: export map, RVA<->offset, capstone disassembly, byte/float reads.

Static only — reads the UED22 DLLs, never runs the editor. Mirror of the reusable
`_scratch/bspspike/pe.py` harness, committed here so this spike is reproducible without
the throwaway scratch dir. Needs `pip install capstone pefile` into the uedcli venv.
"""
import struct

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

_cache = {}


def load(path):
    if path not in _cache:
        _cache[path] = pefile.PE(path, fast_load=False)
    return _cache[path]


def image_base(path):
    return load(path).OPTIONAL_HEADER.ImageBase


def exports(path):
    pe = load(path)
    out = {}
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if e.name:
                out[e.name.decode("latin1")] = e.address  # RVA
    return out


def find_exports(path, substr):
    return {n: rva for n, rva in exports(path).items() if substr in n}


def va_to_offset(path, va):
    return load(path).get_offset_from_rva(va - image_base(path))


def read_at_va(path, va, n):
    off = va_to_offset(path, va)
    return load(path).__data__[off:off + n]


def read_float_va(path, va):
    return struct.unpack("<f", read_at_va(path, va, 4))[0]


def read_u32_va(path, va):
    return struct.unpack("<I", read_at_va(path, va, 4))[0]


def disasm(path, rva, length=0x600):
    """Disassemble `length` bytes starting at the file RVA (not subtracting image base)."""
    pe = load(path)
    base = image_base(path)
    off = pe.get_offset_from_rva(rva)
    code = pe.__data__[off:off + length]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    return list(md.disasm(code, base + rva))
