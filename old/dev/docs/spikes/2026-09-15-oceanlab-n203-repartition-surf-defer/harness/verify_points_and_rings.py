#!/usr/bin/env python3
"""Offline (no docker) re-check of the OceanLab N=203 fix: rebuilds native's N=203 world Model2 and
compares it against a KEPT `ref_N203.dx` (from a prior `ladder_run.py --keep-native` run) for the
`Model2.points` array and every live node ring.

Confirms two things independently of `parity_gate.py`'s full canonical-body compare (which still
FAILs at N=203 on the separate, already-tracked orphan-vert-COUNT residual — see the board item's
`questions/orphan-vert-count-mismatch-gate-widening.md`):
  1. `points` is byte-identical (was: a genuine 2-ULP divergent pair).
  2. Every live BSP node ring (resolved through Points, not raw Verts-array position) is
     coordinate-identical — the geometry itself is fully correct; only orphan (dead, unreferenced)
     `Verts` bookkeeping still differs.

Usage: verify_points_and_rings.py [--ref <ref_N203.dx>] [--dx <trunk .dx>]

Needs a previously-kept ref build (`ladder_run.py --keep-native --from 203 --to 203`, which leaves
`_scratch/actor-parity/14_oceanlab_lab/ref_N203.dx`) — this script only rebuilds the NATIVE side.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))

import actor_parity as ap  # noqa: E402
import model_dump as md  # noqa: E402
import parity_gate as pg  # noqa: E402

DEFAULT_DX = Path("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx")
DEFAULT_REF = ROOT / "_scratch/actor-parity/14_oceanlab_lab/ref_N203.dx"
N = 203


def _ring(model: dict, node) -> list:
    cis = node[3]
    base, count = cis[0], cis[9]  # i_vert_pool, num_vertices (model_write.rs field order)
    out = []
    for k in range(count):
        i = model["verts"][base + k][0]
        out.append(model["points"][i] if 0 <= i < len(model["points"]) else ("iVertex", i))
    return out


def main() -> int:
    dx = DEFAULT_DX
    ref = DEFAULT_REF
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--dx":
            dx = Path(args[i + 1])
        elif a == "--ref":
            ref = Path(args[i + 1])
    if not ref.exists():
        print(f"missing kept ref build: {ref} -- run ladder_run.py --keep-native --from {N} --to {N} first",
              file=sys.stderr)
        return 2

    subset_full, name = ap._resolve_trunk(dx, "deusex")
    subset = ap.make_subset(subset_full, name, N)
    native = ap.build_native(subset, name, N)

    a_pkg, b_pkg = pg.load_package(str(native)), pg.load_package(str(ref))
    A = md.decode(a_pkg, md.find(a_pkg, "model2"))
    B = md.decode(b_pkg, md.find(b_pkg, "model2"))

    points_same = A["points"] == B["points"]
    print(f"points {'SAME' if points_same else 'DIFF'} ({len(A['points'])} vs {len(B['points'])})")

    if len(A["nodes"]) != len(B["nodes"]):
        print(f"node COUNT differs ({len(A['nodes'])} vs {len(B['nodes'])}) -- not ring-comparable")
        return 1
    same = other = 0
    for i, (na, nb) in enumerate(zip(A["nodes"], B["nodes"])):
        ra, rb = _ring(A, na), _ring(B, nb)
        if ra == rb:
            same += 1
        else:
            other += 1
            print(f"node {i}: ring DIFFERS ({len(ra)} vs {len(rb)} points)")
    print(f"rings: identical={same} different={other} (of {len(A['nodes'])} nodes)")

    live_a = {n[3][0] + k for n in A["nodes"] for k in range(n[3][9])}
    live_b = {n[3][0] + k for n in B["nodes"] for k in range(n[3][9])}
    print(f"live verts: native={len(live_a)} ref={len(live_b)} "
          f"(raw Verts array: native={len(A['verts'])} ref={len(B['verts'])})")

    ok = points_same and other == 0 and len(live_a) == len(live_b)
    print("VERIFY:", "PASS (geometry byte-exact; only orphan-vert bookkeeping may still differ)"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
