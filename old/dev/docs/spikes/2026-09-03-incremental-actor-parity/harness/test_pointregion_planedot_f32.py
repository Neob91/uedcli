"""Pins `UModel::PointRegion`'s descent arithmetic (2026-09-06, Island N=10 / NYC_Bar N=113).

Both levels bailed on a single `Region` token because native evaluated the node plane in f64 while
the engine evaluates it in SINGLE precision with a fixed summation order. On a brush pivot that sits
ON a node plane the f64 value is ~1e-5 off zero and the descent takes the other child.

The two binary facts the fix rests on:

1. `FPlane::PlaneDot` (`Core.dll 0x10024e60`) is an SSE horizontal add over f32 lanes
   `(P.X*X, P.Y*Y, P.Z*Z, -1.0*W)`, summed as `(lane3 + lane2) + (lane1 + lane0)`. The `-1.0` comes
   from `orps` with the constant at `0x100a0af0` = `(0, 0, 0, -1.0)` over a zeroed lane 3.
2. `UModel::PointRegion` (`Engine.dll 0x101aee60`) descends `iChild[IsFront]` (`node+0x20`, so
   `IsFront=1` picks the SECOND on-disk child index) with `IsFront = setae(PlaneDot, 0.0)`, and
   reads `iLeaf[IsFront]` from `node+0x38`.

Run just this file (project rule: never the whole suite):
  TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider \\
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/test_pointregion_planedot_f32.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))

from uedcli.native.materialize import _plane_dot  # noqa: E402

CORE = ROOT / "uned/UED22/Core.dll"
ENGINE = ROOT / "uned/UED22/Engine.dll"


@pytest.fixture(scope="module")
def pe_mod():
    if not (CORE.exists() and ENGINE.exists()):
        pytest.skip("UED22 DLLs not present")
    try:
        import pe
    except Exception:
        pytest.skip("pe.py / pefile+capstone unavailable")
    return pe


def test_planedot_is_single_precision_sse(pe_mod):
    pe = pe_mod
    body = pe.read_at_va(str(CORE), 0x10024E60, 0x3C).hex()
    assert body == (
        "558bec"              # push ebp; mov ebp,esp
        "8b4508"              # mov eax,[ebp+8]           ; &P
        "0f1001"              # movups xmm0,[ecx]         ; the FPlane
        "f30f105008"          # movss  xmm2,[eax+8]       ; P.Z
        "0f16d2"              # movlhps xmm2,xmm2
        "0f1210"              # movlps xmm2,[eax]         ; -> (P.X,P.Y,P.Z,+0.0)
        "0f5615f00a0a10"      # orps   xmm2,[0x100a0af0]  ; lane3 := -1.0
        "0f59d0"              # mulps  xmm2,xmm0          ; (X*Px, Y*Py, Z*Pz, -W)
        "0f28ca0fc6cab1"      # movaps xmm1,xmm2; shufps xmm1,xmm2,0xb1
        "0f28c10f58c2"        # movaps xmm0,xmm1; addps xmm0,xmm2
        "0f12c8f30f58c8"      # movhlps xmm1,xmm0; addss xmm1,xmm0
        "f30f114d08d94508"    # movss [ebp+8],xmm1; fld dword [ebp+8]
        "5dc2")
    assert pe.read_at_va(str(CORE), 0x100A0AF0, 16).hex() == "000000000000000000000000000080bf"


def test_pointregion_descends_ichild_isfront(pe_mod):
    pe = pe_mod
    assert pe.read_at_va(str(ENGINE), 0x101AEED8, 0x40).hex() == (
        "83ffff7431"          # cmp edi,-1; je exit
        "8bf7c1e60603f2"      # esi = &Nodes[iNode]  (<<6 == sizeof FBspNode 64)
        "8d4510508bce"        # push &P; ecx = node   (FPlane is at node+0)
        "ff15fc941f10"        # call FPlane::PlaneDot
        "d95decf30f1045ec"    # fstp [ebp-0x14]; movss xmm0,[ebp-0x14]   -- ROUNDED TO f32
        "33c00f57c90f2fc10f93c08945ec"   # comiss xmm0,0; setae al -> IsFront
        "8bcf"                # iParent = iNode
        "8b7c8620"            # iNode = [node + IsFront*4 + 0x20]  = iChild[IsFront]
        "ebc7"
        "8bc1c1e004"          # exit: eax = iParent*16
        "8b75ec03c6")         # + IsFront  (-> iLeaf[IsFront] at +0x38, read next)


@pytest.mark.parametrize("plane,point,f64_sign", [
    # Island `Brush1359` (Location -11680, 4528, -384) at world node 22: the f64 dot is -9.6e-05,
    # which sent the descent to leaf 13 where UED22 lands in leaf 18.
    ((-0.2460974156856537, 0.969245195388794, 0.0, 7263.16015625),
     (-11680.0, 4528.0, -384.0), -1),
    # NYC_Bar `Brush69` (Location -384, -440, 0) at world node 272: the f64 dot is -7.6e-06, which
    # walked the descent out of the tree (iLeaf -1) where UED22 lands in leaf 55.
    ((0.0, 0.8944272994995117, 0.44721364974975586, -393.5480041503906),
     (-384.0, -440.0, 0.0), -1),
])
def test_on_plane_pivots_dot_to_exactly_zero(plane, point, f64_sign):
    x, y, z, w = plane
    naive = x * point[0] + y * point[1] + z * point[2] - w
    assert (naive < 0) == (f64_sign < 0), "the f64 dot must still disagree, else the case is stale"
    assert _plane_dot(plane, point) == 0.0
