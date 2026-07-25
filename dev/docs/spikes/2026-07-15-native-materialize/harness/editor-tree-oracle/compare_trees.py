#!/usr/bin/env python3
r"""COMPARE the editor-tree oracle log against the native NADD log for the SAME N-brush subset.

Aligns the two incremental world-BSP LEAF-ADD streams and reports the first position where they
diverge — the concrete first-diverging incremental add that §82 §10.5/§10.6 pinned only from the
final tree.

Stream selection:
  * NATIVE  — `native-N.log`, `phase=ADD` lines (the LOOP-2 `leaf_func` Add — the brush face added
              as it reaches a world-tree leaf).  `phase=SUB`/`FWTB` are compared by COUNT only.
  * EDITOR  — `oracle-N.log`, world model + `ret=0x100317df` lines (`AddBrushToWorldFunc` leaf add,
              the editor's LOOP-2 counterpart — count-verified 1:1 with native `phase=ADD`).

Each add is reduced to a plane-normalised key `(place, ilink, nv, N, d)` where `d = N·B` is the
plane offset — so a different BASE POINT on the SAME plane (e.g. roof `z=248` at `(160,160)` vs
`(217.28,136.27)`) is treated as EQUAL (bspAddNode stores the plane, not the base; base only moves
the texture origin).  `parent` node index is NOT compared: it drifts because SUB/FWTB adds
interleave and shift indices between the two builds.

Usage:  compare_trees.py N   # aligns logs/oracle-N.log vs logs/native-N.log
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"

_ED = re.compile(
    r"^ADD ret=(?P<ret>0x[0-9a-f]+) model=(?P<model>0x[0-9a-f]+) parent=(?P<parent>-?\d+) "
    r"place=(?P<place>-?\d+) flags=(?P<flags>0x[0-9a-f]+) ilink=(?P<ilink>-?\d+) nv=(?P<nv>\d+) "
    r"N=(?P<nx>[-0-9.]+),(?P<ny>[-0-9.]+),(?P<nz>[-0-9.]+) "
    r"B=(?P<bx>[-0-9.]+),(?P<by>[-0-9.]+),(?P<bz>[-0-9.]+)")
_NA = re.compile(
    r"^NADD phase=(?P<phase>\w+) node=(?P<node>-?\d+) parent=(?P<parent>-?\d+) "
    r"place=(?P<place>-?\d+) flags=(?P<flags>0x[0-9a-f]+) ilink=(?P<ilink>-?\d+) nv=(?P<nv>\d+) "
    r"N=(?P<nx>[-0-9.]+),(?P<ny>[-0-9.]+),(?P<nz>[-0-9.]+) "
    r"B=(?P<bx>[-0-9.]+),(?P<by>[-0-9.]+),(?P<bz>[-0-9.]+)")

EDITOR_LOOP2_RET = "0x100317df"   # AddBrushToWorldFunc leaf add (editor LOOP-2 Add)


def _key(m):
    nx, ny, nz = float(m["nx"]), float(m["ny"]), float(m["nz"])
    bx, by, bz = float(m["bx"]), float(m["by"]), float(m["bz"])
    d = nx * bx + ny * by + nz * bz               # plane offset (base-point-invariant)
    return (int(m["place"]), int(m["ilink"]), int(m["nv"]),
            round(nx, 3), round(ny, 3), round(nz, 3), round(d, 2))


def _geo_key(m):
    """The GEOMETRIC key — the full key MINUS `ilink`.  `ilink` is the coplanar-surf link INDEX; like
    `parent` it drifts by a constant base offset once native and the editor allocate a different number
    of surfs earlier (UNATCO N=104 control: all 81 adds geometrically identical, `ilink` editor==native+6
    for EVERY add — a benign surf-index label drift, NOT a routing divergence).  Keying the divergence
    hunt on geometry (place, nv, plane normal, plane offset) pins the first REAL facet/routing
    disagreement instead of stopping at add #0 on the constant `ilink` offset."""
    return (m[0], m[2], m[3], m[4], m[5], m[6])   # place, nv, nx, ny, nz, d  (drop ilink at idx 1)


def _fmt(k):
    place, ilink, nv, nx, ny, nz, d = k
    return f"place={place} ilink={ilink} nv={nv} N=({nx:+.3f},{ny:+.3f},{nz:+.3f}) d={d:+.2f}"


def load_editor(n: int):
    rows = []
    world_model = None
    counts = {}
    for ln in (LOGS / f"oracle-{n}.log").read_text().splitlines():
        m = _ED.match(ln)
        if not m:
            continue
        counts[m["ret"]] = counts.get(m["ret"], 0) + 1
        if m["ret"] == EDITOR_LOOP2_RET:
            rows.append((_key(m), m))
    return rows, counts


def load_native(n: int):
    add, phase_counts = [], {}
    for ln in (LOGS / f"native-{n}.log").read_text().splitlines():
        m = _NA.match(ln)
        if not m:
            continue
        phase_counts[m["phase"]] = phase_counts.get(m["phase"], 0) + 1
        if m["phase"] == "ADD":
            add.append((_key(m), m))
    return add, phase_counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int)
    args = ap.parse_args()
    n = args.n

    ed, ed_counts = load_editor(n)
    na, na_counts = load_native(n)

    print(f"=== N={n} ===")
    print(f"editor ret-call-site counts: {ed_counts}")
    print(f"native phase counts:         {na_counts}")
    print(f"editor LOOP-2 (ret={EDITOR_LOOP2_RET}) adds: {len(ed)}   native phase=ADD: {len(na)}")
    print()

    lim = min(len(ed), len(na))

    # ilink label-drift trend (diagnostic): a CONSTANT editor-native ilink delta across all shared
    # positions is a benign surf-index base offset; the position where the delta first CHANGES is where
    # the surf allocation itself diverges (native over-produces a surf the editor lacks — the dome).
    deltas = [ed[i][0][1] - na[i][0][1] for i in range(lim)]
    from collections import Counter
    print(f"ilink (editor-native) delta distribution: {dict(sorted(Counter(deltas).items()))}")
    dc = next((i for i in range(1, lim) if deltas[i] != deltas[i - 1]), None)
    print(f"first ilink-delta CHANGE at add #{dc}" if dc is not None
          else "ilink delta constant over all shared positions")
    print()

    # FIRST GEOMETRIC divergence (place, nv, plane) — the real facet/routing disagreement.
    first = next((i for i in range(lim) if _geo_key(ed[i][0]) != _geo_key(na[i][0])), None)
    if first is None:
        if len(ed) == len(na):
            print("LOOP-2 ADD streams are GEOMETRICALLY IDENTICAL (place/nv/plane); only ilink labels drift.")
            return 0
        first = lim
        print(f"streams agree geometrically for all {lim} shared positions but differ in LENGTH "
              f"(editor {len(ed)} vs native {len(na)}).")
    else:
        print(f"FIRST GEOMETRIC LOOP-2 DIVERGENCE at leaf-add #{first}:")
    lo = max(0, first - 3)
    hi = min(lim, first + 4)
    for i in range(lo, hi):
        mark = " <== FIRST GEO DIFF" if i == first else ""
        eq = "==" if (i < lim and _geo_key(ed[i][0]) == _geo_key(na[i][0])) else "!="
        print(f"  [{i:4d}] EDITOR {_fmt(ed[i][0])}")
        print(f"         NATIVE {_fmt(na[i][0])}   {eq}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
