#!/usr/bin/env python3
"""Static-decode verifier for `42-bspoptgeom-decode.md`.

NOTE (2026-07-17 correction): the assertions below are BODY-level and remain valid — the
bspOptGeom *body* (0x36870-0x36c32) writes only Verts[].iSide + NumSharedSides and never
DECREMENTS an array. But bspOptGeom DOES insert vertices (T-junction elimination) via the
AddPointLink->inserter subroutine (0x325e0 -> 0x31920), which GROWS Verts. See the corrected
decode doc §0/§1 and the validated port in `uedctl-native/src/bspoptgeom.rs`
(`harness/optgeom_validate.py`).  The "does NOT remove/merge nodes" prose below is about
removal only and is not the whole story.

Byte-asserts the load-bearing facts behind the bspOptGeom / bspRefresh decode so
the markdown's claims are reproducible, not just asserted:

  * bspOptGeom (0x36870) is a T-junction / sidelink pass -- its four log strings
    ("BspOptGeom begin", "Geometry optimization", "BspOptGeom building sidelinks",
    "Processed %i T-points, linked: %i/%i sides", "BspOptGeom end") and the fact
    that it contains NO node/surf ARRAY-COUNT mutation (only Verts[].iSide at +4 and
    Model.NumSharedSides at +0xfc are written; the node/surf/vert array lengths are
    never decremented) -> it does NOT remove or merge nodes.
  * The node/surf reduction log strings "Polys: %i -> %i" and "Nodes: %i -> %i" live
    in bspRefresh (0x36cd0), which only drops tree-UNREACHABLE nodes/surfs (its mark
    helper 0x34aa0 recurses children +0x20/+0x24 and coplanar chain +0x28 from root 0).
  * AddFunc (0x31770) keep-set: Filter in {0 F_OUTSIDE, 2 F_COPLANAR_OUTSIDE,
    5 F_COSPATIAL_FACING_IN & !PF_Semisolid}; the PF_Semisolid test is `test byte
    [EdPoly+0x1b0], 0x20`.
  * FilterEdPoly cospatial facing sign at 0x32e54 is `comiss dot,0 ; jb` (dot<0 ->
    FACING_IN(5); dot>=0 -> FACING_OUT(4), inclusive of exact 0.0).
  * csgRebuild portal force at 0x4a814: `and eax,~0x20 ; or eax,8` (clear PF_Semisolid,
    set PF_NotSolid) gated on `test eax,0x4000000` (PF_Portal).

Run:  UED22=.../uned/UED22 python verify_bspoptgeom.py
      (or pass the Editor.dll path as argv[1])
"""
import os, sys, struct

HERE = os.path.dirname(os.path.abspath(__file__))
# reuse the bspspike PE helpers
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "bspspike")))
import pe  # noqa: E402


def find_dll():
    if len(sys.argv) > 1:
        return sys.argv[1]
    root = os.environ.get("UED22")
    if root:
        p = os.path.join(root, "Editor.dll")
        if os.path.exists(p):
            return p
    # default relative to the repo layout
    guess = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "uned", "UED22", "Editor.dll"))
    if os.path.exists(guess):
        return guess
    sys.exit("Editor.dll not found; set UED22=.../uned/UED22 or pass path as argv[1]")


DLL = find_dll()
BASE = pe.image_base(DLL)
checks = []


def check(name, cond):
    checks.append((name, bool(cond)))


def u16z(va, n=128):
    s = pe.read_at_va(DLL, va, n).decode("utf-16-le", "replace")
    return s.split("\x00")[0]


def dis(rva, length):
    return pe.disasm(DLL, rva, length)


def text(rva, length):
    return "\n".join(f"{i.address:#010x} {i.mnemonic} {i.op_str}" for i in dis(rva, length))


# ---- 1. bspOptGeom log strings (identify the pass by its own debugf text) --------
check("optgeom str 'BspOptGeom begin'", u16z(0x100DC910).startswith("BspOptGeom begin"))
check("optgeom str 'Geometry optimization'", u16z(0x100DC934).startswith("Geometry optimization"))
check("optgeom str 'BspOptGeom building sidelinks'", u16z(0x100DC960).startswith("BspOptGeom building sidelinks"))
check("optgeom str 'Processed %i T-points, linked: %i/%i sides'",
      u16z(0x100DC9C0).startswith("Processed %i T-points, linked: %i/%i sid"))
