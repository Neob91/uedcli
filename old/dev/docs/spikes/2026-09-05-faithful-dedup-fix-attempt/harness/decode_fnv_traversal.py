#!/usr/bin/env python3
"""Pin the `FindNearestVertex` recursive-descent traversal facts from `UED22/Engine.dll`.

The point-dedup faithful-fix question hinges on WHICH points `bspAddPoint`'s spatial index can
reach. `bspAddPoint` (Editor.dll 0x35430) -> `UModel::FindNearestVertex` (Engine.dll 0x1adeb0) ->
recursive helper 0x1adb60. This asserts, straight from the DLL bytes, that the helper:

  - descends the iFront / iBack children (FBspNode +0x20 / +0x24), and
  - AFTER testing a node's own surf-base (iSurf +0x1c) + vert-pool, FOLLOWS the coplanar iPlane
    chain (+0x28) and re-tests every coplanar node's surf-base + verts.

Consequence: a point wired as ANY live node's surf-base -- primary OR coplanar-chain -- is reachable.
So there is no "coplanar surf-bases are invisible to dedup" escape: the query is an exact
nearest-within-R over the whole live subtree. The x=448 (N8) / Step (N19) editor MISS is therefore a
tree-CONTENTS fact (the editor's incremental tree lacks the snapped point as a reachable node at that
add), not a descent-algorithm fact -- the wall the faithful fix hits.

Static only. Run: `python3 decode_fnv_traversal.py`  (asserts, prints a table).
Reuses the shared PE helper at `dev/docs/spikes/bspspike/pe.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))
import pe  # noqa: E402

EN = str(ROOT / "uned/UED22/Engine.dll")

# (VA, expected bytes, meaning). FBspNode is 64 bytes; child/link offsets below.
CHECKS = [
    (0x101ADBA3, "8b4820", "mov ecx,[eax+0x20]  -> node.iFront child"),
    (0x101ADBD0, "8b4024", "mov eax,[eax+0x24]  -> node.iBack child"),
    (0x101ADC92, "8b4e1c", "mov ecx,[esi+0x1c]  -> node.iSurf (surf-base tested)"),
    (0x101ADE4F, "8b7628", "mov esi,[esi+0x28]  -> node.iPlane (coplanar chain FOLLOWED)"),
    # after loading iPlane: cmp esi,-1 ; jne 0x1adc80 (loop back to re-test the coplanar node)
    (0x101ADE64, "83feff0f8513", "cmp esi,-1 ; jne 0x1adc80  -> re-test each coplanar node"),
    # FindNearestVertex entry gate: empty Nodes (+0x5c) => immediate MISS
    (0x101ADEE3, "83795c00", "cmp [ecx+0x5c],0  -> empty Model->Nodes gates a MISS"),
    (0x101ADF0D, "c74514000080bf", "mov [ebp+0x14],-1.0f  -> the MISS sentinel"),
]


def main() -> int:
    ok = True
    for va, expected, meaning in CHECKS:
        actual = pe.read_at_va(EN, va, len(expected) // 2).hex()
        good = actual == expected
        ok = ok and good
        print(f"[{'OK ' if good else 'BAD'}] {va:#010x} {meaning}: {actual}")
    print("\nFindNearestVertex traverses iFront/iBack AND the coplanar iPlane chain; coplanar "
          "surf-bases ARE reachable." if ok else "\nMISMATCH -- a DLL fact drifted.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
