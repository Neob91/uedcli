#!/usr/bin/env python3
"""Disassemble a function (by export name or RVA) out of a UED22 PE, resolving
call targets to export names and .rdata float/double literals inline."""
import re
import sys

import capstone
import pefile

PATH = sys.argv[1]
WHAT = sys.argv[2]
NINS = int(sys.argv[3]) if len(sys.argv) > 3 else 400

pe = pefile.PE(PATH, fast_load=True)
pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
                           pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
base = pe.OPTIONAL_HEADER.ImageBase
exports = {}
try:
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if e.name:
            exports[e.address] = e.name.decode()
except AttributeError:
    pass

data = open(PATH, 'rb').read()
runs = {}
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){2,}\x00\x00', data):
    off = m.start()
    rva = pe.get_rva_from_offset(off)
    runs[rva] = m.group()[:-2].decode('utf-16le')


def sym(rva):
    if rva in exports:
        return exports[rva]
    return None


if WHAT.startswith('0x'):
    start = int(WHAT, 16)
else:
    start = next(a for a, n in exports.items() if WHAT in n)

code = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

import struct
out = []
addr = start
n = 0
while n < NINS:
    chunk = code[addr:addr + 16]
    ins = next(md.disasm(chunk, addr), None)
    if ins is None:
        break
    line = f"{ins.address:#08x}  {ins.mnemonic:<8} {ins.op_str}"
    ann = []
    for m in re.finditer(r'0x[0-9a-f]+', ins.op_str):
        v = int(m.group(), 16)
        rva = v - base if v > base else v
        s = sym(rva)
        if s:
            ann.append(s)
        if rva in runs:
            ann.append('STR:' + repr(runs[rva]))
        # float literal?
        if 0 < rva < len(code) - 8 and ins.mnemonic in ('fld', 'fmul', 'fadd', 'fsub',
                                                        'fdiv', 'fcomp', 'fdivr', 'fsubr',
                                                        'fcom', 'fmulp'):
            raw = code[rva:rva + 8]
            try:
                if 'dword' in ins.op_str:
                    ann.append('f32=%r' % struct.unpack('<f', raw[:4])[0])
                elif 'qword' in ins.op_str:
                    ann.append('f64=%r' % struct.unpack('<d', raw)[0])
            except Exception:
                pass
    if ann:
        line += '   ; ' + ' | '.join(ann)
    out.append(line)
    if ins.mnemonic == 'ret':
        break
    addr += ins.size
    n += 1

print('\n'.join(out))
