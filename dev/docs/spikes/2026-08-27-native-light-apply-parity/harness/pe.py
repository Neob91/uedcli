"""Shared PE helpers: export map, RVA<->offset, capstone disassembly, float reads."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

_cache = {}

def load(path):
    if path not in _cache:
        pe = pefile.PE(path, fast_load=False)
        _cache[path] = pe
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
    pe = load(path)
    return pe.get_offset_from_rva(va - image_base(path))

def read_at_va(path, va, n):
    off = va_to_offset(path, va)
    return load(path).__data__[off:off+n]

def read_float_va(path, va):
    import struct
    return struct.unpack("<f", read_at_va(path, va, 4))[0]

def read_double_va(path, va):
    import struct
    return struct.unpack("<d", read_at_va(path, va, 8))[0]

def disasm(path, rva, length=0x600):
    """Disassemble `length` bytes starting at export RVA. Returns list of capstone insns."""
    pe = load(path)
    base = image_base(path)
    off = pe.get_offset_from_rva(rva)
    code = pe.__data__[off:off+length]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    return list(md.disasm(code, base + rva))

def disasm_func(path, rva, max_len=0x1200):
    """Disassemble until the balancing ret (stops at first ret at call-depth heuristics:
    simply stop at the first 0xC3/0xC2 ret encountered after prologue)."""
    insns = disasm(path, rva, max_len)
    out = []
    for ins in insns:
        out.append(ins)
        if ins.mnemonic in ("ret", "retn") or ins.bytes[0] in (0xC3, 0xC2):
            break
    return out
