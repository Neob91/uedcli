#!/usr/bin/env python3
"""Regression + negative tests for the N=8 UNATCO node-plane-W / poly-base dedup-tie mask
(board native-n8-unatco-rotated-brush-base-fp-diverges).

Proves the mask (a) passes the genuine x=448 dedup-tie and (b) CANNOT hide a real geometry bug:
a plane W moved off-geometry, a W moved beyond the tie band, a changed node normal, and a changed
NON-brush actor Region all still FAIL. Runs on the cached native_N8 / ref_N8 packages; skips cleanly
if they are absent (they live under _scratch, not git).

Run: python3 test_n8_dedup_tie_mask.py    (or via pytest)
"""
from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"))

import parity_gate as G  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity/03_nyc_unatcohq"
NATIVE = CACHE / "native_N8.dx"
REF = CACHE / "ref_N8.dx"

# Byte offsets in native_N8.dx (from the cached build; asserted below before patching):
NODE29_NORMAL_X = 9253      # node 29 FPlane.normal.x (f32) == -1.0
NODE29_W = 9265             # node 29 FPlane.W (f32) == -448.00006 (the snapped dedup value)
LEVELINFO_ILEAF = 1823      # LevelInfo0 Region.iLeaf (i32) == -1  (non-brush -> never masked)
POLY14_BASE_X = 3728        # Polys soup poly 14 FPoly.Base.x (f32) == 448.00006 (a table point)

# The two real, byte-identical Model.Points x's straddling this face (normal = (-1,0,0), so a node's
# W = -x). ued's node-29 W is -P32 (its own snapped pBase); native's is -P29 (a sibling). 2.16e-4 apart.
P29_X = 448.00006103515625
P32_X = 447.9998474121094
UED_W = -P32_X              # ued node-29 W (the tie's other side)
ULP448 = 3.0517578125e-05  # f32 ulp in [256,512); P29 and P32 are exactly 7 ulp apart
# A W exactly 4 ulp off the nearest real point (P32): 1.22e-4 away -- inside the OLD 1.5e-4 point-tol
# (would mask) but outside the tightened 1e-4 (must FAIL), and still inside the 5e-4 band so it is
# POINT_TOL, not the band, that rejects it. (An f32 value strictly BETWEEN the two 7-ulp-apart points
# is always <= 3 ulp ~= 9.15e-5 from an endpoint -- i.e. essentially a real point -- so a true
# "midpoint" cannot be constructed in f32 here; 4-ulp-off is the tightest realizable off-point W.)
W_OFF_POINT = -(P32_X - 4 * ULP448)


def _gate(native_bytes: bytes) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".dx", delete=False) as f:
        f.write(native_bytes)
        tmp = f.name
    try:
        ok, _ = G.gate(tmp, str(REF))
        return ok
    finally:
        Path(tmp).unlink(missing_ok=True)


def _patch_f32(b: bytes, off: int, val: float) -> bytes:
    return b[:off] + struct.pack("<f", val) + b[off + 4:]


def _patch_i32(b: bytes, off: int, val: int) -> bytes:
    return b[:off] + struct.pack("<i", val) + b[off + 4:]


def run() -> int:
    if not (NATIVE.exists() and REF.exists()):
        print("SKIP: cached native_N8/ref_N8 not present")
        return 0
    base = NATIVE.read_bytes()
    # Sanity-check the offsets against the cached build before trusting the patches.
    assert struct.unpack_from("<f", base, NODE29_NORMAL_X)[0] == -1.0
    assert abs(struct.unpack_from("<f", base, NODE29_W)[0] + 448.00006) < 1e-3
    assert struct.unpack_from("<i", base, LEVELINFO_ILEAF)[0] == -1
    assert abs(struct.unpack_from("<f", base, POLY14_BASE_X)[0] - 448.00006) < 1e-3

    cases = [
        # (label, patched_native_bytes, expected_gate_pass)
        ("b  genuine x=448 dedup-tie (unpatched)", base, True),
        ("a1 node29 W off-geometry, far (-500)", _patch_f32(base, NODE29_W, -500.0), False),
        # Within the 0.002 tie band of ued's W (-447.99985) but on NO table point -> must still FAIL:
        ("a2 node29 W in-band, off-geometry (-447.9990)", _patch_f32(base, NODE29_W, -447.9990), False),
        ("d  node29 normal.x changed (-1 -> -0.9)", _patch_f32(base, NODE29_NORMAL_X, -0.9), False),
        ("c  non-brush LevelInfo Region iLeaf (-1 -> 5)", _patch_i32(base, LEVELINFO_ILEAF, 5), False),
        # Poly-soup base moved off-geometry within the tie band -> native base no longer a table point:
        ("e1 poly14 base in-band, off-geometry (x=447.9990)", _patch_f32(base, POLY14_BASE_X, 447.9990), False),
        ("e2 poly14 base far (x=500)", _patch_f32(base, POLY14_BASE_X, 500.0), False),
        # Band: |dW| between the 5e-4 mask tol and the +/-0.001 inconsequence band -> must FAIL.
        ("f1 node29 W dW=0.0007 (> 5e-4 band)", _patch_f32(base, NODE29_W, UED_W + 0.0007), False),
        ("f2 node29 W dW=0.0015", _patch_f32(base, NODE29_W, UED_W + 0.0015), False),
        # Point-tol: a W 4 ulp (1.22e-4) off the nearest real point, still inside the 5e-4 band ->
        # masked under the old 1.5e-4 tol, must FAIL under the tightened 1e-4.
        ("g  node29 W 4-ulp off point (1.22e-4, in-band)", _patch_f32(base, NODE29_W, W_OFF_POINT), False),
    ]
    failures = 0
    for label, patched, want in cases:
        got = _gate(patched)
        ok = got == want
        failures += not ok
        print(f"  [{'OK ' if ok else 'BAD'}] {label}: gate={'YES' if got else 'NO'} "
              f"(want {'YES' if want else 'NO'})")
    print("PASS" if not failures else f"FAIL: {failures} case(s)")
    return 1 if failures else 0


def test_n8_dedup_tie_mask():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
