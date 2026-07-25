"""SPIKE 41 — whole-.text FP-model census.

Linear-sweep disassemble the entire .text section and tally x87 vs SSE-scalar
vs SSE-packed mnemonics, plus any x87 control-word (rounding/precision) ops.
A near-total absence of x87 across the binary confirms the build is SSE-scalar
(true-32-bit) end-to-end, so a Rust f32 port can be bit-exact.

Linear sweep over a stripped .text will mis-decode some data/padding, but the
AGGREGATE ratio between x87 and SSE mnemonics is robust to that noise.

Usage: fp_scan_text.py <dll>
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bspspike"))
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from collections import Counter

X87_ARITH = {"fld","fst","fstp","fadd","faddp","fsub","fsubp","fsubr","fsubrp",
    "fmul","fmulp","fdiv","fdivp","fdivr","fdivrp","fcom","fcomp","fcompp",
    "fcomi","fcomip","fucom","fucomp","fucomi","fabs","fchs","fsqrt","fild",
    "fistp","fist","fxch","fld1","fldz","fldpi","fprem","frndint","fscale"}
X87_CTRL = {"fldcw","fnstcw","fstcw","fnstsw","fstsw","fldenv","fnstenv",
    "finit","fninit","fnclex"}
SSE_SCALAR = {"movss","addss","subss","mulss","divss","sqrtss","comiss",
    "ucomiss","minss","maxss","cvtss2sd","cvtsd2ss","cvtsi2ss","cvttss2si",
    "cvtss2si","movsd","addsd","subsd","mulsd","divsd","comisd","ucomisd",
    "cvtsi2sd","cvttsd2si"}
SSE_PACKED = {"movaps","movups","addps","subps","mulps","divps","xorps","andps",
    "orps","andnps","shufps","unpcklps","unpckhps","movlps","movhps","cvtdq2ps",
    "cvtps2dq","cvttps2dq","sqrtps","rcpps","maxps","minps"}
FMA = {"vfmadd132ss","vfmadd213ss","vfmadd231ss","vfmadd132ps","vfmadd213ps",
    "vfmadd231ps","vfmsub231ss","vfnmadd231ss"}

def scan(path):
    p = pe.load(path)
    base = p.OPTIONAL_HEADER.ImageBase
    sec = next(s for s in p.sections if s.Name.rstrip(b"\x00")==b".text")
    off = sec.PointerToRawData
    size = min(sec.Misc_VirtualSize, sec.SizeOfRawData)
    code = p.__data__[off:off+size]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    c = Counter()
    x87ctrl = Counter(); fma = Counter()
    for ins in md.disasm(code, base + sec.VirtualAddress):
        m = ins.mnemonic
        if m in X87_ARITH: c["x87_arith"]+=1
        elif m in X87_CTRL: c["x87_ctrl"]+=1; x87ctrl[m]+=1
        elif m in SSE_SCALAR: c["sse_scalar"]+=1
        elif m in SSE_PACKED: c["sse_packed"]+=1
        elif m in FMA: c["fma"]+=1; fma[m]+=1
    print(f"=== {path.split('/')[-1]}  .text sweep ({size} bytes) ===")
    for k in ("x87_arith","x87_ctrl","sse_scalar","sse_packed","fma"):
        print(f"  {k:12s}: {c[k]}")
    print(f"  x87_ctrl breakdown: {dict(x87ctrl)}")
    print(f"  fma breakdown     : {dict(fma)}")
    tot_sse = c["sse_scalar"]+c["sse_packed"]
    print(f"  SSE:x87_arith ratio = {tot_sse}:{c['x87_arith']}"
          f"  ({tot_sse/max(1,c['x87_arith']):.0f}x)")

if __name__=="__main__":
    scan(sys.argv[1])
