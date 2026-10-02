"""Minimal PE helper: export lookup + capstone x86 disassembly at an RVA."""
import capstone
import pefile

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
    d = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    if d:
        for e in d.symbols:
            if e.name:
                out[e.name.decode()] = e.address
    return out


def find_exports(path, sub):
    return {k: v for k, v in exports(path).items() if sub.lower() in k.lower()}


def read_at_va(path, va, n):
    pe = load(path)
    return pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, n)


def disasm(path, rva, length=0x400):
    pe = load(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_data(rva, length)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    return list(md.disasm(data, base + rva))
