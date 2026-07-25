"""Disassemble the game's Render.dll URender::OccludeBsp iRenderBound guard.

Proves the "Anomalous singularity" root cause (section 50): the per-node bound test at
Render.dll RVA 0x17adb is `if (Node.iRenderBound(+0x30) == -1) skip; else index Model->Bounds
(Model+0xc0, FBox stride 28) and call BoundVisible`.  A node with iRenderBound != -1 while the
Bounds array is empty (Data == NULL) dereferences a null FBox -> AV in BoundVisible.

Run:  <uedctl>/.venv/bin/python render_bound_guard.py [path-to-Render.dll]
(needs `capstone` + `pefile` in the venv)
"""
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/neob91/Games/LutrisDX/drive_c/DX/System/Render.dll"

pe = pefile.PE(DLL)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
md = Cs(CS_ARCH_X86, CS_MODE_32)

# Resolve exports (member fns are incremental-link jmp thunks -> follow the first jmp).
def export_rva(substr):
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if e.name and substr.encode() in e.name:
            # thunk at e.address: `jmp <real>`
            for insn in md.disasm(data[e.address:e.address + 8], base + e.address):
                if insn.mnemonic == "jmp":
                    return int(insn.op_str, 16) - base
    raise KeyError(substr)

occlude = export_rva("OccludeBsp@URender")
print(f"ImageBase {base:#x}   OccludeBsp real RVA {occlude:#x}")
print("--- iRenderBound guard block (RVA 0x17ab0..0x17b60) ---")
for insn in md.disasm(data[0x17ab0:0x17ab0 + 0x140], base + 0x17ab0):
    print(f"  {insn.address - base:#08x}: {insn.mnemonic} {insn.op_str}")
