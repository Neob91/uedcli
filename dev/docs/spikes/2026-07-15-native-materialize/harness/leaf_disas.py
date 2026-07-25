import sys, struct
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/dev/docs/spikes/2026-07-15-native-materialize/harness")
import pe

G = '/home/neob91/Games/LutrisDX/drive_c/DX/System/Engine.dll'
base = pe.image_base(G)
exp = {base + r: n for n, r in pe.exports(G).items()}

def demangle_short(n):
    if n and n.startswith("?"):
        parts = n[1:].split("@@")[0].split("@")
        return "::".join(reversed([x for x in parts if x]))
    return n

# resolve thunk: if target is a jmp, follow once
def follow(va):
    ins = pe.disasm(G, va - base, 8)
    if ins and ins[0].mnemonic == "jmp" and ins[0].op_str.startswith("0x"):
        return int(ins[0].op_str, 16)
    return va

rva = int(sys.argv[1], 16)
length = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x600
va = base + rva
va = follow(va)
print(f"; function at {va:#x} (rva {va-base:#x})")
insns = pe.disasm(G, va - base, length)
depth = 0
for ins in insns:
    line = f"{ins.address:#08x}  {ins.mnemonic:<7} {ins.op_str}"
    ann = ""
    if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
        tgt = int(ins.op_str, 16)
        t2 = follow(tgt)
        nm = exp.get(t2) or exp.get(tgt)
        if nm:
            ann = "  ; " + demangle_short(nm)
    print(line + ann)
    if ins.mnemonic in ("ret", "retn") or ins.mnemonic.startswith("ret"):
        # keep going a little to catch tails, but mark
        pass
