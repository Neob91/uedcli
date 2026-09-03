#!/usr/bin/env python3
"""Decompose a level's verts/points COUNT residual into structural buckets.

Verts: split d_verts into (a) per-node num_vertices deltas (same index both sides) and
(b) orphan-vert delta (verts covered by no node's [i_vert_pool, +nv) range).

Points: bipartite nearest-match native<->golden pools (tol) to separate VALUE drift
(1:1 pairs, count-neutral) from count-affecting cases: a golden point matched by 2+ native
points (native dedup miss, +1 each) and native points with no golden match within tol
(genuine extra), and vice versa.

Usage: .venv/bin/python vp_structure.py <OG.dx> [--tol 0.5]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair, referenced_vert_indices  # noqa: E402


def match_pools(a: list[tuple], b: list[tuple], tol: float):
    """For each coord in multiset `a`, nearest coord in `b` within tol (grid-bucketed)."""
    cell = max(tol, 1e-6)
    grid: dict[tuple, list[int]] = defaultdict(list)
    for j, q in enumerate(b):
        grid[tuple(int(c // cell) for c in q)].append(j)
    out = []
    for i, p in enumerate(a):
        key = tuple(int(c // cell) for c in p)
        best, bd = None, tol
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        q = b[j]
                        d = max(abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2]))
                        if d <= bd:
                            best, bd = j, d
        out.append((i, best, bd))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dx_path")
    ap.add_argument("--tol", type=float, default=0.5)
    args = ap.parse_args()
    native, golden = load_pair(Path(args.dx_path))

    # --- verts decomposition ---
    nv_delta = sum(native.nodes[i].num_vertices - golden.nodes[i].num_vertices
                   for i in range(len(native.nodes)))
    n_orph = len(native.verts) - len(referenced_vert_indices(native))
    g_orph = len(golden.verts) - len(referenced_vert_indices(golden))
    print(f"d_verts={len(native.verts)-len(golden.verts):+d} = ring(nv) {nv_delta:+d} "
          f"+ orphan {n_orph-g_orph:+d}   (orphans native={n_orph} golden={g_orph})")

    # --- points matching ---
    n_pts = [tuple(p) for p in native.points]
    g_pts = [tuple(p) for p in golden.points]
    n_exact = Counter(n_pts)
    g_exact = Counter(g_pts)
    extra = list((n_exact - g_exact).elements())    # native coords not exactly in golden
    missing = list((g_exact - n_exact).elements())
    print(f"d_points={len(n_pts)-len(g_pts):+d}  exact-mismatch: native-extra={len(extra)} "
          f"golden-extra={len(missing)}")

    m = match_pools(extra, missing, args.tol)
    hit_by: dict[int, list[int]] = defaultdict(list)
    unmatched_native = []
    for i, j, d in m:
        if j is None:
            unmatched_native.append(i)
        else:
            hit_by[j].append(i)
    multi = {j: v for j, v in hit_by.items() if len(v) > 1}
    unmatched_golden = [j for j in range(len(missing)) if j not in hit_by]
    print(f"paired 1:1 drift: {sum(1 for v in hit_by.values() if len(v) == 1)}")
    print(f"dedup-miss (2+ native -> 1 golden): {len(multi)} golden coords, "
          f"{sum(len(v) for v in multi.values())} native coords")
    print(f"native unmatched (no golden within {args.tol}): {len(unmatched_native)}")
    print(f"golden unmatched (no native matched it): {len(unmatched_golden)}")
    print("--- native unmatched coords ---")
    for i in unmatched_native[:40]:
        print("  ", extra[i])
    print("--- golden unmatched coords ---")
    for j in unmatched_golden[:40]:
        print("  ", missing[j])
    print("--- dedup-miss clusters (golden coord <- native coords) ---")
    for j, v in list(multi.items())[:20]:
        print("  ", missing[j], "<-", [extra[i] for i in v])


if __name__ == "__main__":
    main()
