"""Linearly disassemble a function from its export RVA and print a window around a target VA,
so the instruction stream is correctly aligned (unlike starting mid-function)."""
import sys
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

P = sys.argv[1]
fn = int(sys.argv[2], 16)
target = int(sys.argv[3], 16)
before = int(sys.argv[4]) if len(sys.argv) > 4 else 40
after = int(sys.argv[5]) if len(sys.argv) > 5 else 40

pef = pe.load(P)
base = pe.image_base(P)
exp = {base + rva: n for n, rva in pe.exports(P).items()}
off = pef.get_offset_from_rva(fn - base)
code = pef.__data__[off:off + (target - fn) + 0x400]
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
ins = list(md.disasm(code, fn))
idx = None
for i, x in enumerate(ins):
    if x.address <= target < x.address + x.size:
        idx = i
        break
if idx is None:
    print(f"target {target:#x} not reached; stream ended at "
          f"{ins[-1].address:#x} after {len(ins)} insns")
    sys.exit(1)
for x in ins[max(0, idx - before): idx + after]:
    mark = "  <<<" if x.address == target else ""
    ann = ""
    for o in x.operands:
        if o.type == 2 and o.imm in exp:
            ann = "   ; " + exp[o.imm]
    print(f"{x.address:#010x}  {x.bytes.hex():<20} {x.mnemonic:<8} {x.op_str}{ann}{mark}")
