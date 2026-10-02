#!/usr/bin/env python3
r"""Diff native's post-repartition node array against the editor's, node for node.

Pairs `repart_tree_unatco.py` (the live editor capture at `Editor.dll 0x1004a05f`) with native's own
`UEDCLI_BSPCSG_REPART_NODES` dump — both emit the same `RNODE` line format, from the same point in
the pipeline (right after `bspRefresh` inside `bspRepartition`).

`iSurf` is NOT compared for equality: native rebuilds the Surfs pool in split-recursion order while
the editor keeps its incremental-CSG pool, so the two numberings are a permutation of each other.
What is checked instead is that the mapping is a consistent BIJECTION — if native's surf `a` ever
pairs with two different editor surfs (or vice versa), the trees are not the same tree.

Usage:  repart_tree_diff.py <native.log> <editor.log>
"""
import re
import sys
from collections import Counter

RNODE = re.compile(r"^RNODE (\d+) isurf=(-?\d+) nv=(\d+) iB=(-?\d+) iF=(-?\d+) iP=(-?\d+) nf=(\d+) "
                   r"plane=([-0-9.e]+),([-0-9.e]+),([-0-9.e]+),([-0-9.e]+)")
PLANE_TOL = 0.05  # looks past the separately-filed ~100-ULP rotated-brush normal drift


def load(path):
    out = []
    for line in open(path, errors="replace"):
        m = RNODE.match(line)
        if m:
            out.append(dict(i=int(m[1]), isurf=int(m[2]), nv=int(m[3]), iB=int(m[4]), iF=int(m[5]),
                            iP=int(m[6]), nf=int(m[7]),
                            plane=tuple(float(m[k]) for k in (8, 9, 10, 11))))
    return out


def main():
    nat, ed = load(sys.argv[1]), load(sys.argv[2])
    print(f"native {len(nat)} nodes, editor {len(ed)} nodes")
    bad, first = Counter(), []
    for a, b in zip(nat, ed):
        d = [f for f in ("nv", "iB", "iF", "iP", "nf") if a[f] != b[f]]
        if max(abs(x - y) for x, y in zip(a["plane"], b["plane"])) > PLANE_TOL:
            d.append("plane")
        for f in d:
            bad[f] += 1
        if d and len(first) < 15:
            first.append((a["i"], d, a, b))
    print(f"field mismatches over {min(len(nat), len(ed))} aligned nodes: {dict(bad)}")
    for i, d, a, b in first:
        print(f"  idx {i} {d}\n    nat {a}\n    ed  {b}")

    fwd, rev, ok = {}, {}, True
    for a, b in zip(nat, ed):
        ok &= fwd.setdefault(a["isurf"], b["isurf"]) == b["isurf"]
        ok &= rev.setdefault(b["isurf"], a["isurf"]) == a["isurf"]
    print(f"isurf is a consistent bijection: {ok} "
          f"({len(fwd)} native surfs used, {len(rev)} editor surfs used)")


if __name__ == "__main__":
    main()