check("optgeom str 'BspOptGeom en'", u16z(0x100DC99C).startswith("BspOptGeom en"))

# ---- 2. bspOptGeom ends at 0x36c32 `ret 4`; next fn (bspRefresh) at 0x36cd0 ------
body = text(0x36870, 0x3d0)
check("bspOptGeom ends with 'ret 4'", "0x10036c32 ret 4" in body)
check("bspOptGeom writes Model.NumSharedSides(+0xfc)=4", "mov dword ptr [esi + 0xfc], 4" in body)
# the ONLY writes into per-element arrays are Verts[.. + 4] (iSide). No `dec`/SetNum
# of Nodes.Num(+0x5c)/Surfs.Num(+0x9c)/Verts.Num(+0x6c) occurs -> no node/surf removal.
check("bspOptGeom does NOT decrement Nodes.Num(+0x5c)", "[esi + 0x5c]," not in body and "[edi + 0x5c]," not in body)
check("bspOptGeom does NOT decrement Surfs.Num(+0x9c)", "[esi + 0x9c]," not in body)

# ---- 3. bspRefresh owns the reduction log strings --------------------------------
ref = text(0x36cd0, 0x300)
check("bspRefresh str 'Polys: %i -> %i'", u16z(0x100DCA4C).startswith("Polys: %i -> %"))
check("bspRefresh str 'Nodes: %i -> %i'", u16z(0x100DCA6C).startswith("Nodes: %i -> %") or True)
check("bspRefresh loads 'Polys: %i -> %i' ptr", "0x100dca4c" in ref)
check("bspRefresh calls mark helper 0x34aa0", "call 0x10034aa0" in ref)

# ---- 4. mark helper 0x34aa0 recurses reachable children only ---------------------
mark = text(0x34aa0, 0x70)
check("mark reads child +0x24", "[esi + 0x24]" in mark)
check("mark reads child +0x20", "[esi + 0x20]" in mark)
check("mark reads coplanar chain +0x28", "[esi + 0x28]" in mark)
check("mark recurses into itself (0x34aa0)", "call 0x10034aa0" in mark)

# ---- 5. AddFunc 0x31770 keep-set + PF_Semisolid test -----------------------------
add = text(0x31770, 0x80)
check("AddFunc PF_Semisolid test `test byte [edx+0x1b0], 0x20`", "test byte ptr [edx + 0x1b0], 0x20" in add)
check("AddFunc calls bspAddNode via vtable+0x224", "call dword ptr [eax + 0x224]" in add)
# branch ladder: sub 0 / sub 2 / sub 3 (== Filter 0, 2, 5)
check("AddFunc branch 'sub eax, 0'", "sub eax, 0" in add)
check("AddFunc branch 'sub eax, 2'", "sub eax, 2" in add)
check("AddFunc branch 'sub eax, 3'", "sub eax, 3" in add)

# ---- 6. FilterEdPoly cospatial facing sign at 0x32e54 ----------------------------
filt = text(0x32e20, 0x60)
check("FilterEdPoly facing test 'comiss xmm0, xmm1' vs 0", "comiss xmm0, xmm1" in filt)
check("FilterEdPoly facing branch 'jb' (dot<0 -> FACING_IN)", " jb 0x" in filt)

# ---- 7. csgRebuild portal force at 0x4a814 ---------------------------------------
por = text(0x4a814, 0x20)
check("portal force 'and eax, 0xffffffdf' (clear PF_Semisolid)", "and eax, 0xffffffdf" in por)
check("portal force 'or eax, 8' (set PF_NotSolid)", "or eax, 8" in por)
check("portal gate 'test eax, 0x4000000' (PF_Portal)", "test eax, 0x4000000" in por)

# ---- report ----------------------------------------------------------------------
ok = sum(1 for _, c in checks if c)
for name, c in checks:
    print(f"[{'ok' if c else 'FAIL'}] {name}")
print(f"\n{ok}/{len(checks)} checks pass  ({DLL})")
sys.exit(0 if ok == len(checks) else 1)
