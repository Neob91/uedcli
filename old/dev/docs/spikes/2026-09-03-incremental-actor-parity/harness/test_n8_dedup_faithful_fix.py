#!/usr/bin/env python3
"""Positive regression for the FAITHFUL x=448 point-dedup fix (replaces test_n8_dedup_tie_mask.py).

The node-plane-W / CSG-soup-base dedup-tie mask is GONE — native now dedups incremental points with the
editor's radius-pruned FindNearestVertex descent (`bspcsg.rs`), so UNATCO N8 (and WanChai N19) byte-match
the editor with NO tolerance. These tests assert:
  1. `parity_gate` compares node-plane W and FPoly.Base BYTE-EXACT now — the exact 2.16e-4 x=448 tie the
     old mask hid must FAIL, and the Brush Region mask is gone.
  2. The cached descent build of UNATCO N8 gates byte-exact against its editor ref (skips if absent —
     the .dx files live under _scratch, not git).

Run: python3 test_n8_dedup_faithful_fix.py    (or via pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))

import parity_gate as G  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity/03_nyc_unatcohq"
NATIVE = CACHE / "native_N8.dx"
REF = CACHE / "ref_N8.dx"

# The two real Model.Points x's that straddle the x=448 face, 2.16e-4 apart (the old masked tie).
P29_X = 448.00006103515625
P32_X = 447.9998474121094


def test_node_w_is_byte_strict_now():
    a = ("model", None, [("b", b"pre"), ("NW", -P32_X), ("b", b"post")])
    assert G._bodies_equal(a, ("model", None, [("b", b"pre"), ("NW", -P32_X), ("b", b"post")]))
    tie = ("model", None, [("b", b"pre"), ("NW", -P29_X), ("b", b"post")])  # 2.16e-4 off = old tie
    assert not G._bodies_equal(a, tie), "the x=448 node-W tie must now FAIL (mask removed)"


def test_poly_base_is_byte_strict_now():
    a = ("polys", None, [("PB", (P32_X, 64.0, 0.0))])
    assert G._bodies_equal(a, ("polys", None, [("PB", (P32_X, 64.0, 0.0))]))
    tie = ("polys", None, [("PB", (P29_X, 64.0, 0.0))])
    assert not G._bodies_equal(a, tie), "the x=448 soup-base tie must now FAIL (mask removed)"


def test_mask_code_is_gone():
    assert not hasattr(G, "NODE_W_DEDUP_TOL"), "the W dedup-tie tolerance must be removed"
    assert not hasattr(G, "_node_w_tie") and not hasattr(G, "_poly_base_tie")
    assert G._BRUSH_MASKED_PROPS == frozenset(), "Brush Region must no longer be masked"


def test_n8_gates_byte_exact_without_mask():
    if not (NATIVE.exists() and REF.exists()):
        import pytest  # loud skip (not a silent pass) — build with `actor_parity.py native 8` first
        pytest.skip(f"cached descent build absent: {NATIVE} / {REF}")
    argv = sys.argv
    try:
        sys.argv = ["parity_gate.py", str(NATIVE), str(REF)]
        assert G.main() == 0, "UNATCO N8 must gate byte-exact WITHOUT the x=448 mask"
    finally:
        sys.argv = argv


if __name__ == "__main__":
    test_node_w_is_byte_strict_now()
    test_poly_base_is_byte_strict_now()
    test_mask_code_is_gone()
    try:
        test_n8_gates_byte_exact_without_mask()
    except Exception as e:  # pytest.skip when the cached .dx are absent
        if type(e).__name__ != "Skipped":
            raise
        print(f"SKIP n8 gate: {e}")
    print("OK")
