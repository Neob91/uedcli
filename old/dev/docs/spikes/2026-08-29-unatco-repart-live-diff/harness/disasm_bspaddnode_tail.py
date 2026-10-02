"""Raw capstone disassembly of bspAddNode's vertex-pool-loop tail, to cross-check the angr
pseudo-C reading of a suspected wrap-around vertex dedup (drop the closing vertex if it equals
the first vertex, after already deduping consecutive-only duplicates during the loop) that
bspcsg.rs's own `bsp_add_node` (uedcli-native/src/bspcsg.rs ~322-337) does NOT implement.
"""
import pefile, capstone

pe = pefile.PE('uned/UED22/Editor.dll')
image_base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

start = 0x10035260
end = 0x10035400
rva_start = start - image_base
rva_end = end - image_base
code = data[rva_start:rva_end]

for insn in md.disasm(code, start):
    print(f"0x{insn.address:08x}: {insn.mnemonic} {insn.op_str}")
