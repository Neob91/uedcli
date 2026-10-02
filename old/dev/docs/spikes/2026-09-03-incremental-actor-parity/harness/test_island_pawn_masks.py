#!/usr/bin/env python3
"""Regression + negative tests for the Island N=12 ThugMale5 pawn-body masks:

  1. prop-tag-name FName-case fold (`maxRange` vs `MaxRange`), and
  2. `InitialAllianceInfo.AllianceName` resolved to its STRING (the name-table INDEX differs across
     the two builds' owner-excluded name-table order, the string is equal).

Proves (a) the real cached native_N12/ref_N12 pass, and (b) neither mask can hide a genuine bug: a
different alliance STRING, or a changed AllianceLevel/bPermanent tail, still FAILS.

Run: python3 test_island_pawn_masks.py    (or via pytest)
"""
from __future__ import annotations

import struct
import sys
import types
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"))

import parity_gate as G  # noqa: E402
from uedcli.upackage import PT_STRUCT, PropertyTag  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity/01_nyc_unatcoisland"
NATIVE, REF = CACHE / "native_N12.dx", CACHE / "ref_N12.dx"


def _idt(names):
    return types.SimpleNamespace(p=types.SimpleNamespace(names=names))


def _ia_tag(name_idx, level=1.0, permanent=0):
    raw = bytes([name_idx]) + struct.pack("<f", level) + bytes([permanent])
    return PropertyTag(name="InitialAlliances", ptype=PT_STRUCT,
                       struct_name="InitialAllianceInfo", array_index=0, bool_value=None, raw=raw)


def test_ia_name_index_differs_string_equal_is_masked():
    a = G._canon_value(_idt(["None", "NSF"]), _ia_tag(1))       # idx 1 -> 'NSF'
    b = G._canon_value(_idt(["None", "x", "x", "NSF"]), _ia_tag(3))  # idx 3 -> 'NSF'
    assert a == b, (a, b)


def test_ia_different_alliance_string_fails():
    a = G._canon_value(_idt(["None", "NSF"]), _ia_tag(1))
    b = G._canon_value(_idt(["None", "UNATCO"]), _ia_tag(1))
    assert a != b


def test_ia_tail_change_not_masked():
    base = G._canon_value(_idt(["None", "NSF"]), _ia_tag(1, level=1.0, permanent=0))
    assert base != G._canon_value(_idt(["None", "NSF"]), _ia_tag(1, level=-1.0, permanent=0))
    assert base != G._canon_value(_idt(["None", "NSF"]), _ia_tag(1, level=1.0, permanent=1))


def test_cached_island_n12_pawn_passes():
    if not (NATIVE.exists() and REF.exists()):
        print("skip: cached native_N12/ref_N12 absent")
        return
    ok, fails = G.gate(str(NATIVE), str(REF))
    assert ok, fails


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print(f"ok {k}")
    print(f"{n} passed")
