#!/usr/bin/env python3
"""Find WHERE the extra vert(s) sit in the Verts array (d_verts=+1 levels).

Aligns native.verts against golden.verts entry-by-entry (resolved point coord within tol +
same i_side), reports the first misaligned index and whether shifting native by +1 from
there re-aligns the tail — bracketing the inserted entry. Also prints the surrounding
entries and which node (if any) covers each region.

Usage: .venv/bin/python vp_insertion_point.py <OG.dx> [--tol 0.1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair  # noqa: E402


def coord(model, v):
    if 0 <= v.i_vertex < len(model.points):
        return tuple(model.points[v.i_vertex])
    return ("DANGLING", v.i_vertex)


def eq(model_a, va, model_b, vb, tol) -> bool:
    ca, cb = coord(model_a, va), coord(model_b, vb)
    if isinstance(ca[0], str) or isinstance(cb[0], str):
        return isinstance(ca[0], str) and isinstance(cb[0], str)
    return all(abs(x - y) <= tol for x, y in zip(ca, cb))


def covering_node(model, vi: int):
    for ni, n in enumerate(model.nodes):
        if n.i_vert_pool <= vi < n.i_vert_pool + n.num_vertices:
            return ni
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dx_path")
    ap.add_argument("--tol", type=float, default=0.1)
    args = ap.parse_args()
    native, golden = load_pair(Path(args.dx_path))
    nv, gv = native.verts, golden.verts
    n = min(len(nv), len(gv))

    shift = 0
    i = 0
    events = []
    while i + shift < len(nv) and i < len(gv):
        if eq(native, nv[i + shift], golden, gv[i], args.tol):
            i += 1
            continue
        # try increasing the shift (a native insertion here)
        probe = shift + 1
        # verify the next 32 entries align under the new shift
        ok = all(
            eq(native, nv[i + k + probe], golden, gv[i + k], args.tol)
            for k in range(min(32, len(gv) - i, len(nv) - i - probe))
        )
        if ok:
            vi = i + shift
            events.append(("insert", vi))
            print(f"NATIVE INSERTION at native vert index {vi}: "
                  f"{coord(native, nv[vi])} i_side={nv[vi].i_side} "
                  f"(covered by node {covering_node(native, vi)})")
            for k in range(max(0, vi - 3), min(len(nv), vi + 4)):
                print(f"   native[{k}] {coord(native, nv[k])} side={nv[k].i_side}"
                      + ("   <-- extra" if k == vi else ""))
            shift = probe
            continue
        # genuine local mismatch (drift beyond tol or order swap) — skip it
        events.append(("mismatch", i))
        i += 1
    print(f"total events: {len(events)} "
          f"({sum(1 for e in events if e[0] == 'insert')} insertions, "
          f"{sum(1 for e in events if e[0] == 'mismatch')} local mismatches)")
    mism = [e[1] for e in events if e[0] == "mismatch"]
    if mism:
        print("first local mismatches:", mism[:20])


if __name__ == "__main__":
    main()
