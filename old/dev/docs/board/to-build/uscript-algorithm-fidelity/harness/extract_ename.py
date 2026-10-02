"""Extract a substrate's intrinsic `EName` name-registration order from its `core.dll`.

This is the base of the global `FName` registration order UCC uses for name-table tie-breaks
(the first N names of `GObjNames`, before any package load). Per-substrate: point it at the TARGET
substrate's `core.dll` (UED22/OldUnreal, UT99, DXORIG each differ). It is a real computation over the
binary, not a baked list.

Mechanism (UE1): Core registers its hardcoded names at boot via a `RegisterNames()` routine full of
inline `new(TEXT("<name>"),(EName)<n>) FName;` constructions — one per `REGISTER_NAME` in `UnNames.h`,
in source (= index) order. The names are UTF-16LE literals in `.rdata`; the routine `push`es each
literal's address in order. We locate the routine by the cluster of `push <wide "ByteProperty">`
(EName #1) and disassemble forward, collecting each `push <addr-of-a-wide-identifier>` until the
routine returns. The resulting sequence is the EName table in index order (verified: [0]="None").

Usage:  python3 extract_ename.py <path/to/core.dll>   # prints one name per line
Deps:   pip install capstone pefile
"""
import re
import struct
import sys

import capstone
import pefile

_SEED = "ByteProperty"   # EName #1 — its wide-string `push` anchors the registration routine


def _wide_va(data: bytes, off2va, name: str) -> list[int]:
    pat = b"".join(bytes([ord(c), 0]) for c in name) + b"\x00\x00"
    out, idx = [], data.find(pat)
    while idx >= 0:
        va = off2va(idx)
        if va is not None:
            out.append(va)
        idx = data.find(pat, idx + 1)
    return out


def extract(dll_path: str) -> list[str]:
    pe = pefile.PE(dll_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.__data__
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.SizeOfRawData, s.PointerToRawData)
            for s in pe.sections]

    def va2off(va: int):
        rva = va - base
        for vaddr, vsz, rsz, praw in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                o = praw + (rva - vaddr)
                return o if o < len(data) else None
        return None

    def off2va(o: int):
        for vaddr, vsz, rsz, praw in secs:
            if praw <= o < praw + rsz:
                return base + vaddr + (o - praw)
        return None

    def read_wstr(va: int):
        o = va2off(va)
        if o is None:
            return None
        end = data.find(b"\x00\x00", o)
        if end < 0:
            return None
        if (end - o) % 2:
            end += 1
        try:
            s = data[o:end].decode("utf-16le")
        except UnicodeDecodeError:
            return None
        return s if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s) else None

    # Find the registration routine: a `push <addr>` where addr is the wide "ByteProperty" literal.
    text = next(s for s in pe.sections if s.Name.rstrip(b"\x00") == b".text")
    tpraw, tsz = text.PointerToRawData, text.SizeOfRawData
    anchor = None
    for seed_va in _wide_va(data, off2va, _SEED):
        idx = data.find(b"\x68" + struct.pack("<I", seed_va))      # push imm32 == seed_va
        while idx >= 0:
            if tpraw <= idx < tpraw + tsz:
                anchor = off2va(idx)
                break
            idx = data.find(b"\x68" + struct.pack("<I", seed_va), idx + 1)
        if anchor is not None:
            break
    if anchor is None:
        raise SystemExit(f"registration routine not found (no push of {_SEED!r} wide literal)")

    # Disassemble forward from a little before the anchor; collect push-of-wide-identifier in order
    # until the enclosing routine returns.
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    start = anchor - 0x60
    code = data[va2off(start):va2off(start) + 0x4000]
    names, last_push = [], start
    for insn in md.disasm(code, start):
        if insn.mnemonic == "push" and insn.op_str.startswith("0x"):
            s = read_wstr(int(insn.op_str, 16))
            if s:
                names.append(s)
                last_push = insn.address
        elif insn.mnemonic == "ret" and insn.address > last_push and names:
            break
    if not names or names[0] != "None":
        raise SystemExit(f"unexpected EName sequence (starts {names[:3]}, want None@0)")
    return names


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for n in extract(sys.argv[1]):
        print(n)
