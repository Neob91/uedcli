#!/usr/bin/env python3
"""Walk ring blocks in vert-ARRAY order (sorted by i_vert_pool) and report every position where
the native-vs-golden ivp delta CHANGES — i.e. the orphan-slot gap between two consecutive rings
differs. Node rings correspond index-for-index (nv now matches everywhere), so each delta change
brackets exactly where extra/missing orphan slots were allocated.

Usage: .venv/bin/python vp_gap_walk.py <OG.dx>
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
    order_n = sorted(range(len(native.nodes)), key=lambda i: native.nodes[i].i_vert_pool)
    order_g = sorted(range(len(golden.nodes)), key=lambda i: golden.nodes[i].i_vert_pool)
    same_order = order_n == order_g
    print(f"ring blocks in identical array order: {same_order}")
    prev_delta = 0
    prev_ni = None
    changes = 0
    for k, (ni, gi) in enumerate(zip(order_n, order_g)):
        if ni != gi:
            print(f"  ORDER DIVERGES at rank {k}: native node {ni} vs golden node {gi} — stopping")
            break
        d = native.nodes[ni].i_vert_pool - golden.nodes[gi].i_vert_pool
        if d != prev_delta:
            n_gap = (native.nodes[ni].i_vert_pool
                     - (native.nodes[prev_ni].i_vert_pool + native.nodes[prev_ni].num_vertices
                        if prev_ni is not None else 0))
            g_gap = (golden.nodes[gi].i_vert_pool
                     - (golden.nodes[prev_ni].i_vert_pool + golden.nodes[prev_ni].num_vertices
                        if prev_ni is not None else 0))
            changes += 1
            if changes <= 40:
                print(f"  rank {k}: node {ni} ivp {native.nodes[ni].i_vert_pool}/{golden.nodes[gi].i_vert_pool} "
                      f"delta {prev_delta:+d} -> {d:+d}; gap after node {prev_ni}: "
                      f"native {n_gap} vs golden {g_gap} "
                      f"(node {ni}: isurf={native.nodes[ni].i_surf} nv={native.nodes[ni].num_vertices} "
                      f"plane={tuple(round(c,3) for c in native.nodes[ni].plane)})")
            prev_delta = d
        prev_ni = ni
    print(f"total delta changes: {changes}; final delta {prev_delta:+d}; "
          f"tail slots: native {len(native.verts)} golden {len(golden.verts)}")


if __name__ == "__main__":
    main()
