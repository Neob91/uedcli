"""Pins the two UED22 facts the WanChai N31 / N35 ladder steps turned up (2026-09-05).

Both were found as parity failures and fixed by matching the editor's algorithm, so a drift in
either binary fact silently invalidates the fix:

1. `URender::OccludeBsp` (`render.dll 0x18e10`) RECOMPUTES `IsFront` from each coplanar chain
   member's own plane on the chain advance. A member can carry the flipped plane, with its `iZone`
   pair swapped to match, so inheriting the head's `IsFront` reads the wrong side's zone for the
   step-10 reachability test — which dropped four lit floor surfs at WanChai N31.
   Fix: `visible_surfs.rs::traverse`.

2. `csgRebuild` (`Editor.dll 0x4a650`) ends with a `bspRepartition` per grown frontier slot, then
   only `bspOptGeom` + `bspBuildBounds` — nothing rebuilds `Model->Polys` after. And
   `bspRepartition` (`0x49fc0`) is `bspBuildFPolys` -> `bspMergeCoplanars` -> `bspBuild` ->
   `bspRefresh`, the first of which empties and refills `Model->Polys` (`Model+0x54`). So the saved
   world soup is the LAST frontier call's, which only diverges once a level has a detail brush —
   WanChai N35's first semisolid Add. Fix: `bspcsg.rs::repartition_frontier`.

Run just this file (project rule: never the whole suite):
  TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider \\
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/test_wanchai_n31_n35_facts.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))

ED = ROOT / "uned/UED22/Editor.dll"
RD = ROOT / "uned/UED22/render.dll"
# UEditorEngine's vtable, located by the slot that holds `bspBrushCSG` (asserted below).
EDITOR_VTABLE_RVA = 0xCF5D4


@pytest.fixture(scope="module")
def pe_mod():
    if not (ED.exists() and RD.exists()):
        pytest.skip("UED22 DLLs not present")
    try:
        import pe
    except Exception:
        pytest.skip("pe.py / pefile+capstone unavailable")
    return pe


def _slot(pe, rva: int) -> int:
    """The absolute VA in UEditorEngine's vtable at byte offset `rva`."""
    return struct.unpack("<I", pe.read_at_va(str(ED), pe.image_base(str(ED))
                                             + EDITOR_VTABLE_RVA + rva, 4))[0]


def test_occludebsp_recomputes_isfront_per_coplanar_member(pe_mod):
    pe = pe_mod
    # chain advance: load iPlane (+0x28) off the CURRENT node, index Model->Nodes, become current
    assert pe.read_at_va(str(RD), 0x1001A7F1, 3).hex() == "8b7028"          # mov esi,[eax+0x28]
    assert pe.read_at_va(str(RD), 0x1001A934, 5).hex() == "8bc6c1e006"      # mov eax,esi; shl eax,6
    # ... then PlaneDot(member's own plane) / comiss vs 0.0 / seta -> IsFront, into the SAME slot
    # ([ebp-0x8dc]) the chain head writes at 0x100196c9, and re-enter the per-node filters.
    assert pe.read_at_va(str(RD), 0x1001A954, 6).hex() == "ff15e4400310"  # call FPlane::PlaneDot
    assert pe.read_at_va(str(RD), 0x1001A96A, 7).hex() == "0f2f053c510310"  # comiss xmm0,[0x1003513c]
    assert pe.read_at_va(str(RD), 0x1001A971, 3).hex() == "0f97c1"          # seta cl
    assert pe.read_at_va(str(RD), 0x1001A974, 6).hex() == "898d24f7ffff"    # mov [ebp-0x8dc],ecx
    assert pe.read_at_va(str(RD), 0x100196C9, 6).hex() == "898d24f7ffff"    # the head's own write
    assert pe.read_at_va(str(RD), 0x1001A986, 5).hex() == "e915efffff"      # jmp 0x100198a0


