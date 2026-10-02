#!/usr/bin/env python3
"""Localize the verts-count residual: where in the Verts array do native/golden diverge?

Compares per-node `i_vert_pool` (same node index both sides; rings themselves are near-identical
on these levels), bracketing where extra orphan verts were inserted, and lists nodes whose
`num_vertices` differ. Usage: .venv/bin/python vp_vert_locus.py <OG.dx>
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair  # noqa: E402


def main() -> None:
    native, golden = load_pair(Path(sys.argv[1]))
    n_nodes, g_nodes = native.nodes, golden.nodes
    print(f"verts native={len(native.verts)} golden={len(golden.verts)} "
          f"d={len(native.verts)-len(golden.verts):+d}")

    nv = [(i, a.num_vertices, b.num_vertices, a.i_surf, b.i_surf)
          for i, (a, b) in enumerate(zip(n_nodes, g_nodes)) if a.num_vertices != b.num_vertices]
    print(f"nodes with nv diff: {len(nv)}")
    for row in nv[:30]:
        i = row[0]
        print(f"  node={i} nv {row[1]} vs {row[2]} i_surf=({row[3]},{row[4]}) "
              f"plane_n={tuple(round(c,3) for c in n_nodes[i].plane)} "
              f"plane_g={tuple(round(c,3) for c in g_nodes[i].plane)}")

    # i_vert_pool delta runs: group consecutive node indices by (native_ivp - golden_ivp).
    runs = []
    prev = None
    for i, (a, b) in enumerate(zip(n_nodes, g_nodes)):
        d = a.i_vert_pool - b.i_vert_pool
        if d != prev:
            runs.append([i, i, d, a.i_vert_pool, b.i_vert_pool])
            prev = d
        else:
            runs[-1][1] = i
    print(f"i_vert_pool delta runs: {len(runs)} (showing nonzero-delta boundaries)")
    for r in runs[:60]:
        print(f"  nodes[{r[0]}..{r[1]}] d_ivp={r[2]:+d} (native_ivp@start={r[3]} golden={r[4]})")


if __name__ == "__main__":
    main()
