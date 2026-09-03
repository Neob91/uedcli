#!/usr/bin/env python3
"""Multiset-diff the ORPHAN verts (resolved coords) native vs golden, drift-tolerant.

Orphan verts = verts covered by no node ring. Golden orphans with dangling iVertex resolve to
no coord and are bucketed separately. Reports the net extra/missing orphan coords after
nearest-matching within --tol (drift pairing), localizing the verts-count residual's source
region. Usage: .venv/bin/python vp_orphan_multiset.py <OG.dx> [--tol 0.5]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair, referenced_vert_indices  # noqa: E402
from vp_structure import match_pools                    # noqa: E402


def orphan_coords(model):
    ref = referenced_vert_indices(model)
    coords, dangling = [], 0
    for vi, v in enumerate(model.verts):
        if vi in ref:
            continue
        if 0 <= v.i_vertex < len(model.points):
            coords.append(tuple(model.points[v.i_vertex]))
        else:
            dangling += 1
    return coords, dangling


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dx_path")
    ap.add_argument("--tol", type=float, default=0.5)
    args = ap.parse_args()
    native, golden = load_pair(Path(args.dx_path))
    nc, nd = orphan_coords(native)
    gc_, gd = orphan_coords(golden)
    print(f"orphans: native={len(nc)}+{nd} dangling, golden={len(gc_)}+{gd} dangling "
          f"(total d={len(nc)+nd-len(gc_)-gd:+d})")
    n_cnt, g_cnt = Counter(nc), Counter(gc_)
    extra = list((n_cnt - g_cnt).elements())
    missing = list((g_cnt - n_cnt).elements())
    print(f"exact multiset: native-extra={len(extra)} golden-extra={len(missing)}")
    m = match_pools(extra, missing, args.tol)
    hit = set()
    unmatched_n = []
    for i, j, d in m:
        if j is None:
            unmatched_n.append(i)
        else:
            hit.add(j)
    unmatched_g = [j for j in range(len(missing)) if j not in hit]
    print(f"after drift pairing (tol {args.tol}): native-only={len(unmatched_n)} "
          f"golden-only={len(unmatched_g)}")
    print("--- native-only orphan coords ---")
    cnt = Counter(extra[i] for i in unmatched_n)
    for c, k in cnt.most_common(40):
        print(f"   x{k} {c}")
    print("--- golden-only orphan coords ---")
    cnt = Counter(missing[j] for j in unmatched_g)
    for c, k in cnt.most_common(40):
        print(f"   x{k} {c}")


if __name__ == "__main__":
    main()
