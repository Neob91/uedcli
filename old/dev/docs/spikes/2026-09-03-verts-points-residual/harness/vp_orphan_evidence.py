#!/usr/bin/env python3
"""Golden-side evidence check for the orphan-iVertex/points-GC hypothesis.

(1) GOLDEN: how many orphan verts (covered by no node's vert range) name an iVertex that is
    OUT OF RANGE of the final Points pool (dangling stale index), vs in-range; same for native.
(2) NATIVE: for each native point with no golden value-match (the count residual), what
    references it: surf p_base / node-reachable verts / orphan verts only.

Usage: .venv/bin/python vp_orphan_evidence.py <OG.dx>
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair, referenced_vert_indices  # noqa: E402
from vp_structure import match_pools                    # noqa: E402


def orphan_stats(tag: str, model) -> None:
    ref = referenced_vert_indices(model)
    npts = len(model.points)
    out_of_range, in_range = [], 0
    for vi, v in enumerate(model.verts):
        if vi in ref:
            continue
        if not (0 <= v.i_vertex < npts):
            out_of_range.append((vi, v.i_vertex))
        else:
            in_range += 1
    print(f"{tag}: points={npts} orphan verts={in_range + len(out_of_range)} "
          f"(iVertex in-range={in_range}, OUT-OF-RANGE={len(out_of_range)})")
    if out_of_range:
        vals = [x[1] for x in out_of_range]
        print(f"  out-of-range iVertex min={min(vals)} max={max(vals)} sample={out_of_range[:10]}")


def main() -> None:
    native, golden = load_pair(Path(sys.argv[1]))
    orphan_stats("golden", golden)
    orphan_stats("native", native)

    n_pts = [tuple(p) for p in native.points]
    g_pts = [tuple(p) for p in golden.points]
    extra = list((Counter(n_pts) - Counter(g_pts)).elements())
    missing = list((Counter(g_pts) - Counter(n_pts)).elements())
    matches = match_pools(extra, missing, 0.5)
    unmatched = {extra[i] for i, j, _ in matches if j is None}

    idx_of = defaultdict(list)
    for pi, p in enumerate(n_pts):
        if p in unmatched:
            idx_of[p].append(pi)
    want = {pi for v in idx_of.values() for pi in v}
    pbase_ref, reach_ref, orph_ref = defaultdict(int), defaultdict(int), defaultdict(int)
    for s in native.surfs:
        if s.p_base in want:
            pbase_ref[s.p_base] += 1
    ref = referenced_vert_indices(native)
    for vi, v in enumerate(native.verts):
        if v.i_vertex in want:
            (reach_ref if vi in ref else orph_ref)[v.i_vertex] += 1

    only_orphan = only_reach = mixed = unref = 0
    for p, idxs in idx_of.items():
        for pi in idxs:
            r, o, b = reach_ref.get(pi, 0), orph_ref.get(pi, 0), pbase_ref.get(pi, 0)
            if r == 0 and b == 0 and o > 0:
                only_orphan += 1
            elif o == 0 and (r > 0 or b > 0):
                only_reach += 1
            elif o > 0:
                mixed += 1
            else:
                unref += 1
    print(f"native count-residual points: {len(want)} -> orphan-only={only_orphan} "
          f"reachable-only={only_reach} mixed={mixed} unreferenced={unref}")


if __name__ == "__main__":
    main()
