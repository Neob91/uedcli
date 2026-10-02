#!/usr/bin/env python3
"""Stage 1 reproducer + self-assert — point-dedup reachability divergence (UNATCO N8, WanChai N19).

Foundation stage of the faithful incremental-BSP-core point-dedup rewrite
(`board/to-build/native-materialize/faithful-incremental-bsp-dedup-rewrite/`). Instrumentation only;
the default native build path is byte-unchanged (masked gate PASS + cargo goldens green with the trace
compiled in). This script rebuilds native N8/N19 with the point trace on and asserts the divergent snaps
still fire — so a later change that alters the class trips a red instead of drifting.

THE PINNED DIVERGENCE (both cases = ONE class)
----------------------------------------------
A later brush's face whose raw transformed `FPoly.Base` is a ~ULP-scale near-tie to a point an EARLIER
brush already wired as a LIVE, REACHABLE BSP node surf-base. Native's `bsp_add_point` linear scan snaps
onto it; the editor's `FindNearestVertex` (Engine.dll 0x1adeb0) keeps it distinct (a MISS). Native's
tree reachably wires the target, so an FNV descent over NATIVE'S tree also snaps -> the fix is the tree
WIRING/reachability, not the dedup rule.

UNATCO N8 (actor #8 Brush74, rotated subtract). Two brushes meet at corner (448,64,0), x rounds ~7 ULP
apart. Divergent add (`traces/n8_pt.log`):
    q=(447.999847,64.000107,0.0) SNAP -> idx86=(448.000061,64.000107,0.000031) d=2.158e-4
    reach=62/62  sb=[48,49,50]  (surf iSurf=32, actor 5 +Y face, ALIVE)
  actor 5 `+Y` ilink32 base 448.00006 wired FIRST at nodes 48-50; actor 6 `-X` ilink38 (node 62) raw
  base 447.99985 SNAPS onto it. `n8_nadd.log`: actor 6 fragments attach UNDER 48-50 (parent=48/49/50) --
  the snap target is the divergent face's own tree PARENT.
  Editor: MISS; node-plane W frozen at -447.99985; 76-point table stays byte-identical (final pBase
  re-dedups to 448.00006). Reachability fact to reproduce: actor 5's 448.00006 must be NON-reachable to
  FNV at actor 6's -X surf-base add.

WanChai N19 (actor #19 Brush405). In-plane (normal (0,0,1), dW=0), gap 1.007e-3 (> 5e-4 mask -> FAIL).
Divergent adds (`traces/n19_pt.log`), z=-152/-144/-136:
    q=(-0.000366,-3072.000244,z) SNAP -> (0.000610,-3072.0,z) d=1.007e-3  reach~262/293  sb=[271/273/275]
  actor 15 step-top +Z faces (base 0.00061) wired first; later coplanar step faces (raw -0.00037) snap
  onto them. Whole Model byte-identical; only `Polys@model model2` soup base diverges (soup_base_diff.py).

WALL (stages 2-3): the editor's INTERMEDIATE tree at the divergent add is unobservable from the built
package (repartition rewrites it) or static disasm -- WHY its reachable set lacks the target (Model+0x5c
index staleness vs splice timing vs FilterWorldThroughBrush node-wiring order) needs a LIVE editor gdb
probe. The FNV traversal is already pinned: `../harness/decode_fnv_traversal.py`.

Run (needs the native ext built from THIS worktree + the cached trunk):
    python3 reproduce.py            # rebuild native N8+N19 with the trace, assert the divergent snaps
Env: UED_DX_DIR overrides the shipped-map dir (default dev/games/deusex/Maps).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AP = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py"
PY = ROOT / ".venv/bin/python"
DX_DIR = Path(os.environ.get("UED_DX_DIR", ROOT / "dev/games/deusex/Maps"))

# (level dx, N, POINT_TRACE filter, substrings every divergent SNAP line must contain)
CASES = [
    ("03_NYC_UNATCOHQ.dx", 8, "448,64,0,2.5",
     ["q=(447.999847,64.000107,0.000000) SNAP", "tval=(448.000061", "sb=[48, 49, 50]"]),
    ("06_HongKong_WanChai_Market.dx", 19, "0,-3072,-144,30",
     ["q=(-0.000366,-3072.000244,-152.000000) SNAP", "tval=(0.000610,-3072.000000,-152.000000)",
      "sb=[271]"]),
]


def run(dx: str, n: int, trace: str) -> str:
    env = {**os.environ, "UEDCLI_BSPCSG_POINT_TRACE": trace}
    r = subprocess.run([str(PY), str(AP), "--dx", str(DX_DIR / dx), "native", str(n)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit(f"build FAILED {dx} N={n}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stderr


def main() -> int:
    ok = True
    for dx, n, trace, needles in CASES:
        log = run(dx, n, trace)
        hit = all(s in log for s in needles)
        ok = ok and hit
        print(f"[{'OK ' if hit else 'BAD'}] {dx} N={n}: divergent snap present")
        if not hit:
            for s in needles:
                if s not in log:
                    print(f"    MISSING: {s}")
    print("\nStage-1 divergences reproduce." if ok else "\nDRIFT -- a divergent snap changed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
