#!/usr/bin/env python3
r"""Stage 2b — LIVE editor gdb/winedbg probe: the reachable-set fact at the divergent add.

Coordinator's crux question: at the editor's actor-6 `-X` face surf-base add (query near
`(447.999847, 64.000107, 0)`), is actor-5's `+Y` face base `(448.000061,...)` reachable in the
editor's live BSP node tree (-> `FindNearestVertex` HIT) or not (-> MISS)? That single fact separates
"editor tree topology genuinely differs" (expensive Stage 3) from a cheap ordering effect.

RESULT (captured live from UED22 under wine, `traces/n8_editor_fnv_capture.out`):

  hit  query (x, y, z)                 thr     FindNearestVertex
  12   (447.999847, 64.000107, 0.0)    0.002   -1.0  MISS   <- THE DIVERGENT SURF-BASE ADD
   5   (447.999847, -288.00015, 0.0)   0.002   -1.0  MISS   <- actor-6's other face, same class
   1   (447.999847, 64.000107, 416.0)  0.015   HIT d=4.590e-4  (a ring-vert add, at z=416)
   4   (447.999847, 64.000107, 240.0)  0.015   HIT d=2.142e-4  (a ring-vert add, at z=240)

VERDICT: **genuine tree-CONTENTS / reachability difference — the expensive tree-wiring class, NOT a
cheap ordering-only effect.** At the surf-base add the editor's `FindNearestVertex` returns the
-1.0 MISS sentinel: NO vertex within 0.002 of `(448,64,0)` is reachable from root 0 in the editor's
live tree at that moment. Native (Stage 1) HITS `448.00006` there (d=2.158e-4; it is the reachable
surf-base of live nodes 48/49/50). So the editor's incremental world BSP genuinely lacks that corner
point as a reachable node-vertex at the add, while native's has it — the trees differ mid-CSG even
though their FINAL trees are byte-identical (board: Points 76/76 identical, only node W differs).

The editor computes actor-6's `-X` base x = 447.999847 EXACTLY (float bits 0x43dffffb) — same as
native — so this is not a base-value difference; the conditional breakpoint (below) fired precisely on
that bit pattern, and it MISSED. The MISS is exactly the point-dedup provenance the board pinned: the
editor's pre-repartition surf `pBase` becomes a DISTINCT 447.99985 point, `bspAddNode` freezes node W
= -447.99985, native's linear scan instead snaps to 448.00006.

Stage 3 target (confirmed): native must reproduce the editor's per-add REACHABLE-surf-base set. That
is (a) FNV-over-the-live-incremental-tree dedup replacing the linear-immortal-pool scan, AND (b) the
incremental tree wiring (`FilterWorldThroughBrush` fragment/link order + `bspCleanup` splices) matched
so that `(448,64,0)` is likewise UNREACHABLE at the `-X` surf-base add. The FNV port alone is
insufficient (Stage 1 / ba23319): over native's CURRENT tree it still HITS. Not a cheap reorder: the
ring-vert adds at the same face HIT while the surf-base MISSES, and dead-node surf-bases are still
tested (Stage 2), so the corner is genuinely absent from the reachable tree, not merely mis-ordered.
An optional Stage-3 refinement (not needed for this verdict): dump the editor's Nodes/Surfs/Points at
hit 12 to see WHICH nodes it has that native lacks (topology detail) — a bigger winedbg traversal.

------------------------------------------------------------------------------------------------
THE LIVE-PROBE RECIPE (reproduce; x86_64 host, native wine — no gdb in the image, winedbg only)

Editor image `ued-x86-runtime:latest`; ephemeral container per `parallel-editors.md`. Module load
bases under wine (from `winedbg` `info share`): **editor (Editor.dll) at 0x10000000 (preferred, NO
relocation)**, engine (Engine.dll) RELOCATED to 0x01620000. So:
  bspAddPoint = 0x10035430, bspAddNode = 0x10034e80, FindNearestVertex = 0x01620000+0x1adeb0.
Break at **0x100354a1** — inside bspAddPoint, right after the `call FindNearestVertex`, where
`*(int*)($ebp+0x0c)` = query FVector ptr, `*(float*)($ebp+0x10)` = threshold (0.002 surf-base /
0.015 ring), `*(float*)($ebp+8)` = FNV return distance (-1.0 = MISS), `*(int*)($ebp-0x14)` = vertex idx.

Steps (docker cp is broken under rootless overlay — write files via `docker exec python3 -c`,
base64 for the T3D):
 1. Generate the N8 import T3D: `emit_map([LevelInfo, dummy_builder, *N8 actors])`
    (build_ued_import_built_golden helpers). Base64 it into the container `/work/n8.t3d`.
 2. `/work/build.txt` = `MAP NEW` / `MAP IMPORT FILE=Z:\work\n8.t3d` / `MAP REBUILD` (CRLF).
 3. winedbg command file: `attach 0x20` (unrealed.exe win pid, from `info process`);
    `break *0x100354a1`; `condition 1 *(int*)(*(int*)($ebp+0x0c))==0x43dffffb` (float bits of
    447.999847 — isolates the actor-6 x=447.99985 adds, ~12 hits, not thousands); `cont`; then N
    blocks of `print *(int*)(...)` x6 (raw int bits — winedbg's `x/` format errored; read ints,
    convert host-side) + `cont`; then `detach; quit`.
 4. Run winedbg in a BACKGROUND `docker exec` (it blocks on `cont`); in the FOREGROUND drive
    `wine_ctl.py exec 'EXEC Z:\work\build.txt'`. Pair with a ~20-min hang-detector; tear the
    container + wine volume down after (editor wedges silently — `background-work.md`).

`parse_capture()` below re-asserts the crux (surf-base add -> MISS) from the committed capture.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / "traces" / "n8_editor_fnv_capture.out"


def _f(bits: str) -> float:
    return struct.unpack("<f", struct.pack("<I", int(bits, 16) & 0xFFFFFFFF))[0]


def parse_capture(path: Path = CAPTURE) -> list[dict]:
    """Each hit = the 6 int-bit values printed after a 'Stopped on breakpoint' line."""
    lines = [l.replace("Wine-dbg>", "").strip() for l in path.read_text().splitlines()]
    hits, cur = [], None
    for l in lines:
        if "Stopped on breakpoint" in l:
            if cur is not None:
                hits.append(cur)
            cur = []
        elif cur is not None and re.fullmatch(r"(0x[0-9a-f]+|0)", l):
            cur.append(l)
    if cur:
        hits.append(cur)
    out = []
    for h in hits:
        if len(h) < 6:
            continue
        x, y, z, thr, dist, _vidx = h[:6]
        out.append({"x": _f(x), "y": _f(y), "z": _f(z), "thr": _f(thr), "dist": _f(dist)})
    return out


def main() -> int:
    hits = parse_capture()
    surf = [h for h in hits if abs(h["thr"] - 0.002) < 1e-4]
    div = [h for h in surf if abs(h["x"] - 447.999847) < 1e-4]
    print(f"parsed {len(hits)} hits, {len(surf)} surf-base (thr=0.002)")
    ok = bool(div) and all(abs(h["dist"] + 1.0) < 1e-6 for h in div)
    for h in div:
        print(f"  surf-base ({h['x']:.6f},{h['y']:.6f},{h['z']:.3f}) FNVdist={h['dist']:+.3e} "
              f"{'MISS' if h['dist'] < 0 else 'HIT'}")
    print("\nCRUX CONFIRMED: editor FindNearestVertex MISSES at the divergent surf-base add "
          "(reachability/tree-wiring divergence, not a cheap ordering effect)."
          if ok else "\nCRUX NOT REPRODUCED from capture -- investigate.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
