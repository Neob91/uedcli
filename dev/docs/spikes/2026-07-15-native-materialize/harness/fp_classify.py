"""SPIKE 41 — classify the FP instruction mix of UED22 CSG hot functions.

Disassembles a function (by RVA) in Editor.dll/Engine.dll and buckets every
instruction into x87 (80-bit stack FPU) vs SSE/SSE2 scalar (32-bit XMM) vs
control-word/rounding manipulation. Decides whether the 1999 engine's CSG math
accumulates in 80-bit extended precision (x87) or true 32-bit (SSE).

Usage:
  fp_classify.py <dll> <rva_hex> <len_hex> [name]

Reuses the bspspike PE/capstone helpers (added to sys.path).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "..", "..", "bspspike"))
import pe

# --- instruction taxonomy -------------------------------------------------
# x87: legacy 80-bit stack FPU. Any of these => extended-precision intermediates.
X87 = {
    "fld","fst","fstp","fild","fist","fistp","fbld","fbstp",
    "fadd","faddp","fiadd","fsub","fsubp","fsubr","fsubrp","fisub","fisubr",
    "fmul","fmulp","fimul","fdiv","fdivp","fdivr","fdivrp","fidiv","fidivr",
    "fcom","fcomp","fcompp","fcomi","fcomip","fucom","fucomp","fucompp",
    "fucomi","fucomip","ficom","ficomp",
    "fabs","fchs","fsqrt","frndint","fscale","fprem","fprem1",
    "fxch","fld1","fldz","fldpi","fldln2","fldl2e","fldl2t","fldlg2",
    "fsin","fcos","fsincos","fptan","fpatan","f2xm1","fyl2x","fyl2xp1",
    "ftst","fxam","fdecstp","fincstp","ffree","fnop",
    "fcmovb","fcmove","fcmovbe","fcmovu","fcmovnb","fcmovne","fcmovnbe","fcmovnu",
}
# x87 control word / rounding manipulation (precision-control tricks)
X87_CTRL = {"fldcw","fnstcw","fstcw","fnstsw","fstsw","fldenv","fnstenv",
            "fstenv","fnsave","fsave","frstor","fnclex","fclex","finit","fninit"}
# SSE / SSE2 scalar single/double (32/64-bit true-width XMM)
SSE_SCALAR = {
    "movss","addss","subss","mulss","divss","sqrtss","comiss","ucomiss",
    "minss","maxss","rcpss","rsqrtss","cmpss","roundss",
    "movsd","addsd","subsd","mulsd","divsd","sqrtsd","comisd","ucomisd",
    "minsd","maxsd","cmpsd","roundsd",
    "cvtss2sd","cvtsd2ss","cvtsi2ss","cvtsi2sd","cvtss2si","cvtsd2si",
    "cvttss2si","cvttsd2si",
}
# SSE packed (vectorized) — also XMM, true-width
SSE_PACKED = {
    "movaps","movups","movlps","movhps","movlhps","movhlps","movmskps",
    "addps","subps","mulps","divps","sqrtps","rcpps","rsqrtps",
    "maxps","minps","cmpps","shufps","unpcklps","unpckhps","andps","andnps",
    "orps","xorps","movapd","movupd","addpd","subpd","mulpd","divpd",
    "cvtdq2ps","cvtps2dq","cvttps2dq","cvtpi2ps","cvtps2pi",
}

def classify(dll, rva, length, name):
    insns = pe.disasm(dll, rva, length)
    # stop at first ret (function boundary heuristic)
    fn = []
    for ins in insns:
        fn.append(ins)
        if ins.mnemonic in ("ret","retn"):
            break
    buckets = {"x87":[], "x87_ctrl":[], "sse_scalar":[], "sse_packed":[], "other_fp":[]}
    counts = {k:0 for k in buckets}
    for ins in fn:
        m = ins.mnemonic
        if m in X87:
            counts["x87"]+=1; buckets["x87"].append(m)
        elif m in X87_CTRL:
            counts["x87_ctrl"]+=1; buckets["x87_ctrl"].append((hex(ins.address),m,ins.op_str))
        elif m in SSE_SCALAR:
            counts["sse_scalar"]+=1; buckets["sse_scalar"].append(m)
        elif m in SSE_PACKED:
            counts["sse_packed"]+=1; buckets["sse_packed"].append(m)
        elif m.startswith("f") and m not in ("fs","fxsave","fxrstor"):
            counts["other_fp"]+=1; buckets["other_fp"].append(m)
    from collections import Counter
    print(f"=== {name}  rva={hex(rva)}  insns={len(fn)} ===")
    print(f"  x87        : {counts['x87']:4d}   {dict(Counter(buckets['x87']))}")
    print(f"  x87_ctrl   : {counts['x87_ctrl']:4d}   {buckets['x87_ctrl']}")
    print(f"  sse_scalar : {counts['sse_scalar']:4d}   {dict(Counter(buckets['sse_scalar']))}")
    print(f"  sse_packed : {counts['sse_packed']:4d}   {dict(Counter(buckets['sse_packed']))}")
    print(f"  other_fp   : {counts['other_fp']:4d}   {dict(Counter(buckets['other_fp']))}")
    verdict = "x87 (80-bit extended)" if counts["x87"]>counts["sse_scalar"]+counts["sse_packed"] \
              else "SSE (32-bit)" if counts["sse_scalar"]+counts["sse_packed"]>0 else "no-FP/indeterminate"
    print(f"  --> dominant FP model: {verdict}")
    return counts

if __name__ == "__main__":
    dll = sys.argv[1]; rva = int(sys.argv[2],16)
    length = int(sys.argv[3],16) if len(sys.argv)>3 else 0x800
    name = sys.argv[4] if len(sys.argv)>4 else hex(rva)
    classify(dll, rva, length, name)