def test_csgrebuild_leaves_model_polys_to_the_frontier_repartition(pe_mod):
    pe = pe_mod
    base = pe.image_base(str(ED))
    rev = {base + rva: name for name, rva in pe.exports(str(ED)).items()}
    slots = {off: rev.get(_slot(pe, off), "?") for off in
             (0x1EC, 0x1FC, 0x200, 0x208, 0x20C, 0x210, 0x214, 0x218)}
    assert "bspBrushCSG" in slots[0x214]        # anchors the vtable address itself
    assert "bspRepartition" in slots[0x1EC]
    assert "bspBuildFPolys" in slots[0x20C]
    assert "bspMergeCoplanars" in slots[0x210]
    assert "bspBuild@" in slots[0x1FC]
    assert "bspRefresh" in slots[0x200]
    assert "bspOptGeom" in slots[0x218]
    assert "bspBuildBounds" in slots[0x208]

    # bspRepartition = bspBuildFPolys(Model,1,iNode) -> bspMergeCoplanars -> bspBuild -> bspRefresh
    assert pe.read_at_va(str(ED), 0x1004A007, 6).hex() == "ff920c020000"   # call [edx+0x20c]
    assert pe.read_at_va(str(ED), 0x1004A021, 6).hex() == "ff9210020000"   # call [edx+0x210]
    assert pe.read_at_va(str(ED), 0x1004A041, 6).hex() == "ff92fc010000"   # call [edx+0x1fc]
    assert pe.read_at_va(str(ED), 0x1004A059, 6).hex() == "ff9200020000"   # call [edx+0x200]
    # bspBuildFPolys EMPTIES Model->Polys (Model+0x54, its Element TArray at +0x28) before refilling
    assert pe.read_at_va(str(ED), 0x100360C7, 6).hex() == "8b4e5483c128"

    # csgRebuild's tail: the two frontier bspRepartition loops, then ONLY bspOptGeom/bspBuildBounds
    assert pe.read_at_va(str(ED), 0x1004AA3F, 6).hex() == "ff90ec010000"    # call [eax+0x1ec]
    assert pe.read_at_va(str(ED), 0x1004AA90, 6).hex() == "ff90ec010000"
    assert pe.read_at_va(str(ED), 0x1004AAB0, 6).hex() == "ff9018020000"    # call [eax+0x218]
    assert pe.read_at_va(str(ED), 0x1004AAC0, 6).hex() == "ff9008020000"    # call [eax+0x208]
    # ... and both frontier calls pass Simple=2, the arg SplitPolyList tests below.
    assert pe.read_at_va(str(ED), 0x1004AA3B, 2).hex() == "6a02"            # push 2
    assert pe.read_at_va(str(ED), 0x1004AA8C, 2).hex() == "6a02"


def test_splitpolylist_reseeds_a_fresh_surf_per_splitter(pe_mod):
    """The rule the frontier soup's saved iLinks follow (`bspcsg.rs::repartition_frontier`)."""
    pe = pe_mod
    # SplitPolyList (0x34530), arg +0x24 = RebuildSimplePolys: non-zero -> the SPLITTER takes
    # `Model->Surfs.Num()` (Model+0x9c) in its iLink (FPoly+0x1c4) ...
    assert pe.read_at_va(str(ED), 0x100345CF, 3).hex() == "395d24"          # cmp [ebp+0x24],ebx(0)
    assert pe.read_at_va(str(ED), 0x100345D4, 12).hex() == "8b8f9c000000898ac4010000"
    # ... each COPLANAR takes `Surfs.Num()-1`, sharing it ...
    assert pe.read_at_va(str(ED), 0x1003468C, 4).hex() == "837d2400"        # cmp [ebp+0x24],0
    assert pe.read_at_va(str(ED), 0x10034692, 16).hex() == "8b45088b809c000000488987c4010000"
    # ... and `bspAddNode` (0x34e80) allocates the surf iff iLink == Surfs.Num().
    assert pe.read_at_va(str(ED), 0x10034EE3, 6).hex() == "3b819c000000"
    # bspRepartition's own bspRefresh gets NoRemapSurfs=1, whose branch only memzeroes the poly-ref
    # table (0x10036d62/0x10036d68) — no surf is dropped there; bspOptGeom's bspRefresh(Model,0)
    # (0x100368ef `push 0`) is what finally collects them.
    assert pe.read_at_va(str(ED), 0x10036D62, 4).hex() == "837d0c00"
    assert pe.read_at_va(str(ED), 0x100368EF, 9).hex() == "6a00568bcfff900002"
