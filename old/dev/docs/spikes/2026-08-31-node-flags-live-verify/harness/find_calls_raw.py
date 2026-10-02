#!/usr/bin/env python3
"""Raw byte-pattern scan (alignment-independent) for every `E8 <rel32>` (call rel32) encoding
anywhere in Editor.dll whose computed target == bspAddNode (0x10034e80). Linear capstone disasm
of the whole .text found ZERO direct calls -- either bspAddNode is called only indirectly
(vtable/function-pointer), or misaligned linear disasm desync hid the E8 bytes. This raw scan is
immune to both: it just looks at every possible byte offset for the E8 opcode + a rel32 that
resolves to the target, regardless of instruction alignment."""
import struct
import pefile

DLL = "uned/UED22/Editor.dll"
IMAGE_BASE = 0x10000000
TARGET = 0x10034e80

pe = pefile.PE(DLL, fast_load=True)
text = None
for s in pe.sections:
    if s.Name.startswith(b".text"):
        text = s
        break
data = text.get_data()
va_start = text.VirtualAddress + IMAGE_BASE

hits = []
for i in range(len(data) - 5):
    if data[i] != 0xE8:
        continue
    rel = struct.unpack_from("<i", data, i + 1)[0]
    call_va = va_start + i
    target = (call_va + 5) + rel
    if target == TARGET:
        hits.append(call_va)

print(f"raw E8-scan: {len(hits)} byte-offsets decode as `call bspAddNode` (may include false positives from misaligned scan, e.g. inside another instruction's immediate)")
for h in hits:
    print(f"  {h:#x}")
