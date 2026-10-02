"""Dump flag-mask ops (test/and/or/cmp/xor with immediates) + calls, for flag RE."""
import sys
import pe

p = sys.argv[1]
rva = int(sys.argv[2], 16)
length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x600
base = pe.image_base(p)

exp = {base + r: n for n, r in pe.exports(p).items()}
iat = {}
pp = pe.load(p)
if hasattr(pp, "DIRECTORY_ENTRY_IMPORT"):
    for entry in pp.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode("latin1")
        for imp in entry.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode('latin1')}"

def short(n):
    if n.startswith("?"):
        return "::".join(reversed([x for x in n[1:].split("@@")[0].split("@") if x]))
    return n

# Known UE1 PolyFlags (PF_) and NodeFlags (NF_)
PF = {0x1:"PF_Invisible",0x2:"PF_Masked",0x4:"PF_Translucent",0x8:"PF_NotSolid",
      0x10:"PF_Environment",0x20:"PF_Semisolid",0x40:"PF_Modulated",0x80:"PF_FakeBackdrop",
      0x100:"PF_TwoSided",0x200:"PF_AutoUPan",0x400:"PF_AutoVPan",0x800:"PF_NoSmooth",
      0x1000:"PF_BigWavy",0x8000:"PF_Unlit",0x10000:"PF_HighShadowDetail",0x20000:"PF_Portal",
      0x40000:"PF_Mirror",0x100000:"PF_Flat",0x400000:"PF_LowShadowDetail",0x800000:"PF_NoMerge",
      0x1000000:"PF_AlphaTexture",0x2000000:"PF_DirtyShadows",0x4000000:"PF_BrightCorners",
      0x8000000:"PF_SpecialLit",0x20000000:"PF_NoBoundRejection",0x40000000:"PF_Unlit2",
      0x80000000:"PF_Selected"}
NF = {0x1:"NF_NotCsg",0x2:"NF_ShootThrough",0x4:"NF_NotVisBlocking",0x8:"NF_PolyOccluded",
      0x10:"NF_BoxOccluded",0x100:"NF_BrightCorners",0x200:"NF_IsNew",0x400:"NF_IsFront",
      0x800:"NF_IsBack"}

insns = pe.disasm(p, rva, length)
for ins in insns:
    line = f"{ins.address:#08x}  {ins.mnemonic:<7} {ins.op_str}"
    ann = ""
    if ins.mnemonic == "call":
        op = ins.operands[0]
        if op.type == 2 and (op.imm & 0xffffffff) in exp:
            ann = "   ; -> " + short(exp[op.imm & 0xffffffff])
        elif op.type == 3 and op.mem.base == 0 and op.mem.disp and (op.mem.disp & 0xffffffff) in iat:
            ann = "   ; -> " + iat[op.mem.disp & 0xffffffff]
    elif ins.mnemonic in ("test","and","or","cmp","xor","mov") and ins.operands:
        for op in ins.operands:
            if op.type == 2:  # imm
                v = op.imm & 0xffffffff
                if v in PF or v in NF:
                    ann = f"   ; {PF.get(v,'')} {NF.get(v,'')}".rstrip()
    print(line + ann)
    if ins.mnemonic in ("ret","retn") and "nostop" not in sys.argv:
        break
