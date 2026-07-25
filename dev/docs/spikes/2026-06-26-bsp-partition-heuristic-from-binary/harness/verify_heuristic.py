"""Re-verify, against the actual UED22 binaries, every load-bearing fact this spike asserts
about the BSP partition-plane heuristic (`FindBestSplit` / `SplitWithPlaneFast` / the
`MAP REBUILD` defaults). Pure static disassembly — never runs the editor.

Each check pins a SPECIFIC byte sequence or instruction at a SPECIFIC address, so if a future
substrate swap changes the binary the assertion fails loudly rather than the doc silently
going stale. Run:

    UED22=/home/human/src/dx_lum/Tools/uedctl/uned/UED22 \
        python verify_heuristic.py

Prints one line per check; exits non-zero on any mismatch.
"""
from __future__ import annotations

import os
import sys

import pe

UED22 = os.environ.get("UED22", "/home/human/src/dx_lum/Tools/uedctl/uned/UED22")
EDITOR = os.path.join(UED22, "Editor.dll")
ENGINE = os.path.join(UED22, "Engine.dll")

_fails = 0


def check(name: str, got, want) -> None:
    global _fails
    ok = got == want
    flag = "ok " if ok else "FAIL"
    print(f"[{flag}] {name}: got={got!r} want={want!r}")
    if not ok:
        _fails += 1


def bytes_at(path, va, n):
    return pe.read_at_va(path, va, n).hex()


def main() -> int:
    # --- Editor.dll image base ---
    check("Editor.dll image base", hex(pe.image_base(EDITOR)), "0x10000000")
    check("Engine.dll image base", hex(pe.image_base(ENGINE)), "0x10000000")

    # --- THRESH_SPLIT_POLY_WITH_PLANE = 0.25 (the front/back band) ---
    check("Engine 0x10206780 = +0.25", pe.read_float_va(ENGINE, 0x10206780), 0.25)
    check("Engine 0x1020b580 = -0.25", pe.read_float_va(ENGINE, 0x1020b580), -0.25)

    # --- the score constant 100.0 (shared by FindBestSplit + the PortalBias /100) ---
    check("Editor 0x100dcb38 = 100.0", pe.read_float_va(EDITOR, 0x100dcb38), 100.0)

    # --- FindBestSplit: the score formula instructions (Editor 0x335d0) ---
    # SSE scalar ops carry the f3 REP prefix: f3 0f <op> <modrm>.
    # subss xmm2, xmm1  (100 - Balance)
    check("0x10033853 subss xmm2,xmm1", bytes_at(EDITOR, 0x10033853, 4), "f30f5cd1")
    # mulss xmm2, xmm0  ((100-Balance)*Splits)
    check("0x1003385e mulss xmm2,xmm0", bytes_at(EDITOR, 0x1003385e, 4), "f30f59d0")
    # mulss xmm0, xmm1  (Balance * |Front-Back|)
    check("0x10033874 mulss xmm0,xmm1", bytes_at(EDITOR, 0x10033874, 4), "f30f59c1")
    # addss xmm0, xmm2  (sum)
    check("0x10033878 addss xmm0,xmm2", bytes_at(EDITOR, 0x10033878, 4), "f30f58c2")

    # --- portal CANDIDATE bonus: test PF_Portal on the candidate, mulss PortalBias, subss ---
    check("0x10033881 PF_Portal test on candidate", bytes_at(EDITOR, 0x10033881, 10),
          "f783b001000000000004")
    check("0x1003388d mulss xmm2,[ebp-0x50] (PortalBias)",
          bytes_at(EDITOR, 0x1003388d, 5), "f30f5955b0")
    check("0x10033892 subss xmm0,xmm2", bytes_at(EDITOR, 0x10033892, 4), "f30f5cc2")

    # --- portal SPLIT penalty x16 (Editor 0x33814 + 0x33832) ---
    check("0x10033814 test [eax+0x1b0],0x4000000",
          bytes_at(EDITOR, 0x10033814, 10), "f780b001000000000004")
    # add eax, 0x10  (portal split adds 16 to Splits)
    check("0x10033832 add eax,0x10", bytes_at(EDITOR, 0x10033832, 3), "83c010")

    # --- structural-splitter prepass + candidate skip (the §4.1 open item, now closed) ---
    # prepass: test byte [eax+0x1b0], 0x28  (PF_Semisolid|PF_NotSolid)
    check("0x100336dc prepass test byte[+0x1b0],0x28",
          bytes_at(EDITOR, 0x100336dc, 7), "f680b001000028")
    # candidate skip: test al, 0x28  then  test eax, 0x4000000
    check("0x10033751 cand test al,0x28", bytes_at(EDITOR, 0x10033751, 2), "a828")
    check("0x10033755 cand test eax,0x4000000", bytes_at(EDITOR, 0x10033755, 5),
          "a900000004")

    # --- SplitWithPlaneFast classification thresholds (Engine 0x151f90) ---
    # front flag set only if d > +0.25:  comiss xmm0,[0x10206780]; jbe (skip)
    check("0x1015202f comiss xmm0,[0.25]", bytes_at(ENGINE, 0x1015202f, 7),
          "0f2f0580672010")
    # back flag set only if d < -0.25:  comiss xmm1(-0.25),xmm0; cmova
    check("0x10152051 movss xmm1,[-0.25]", bytes_at(ENGINE, 0x10152051, 8),
          "f30f100d80b52010")
    # indirect call into SplitWithPlaneFast from FindBestSplit's classify loop
    check("0x100337bc call [Engine!SplitWithPlaneFast]",
          bytes_at(EDITOR, 0x100337bc, 6), "ff1530ee0c10")

    # --- the SplitWithPlaneFast return->counter jump table (Editor 0x33934) ---
    jt = [pe.read_u32_va(EDITOR, 0x10033934 + 4 * k) for k in range(4)]
    check("classify jump table (Coplanar/Front/Back/Split targets)",
          [hex(x) for x in jt],
          ["0x100337ce", "0x100337df", "0x100337fa", "0x1003380e"])

    # --- MAP REBUILD defaults: Balance=50 (0x32), PortalBias=70 (0x46), packed <<8 ---
    # mov edx, 0x32 ; cmove ecx, edx   (Balance default)
    check("0x1006530b mov edx,0x32 (Balance=50)", bytes_at(EDITOR, 0x1006530b, 5),
          "ba32000000")
    # mov edx, 0x46 ; cmove ecx, edx   (PortalBias default)
    check("0x1006533c mov edx,0x46 (PortalBias=70)", bytes_at(EDITOR, 0x1006533c, 5),
          "ba46000000")
    # shl ecx, 8  (pack PortalBias into the high byte)
    check("0x1006534c shl ecx,8 (pack PortalBias<<8)", bytes_at(EDITOR, 0x1006534c, 3),
          "c1e108")

    print()
    if _fails:
        print(f"{_fails} CHECK(S) FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
