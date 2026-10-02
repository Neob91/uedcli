"""Disassemble a VA range of Editor.dll (or any PE), annotating call targets with export names."""
import sys
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = sys.argv[1]
va = int(sys.argv[2], 16)
n = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x200

pef = pe.load(P)
base = pe.image_base(P)
exp = {base + rva: name for name, rva in pe.exports(P).items()}
off = pef.get_offset_from_rva(va - base)
code = pef.__data__[off:off + n]
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
for ins in md.disasm(code, va):
    ann = ""
    for op in ins.operands:
        if op.type == 2:  # imm
            if op.imm in exp:
                ann = "   ; " + exp[op.imm]
    print(f"{ins.address:#010x}  {ins.bytes.hex():<20} {ins.mnemonic:<8} {ins.op_str}{ann}")
