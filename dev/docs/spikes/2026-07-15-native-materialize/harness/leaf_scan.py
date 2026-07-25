import sys
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

def follow(va):
    try:
        ins = pe.disasm(G, va - base, 8)
    except Exception:
        return va
    if ins and ins[0].mnemonic == "jmp" and ins[0].op_str.startswith("0x"):
        return int(ins[0].op_str, 16)
    return va

def func_end(insns):
    # crude: cut at first ret that is not followed by more code we care about
    out = []
    for ins in insns:
        out.append(ins)
        if ins.mnemonic.startswith("ret"):
            break
    return out

# offsets of interest in FBspNode (mem) and UModel
INTEREST = {
    0x20: "iChild0", 0x24: "iChild1", 0x28: "iPlane",
    0x2c: "iCollisionBound", 0x30: "iRenderBound",
    0x34: "iZone0", 0x35: "iZone1", 0x36: "NumVertices",
    0x38: "iLeaf0", 0x3c: "iLeaf1",
    0xc0: "Model.Bounds", 0xcc: "Model.LeafHulls", 0xd8: "Model.Leaves?",
}

def scan(rva, depth, seen, label=""):
    va = follow(base + rva)
    if va in seen:
        return
    seen.add(va)
    nm = exp.get(va)
    name = demangle_short(nm) if nm else f"sub_{va:#x}"
    try:
        insns = func_end(pe.disasm(G, va - base, 0x1500))
    except Exception:
        return
    calls = []
    for ins in insns:
        ops = ins.op_str
        # displacement accesses
        for off, tag in INTEREST.items():
            for pat in (f"+ {hex(off)}]", f"+ {off}]" if off < 10 else None):
                if pat and pat in ops:
                    print(f"  [{name}] {ins.address:#x}  {ins.mnemonic} {ops}   <-- {tag}")
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            calls.append(int(ins.op_str, 16))
    if depth > 0:
        for c in calls:
            scan(c - base, depth - 1, seen)

print("### scanning", sys.argv[1])
scan(int(sys.argv[1], 16), int(sys.argv[2]) if len(sys.argv) > 2 else 2, set())
