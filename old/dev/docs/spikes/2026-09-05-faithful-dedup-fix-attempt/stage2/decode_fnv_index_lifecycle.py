#!/usr/bin/env python3
"""Stage 2 — decode the FNV "index" lifecycle; SETTLE the index-staleness hypothesis (static).

Stage-2 question (coordinator): WHEN is the editor's `FindNearestVertex` spatial index (`Model+0x5c`)
rebuilt/refreshed relative to per-node `bspAddNode`/`bspAddPoint` inside one brush's CSG? Hypothesis:
the index is STALE within a brush (rebuilt only at brush/`bspRefresh` boundaries), so the divergent
MISS is index staleness -- a far cheaper fix than re-deriving the incremental tree.

VERDICT: **staleness hypothesis REFUTED.** There is NO separate spatial index. `Model+0x5c` is
`Model->Nodes.ArrayNum` (the node COUNT), `Model+0x58` is `Model->Nodes.Data`. `bspAddPoint`
(Editor.dll 0x35430) calls `UModel::FindNearestVertex` (Engine.dll 0x1adeb0) which, when the count is
nonzero, descends the LIVE `Model->Nodes` BSP tree from HARD-CODED root iNode=0 (helper 0x1adb60),
reading each node's surf-base straight from the live `Surfs`/`Points` arrays. So the "index" is the
node tree itself -- inherently per-node current; nothing to go stale. The editor's MISS at the
divergent surf-base add is therefore a genuine tree-CONTENTS/reachability fact: the earlier brush's
near-tie face is not present-and-reachable-from-root-0 in the editor's world BSP at that moment, while
in native's it is (Stage-1 trace: reach shows it wired as a live surf-base). => the fix is Stage 3
(reproduce the incremental tree wiring), NOT a cheap index-refresh.

Two cheaper sub-hypotheses ALSO refuted here:
 - "dead-marking causes the miss": the surf-base test (helper 0x1adc80..0x1adcd3) has NO NumVertices
   guard -- a node marked dead (nv==0) by FilterWorldThroughBrush but not yet spliced by bspCleanup
   STILL contributes its surf-base to the nearest search. Only the vert-POOL loop is nv-guarded
   (`cmp byte [esi+0x36],cl` @0x1add6b). So marking the earlier face dead can't produce the MISS.
 - "linear AddThing path": bspAddPoint takes the FindNearestVertex path whenever GFastRebuild is set
   (`[Editor+0x10c]`); the linear `AddThing` (0x31ae0) is the ELSE branch (@0x100354d1 not-and-1),
   and csgRebuild holds GFastRebuild set for the whole rebuild (board, prior spike). So the divergent
   adds go through FindNearestVertex.

FBspNode (64 bytes) offsets in play: iVertPool +0x18, iSurf +0x1c, iFront +0x20, iBack +0x24,
iPlane +0x28, NumVertices(byte) +0x36. UModel: Nodes.Data +0x58 / Nodes.Num +0x5c, Verts.Data +0x68,
Points.Data +0x88, Surfs.Data +0x98. FBspSurf: pBase at +8.

Static only; asserts DLL bytes. Run: `python3 decode_fnv_index_lifecycle.py`.
Reuses the shared PE helper at `dev/docs/spikes/bspspike/pe.py`. Companion (traversal) pin:
`../harness/decode_fnv_traversal.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))
import pe  # noqa: E402

EN = str(ROOT / "uned/UED22/Engine.dll")
ED = str(ROOT / "uned/UED22/Editor.dll")

# (dll, VA, expected bytes, meaning)
CHECKS = [
    (EN, 0x101ADEE3, "83795c00", "FindNearestVertex: cmp [Model+0x5c],0 -> Nodes.Num is the empty-gate"),
    (EN, 0x101ADEEC, "6a00", "FindNearestVertex: push 0 -> descent root iNode is HARD-CODED 0"),
    (EN, 0x101ADB9D, "034158", "helper: add eax,[Model+0x58] -> Nodes.Data (node = Data + iNode*64)"),
    (EN, 0x101ADC61, "8b9088000000", "helper: mov edx,[Model+0x88] -> Points.Data"),
    (EN, 0x101ADC89, "8b8098000000", "helper: mov eax,[Model+0x98] -> Surfs.Data"),
    (EN, 0x101ADC92, "8b4e1c", "helper: mov ecx,[node+0x1c] -> iSurf (surf-base tested, UNCONDITIONAL)"),
    (EN, 0x101ADC98, "8b4c0108", "helper: mov ecx,[Surfs.Data + iSurf*64 + 8] -> Surf.pBase"),
    (EN, 0x101ADD6B, "384e36", "helper: cmp byte [node+0x36],cl -> vert-POOL loop guarded by NumVertices"),
    (EN, 0x101ADE4F, "8b7628", "helper: mov esi,[node+0x28] -> coplanar iPlane chain followed"),
    (ED, 0x10035498, "ff151cee0c10", "bspAddPoint: call [0x100cee1c] -> FindNearestVertex import thunk"),
    (ED, 0x100354D1, "8b860c010000", "bspAddPoint: mov eax,[Editor+0x10c] -> GFastRebuild (else = AddThing)"),
    (ED, 0x100354ED, "e8eec5ffff", "bspAddPoint: call 0x31ae0 (AddThing linear) on the ELSE branch only"),
]


def main() -> int:
    ok = True
    for dll, va, expected, meaning in CHECKS:
        actual = pe.read_at_va(dll, va, len(expected) // 2).hex()
        good = actual == expected
        ok = ok and good
        print(f"[{'OK ' if good else 'BAD'}] {Path(dll).name} {va:#010x} {meaning}: {actual}")
    print("\nNo separate FNV index: Model+0x5c is Nodes.Num; FindNearestVertex descends the LIVE "
          "Nodes tree from root 0. Staleness hypothesis REFUTED -> fix is tree-wiring (Stage 3)."
          if ok else "\nMISMATCH -- a DLL fact drifted.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
