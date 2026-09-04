"""Pins the spike `2026-09-04-bspaddpoint-dedup-base-provenance`:

1. the `bspAddPoint` / `FindNearestVertex` / `csgRebuild` disasm constants (against the real DLLs), and
2. the measured N=8 node-plane base provenance (against the committed goldens):
   `Points`+`Surf.pBase` byte-identical native==editor; only `Node[29/30].plane.W` differ, editor =
   raw base (`-447.99985`), native = `Points[pBase]` (`-448.00006`).

A drift in either trips here. Run just this file (project rule: never the whole suite):
  TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider \
    dev/docs/spikes/2026-09-04-bspaddpoint-dedup-base-provenance/test_bspaddpoint_dedup_facts.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"))

ED = ROOT / "uned/UED22/Editor.dll"
EN = ROOT / "uned/UED22/Engine.dll"


# ---- Part A: disasm facts -------------------------------------------------------------------

@pytest.mark.skipif(not (ED.exists() and EN.exists()), reason="UED22 DLLs not present")
def test_dedup_disasm_constants():
    try:
        import pe  # noqa: F401
    except Exception:
        pytest.skip("pe.py / pefile+capstone unavailable")

    def f32(dll, va):
        return struct.unpack("<f", pe.read_at_va(str(dll), va, 4))[0]

    # bspAddPoint (Points) / bspAddVector (Vectors) thresholds
    assert f32(ED, 0x100DCAF8) == pytest.approx(0.002, abs=1e-9)   # Points Exact=1
    assert f32(ED, 0x100DCAFC) == pytest.approx(0.015, abs=1e-6)   # Points Exact=0
    assert f32(ED, 0x100DCAF0) == pytest.approx(2e-5, abs=1e-9)    # Vectors Exact=1
    assert f32(ED, 0x100DCAF4) == pytest.approx(4e-4, abs=1e-9)    # Vectors Exact=0
    # csgRebuild sets/clears GFastRebuild = Editor+0x10c bit0 around the whole rebuild
    assert pe.read_at_va(str(ED), 0x1004A6A5, 3).hex() == "83c801"           # or eax,1
    assert pe.read_at_va(str(ED), 0x1004AAC6, 7).hex() == "83a30c010000fe"   # and [ebx+0x10c],~1
    # FindNearestVertex gates on Model->Nodes count (+0x5c); MISS returns -1.0f (0xbf800000)
    assert pe.read_at_va(str(EN), 0x101ADEE3, 4).hex() == "83795c00"         # cmp [ecx+0x5c],0
    assert pe.read_at_va(str(EN), 0x101ADF0D, 7).hex() == "c74514000080bf"


# ---- Part B: golden node-plane provenance ---------------------------------------------------

def _models():
    from uedcli.native import umodel as UM  # noqa: F401  (import guard)
    import parity_compare as PC
    nat = PC.parse_dx_model(HERE / "golden/native_N8.dx")
    ref = PC.parse_dx_model(HERE / "golden/ref_N8.dx")
    return nat, ref


def _has_native():
    try:
        _models()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_native(), reason="uedcli_native / parse deps unavailable")
def test_n8_points_and_pbase_identical_only_planes_2930_differ():
    nat, ref = _models()
    # Points + Vectors byte-identical -> bspAddPoint returned the same indices (dedup did NOT diverge)
    assert nat.points == ref.points
    assert nat.vectors == ref.vectors
    # every surf pBase identical
    assert [s.p_base for s in nat.surfs] == [s.p_base for s in ref.surfs]
    # the ONLY node-plane differences are nodes 29 and 30
    diffs = {i for i, (a, b) in enumerate(zip(nat.nodes, ref.nodes)) if a.plane != b.plane}
    assert diffs == {29, 30}, diffs


@pytest.mark.skipif(not _has_native(), reason="uedcli_native / parse deps unavailable")
def test_n8_node_plane_base_provenance():
    nat, ref = _models()
    for i in (29, 30):
        a, b = nat.nodes[i], ref.nodes[i]
        assert a.plane[:3] == b.plane[:3]                       # same normal (-1,0,0)
        # native W = -Points[pBase].x (snapped);  editor W = -(raw base) (distinct, not a point)
        assert a.plane[3] == pytest.approx(-448.00006, abs=1e-4)
        assert b.plane[3] == pytest.approx(-447.99985, abs=1e-4)
        s = ref.surfs[b.i_surf]
        pbase_x = ref.points[s.p_base][0]
        assert pbase_x == pytest.approx(448.00006, abs=1e-4)    # the snapped point exists in the table
        assert abs(b.plane[3] - (-pbase_x)) > 1e-4              # editor's W is NOT that point
