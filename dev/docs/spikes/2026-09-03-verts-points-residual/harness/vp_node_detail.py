#!/usr/bin/env python3
"""Dump full node detail (both sides) for given node indices: links, surf, zone, leaf, ring.

Usage: .venv/bin/python vp_node_detail.py <OG.dx> <node_idx> [...]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair, ring  # noqa: E402


def show(tag, model, i):
    n = model.nodes[i]
    print(f" {tag} node {i}: plane={tuple(round(c, 4) for c in n.plane)} iF={n.i_front} "
          f"iB={n.i_back} iP={n.i_plane} isurf={n.i_surf} nv={n.num_vertices} "
          f"ivp={n.i_vert_pool} izone={n.i_zone} ileaf={n.i_leaf} flags={n.node_flags:#x} "
          f"icb={n.i_collision_bound}")
    for k in range(n.num_vertices):
        v = model.verts[n.i_vert_pool + k]
        print(f"    ring[{k}] pt={tuple(model.points[v.i_vertex])} side={v.i_side}")
    # who points AT this node via i_plane?
    owners = [j for j, m in enumerate(model.nodes) if m.i_plane == i]
    print(f"    iPlane-chain predecessors: {owners}")


def main() -> None:
    native, golden = load_pair(Path(sys.argv[1]))
    for a in sys.argv[2:]:
        i = int(a)
        show("N", native, i)
        show("G", golden, i)
        print()


if __name__ == "__main__":
    main()
