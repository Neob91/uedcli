#!/usr/bin/env python3
r"""Python REFERENCE of the editor's `bspCleanup`/`CleanupNodes` dead-node splice — the rule that was
decoded from `Editor.dll` (RVA `0x36160` -> recursive worker `0x32100`) and ported to Rust
(`bspcsg.rs::cleanup_nodes`).  See `sections/82` §10.9 for the full decode + evidence.

`CleanupNodes(iNode, iParent)` walks the incremental BSP tree from the root, recursing children
(iFront, iBack, iPlane) FIRST, then splices out every DEAD node (`NumVertices == 0`):

  * **Case A — dead node with an iPlane successor P:** promote P.  P inherits the dead node's
    iFront/iBack, SWAPPED when P faces the opposite way (`Node.Normal · P.Normal < 0`, threshold
    `0.0` via `FPlane::operator|`).  The parent is repointed (whichever of iFront/iBack/iPlane
    pointed at the dead node) to P.  Root special-case: copy P into the root slot, mark P dead.
  * **Case B — dead node, no iPlane successor:** if it has BOTH children keep it (pure splitter);
    else repoint the parent to its single child (or -1).

Dead nodes are NOT removed from the array (indices stay stable); they just become unreachable.

This script proves the rule: it applies `CleanupNodes` to the PRE-repartition native struct (built
via tree_struct_diff.native_struct, i.e. `UEDCTL_BSPCSG_NOREPART=1`+`UEDCTL_BSPCSG_TREE_STRUCT=1`) and
shows the resulting `MakeEdPolys` tree-walk (self,front,back,plane) emits the SAME node sequence as
the editor's post-cleanup struct (`editor_struct.py N` -> `logs/editor-struct-N.log`).  The reachable
emit structure matches node-for-node; only unreachable orphaned dead-node links differ.

Usage:  cleanup_proto.py N          # needs logs/editor-struct-N.log
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tree_struct_diff as TSD  # native_struct(n) builds the pre-repartition native node table

_ED = re.compile(
    r"ND (\d+) plane=([-0-9.,]+) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nv=(-?\d+) nf=(\S+)")


class Node:
    __slots__ = ("plane", "iF", "iB", "iP", "surf", "nv", "nf")

    def __init__(self, plane, iF, iB, iP, surf, nv, nf=0):
        self.plane, self.iF, self.iB, self.iP = plane, iF, iB, iP
        self.surf, self.nv, self.nf = surf, nv, nf


def load_native(n: int) -> list[Node]:
    raw = TSD.native_struct(n)  # {idx: (plane, iF, iB, iP, isurf, nv)}
    return [Node(raw[i][0], raw[i][1], raw[i][2], raw[i][3], raw[i][4], raw[i][5]) for i in range(len(raw))]


def load_editor(n: int) -> list[Node]:
    d = {}
    for ln in (HERE / "logs" / f"editor-struct-{n}.log").read_text().splitlines():
        m = _ED.match(ln)
        if m:
            pl = tuple(float(x) for x in m[2].split(","))
            d[int(m[1])] = Node(pl, int(m[3]), int(m[4]), int(m[5]), int(m[6]), int(m[7]))
    return [d[i] for i in range(len(d))]


def cleanup_nodes(nodes: list[Node]) -> None:
    sys.setrecursionlimit(200000)

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def rec(i: int, parent: int) -> None:
        nd = nodes[i]
        nd.nf &= 0x1F
        if nd.iF != -1:
            rec(nd.iF, i)
        if nd.iB != -1:
            rec(nd.iB, i)
        if nd.iP != -1:
            rec(nd.iP, i)
        if nd.nv != 0:
            return  # alive: keep
        if nd.iP != -1:  # Case A
            q = nodes[nd.iP]
            if dot(nd.plane, q.plane) >= 0.0:
                q.iF, q.iB = nd.iF, nd.iB
            else:
                q.iF, q.iB = nd.iB, nd.iF
            if parent == -1:  # root: copy successor into slot, mark it dead
                nd.plane, nd.iF, nd.iB, nd.iP = q.plane, q.iF, q.iB, q.iP
                nd.surf, nd.nv, nd.nf = q.surf, q.nv, q.nf
                q.nv = 0
                return
            pn = nodes[parent]
            if pn.iF == i:
                pn.iF = nd.iP
            elif pn.iB == i:
                pn.iB = nd.iP
            elif pn.iP == i:
                pn.iP = nd.iP
            return
        # Case B
        f, b = nd.iF, nd.iB
        if f != -1 and b != -1:
            return  # keep as splitter
        child = f if f != -1 else b
        if parent == -1:
            return
        pn = nodes[parent]
        if pn.iF == i:
            pn.iF = child
        elif pn.iB == i:
            pn.iB = child
        elif pn.iP == i:
            pn.iP = child

    if nodes:
        rec(0, -1)


def make_ed_polys(nodes: list[Node]) -> list[tuple]:
    """MakeEdPolys pre-order walk (self, front, back, plane); emit nv>0 nodes as (idx, surf)."""
    sys.setrecursionlimit(200000)
    seq: list[tuple] = []

    def rec(i: int) -> None:
        nd = nodes[i]
        if nd.nv > 0:
            seq.append((i, nd.surf))
        if nd.iF != -1:
            rec(nd.iF)
        if nd.iB != -1:
            rec(nd.iB)
        if nd.iP != -1:
            rec(nd.iP)

    if nodes:
        rec(0)
    return seq


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    na = load_native(n)
    ed = load_editor(n)
    cleanup_nodes(na)
    tn, te = make_ed_polys(na), make_ed_polys(ed)
    print(f"N={n}: native-emit={len(tn)} editor-emit={len(te)}")
    diffs = [k for k in range(min(len(tn), len(te))) if tn[k] != te[k]]
    if not diffs:
        print("MakeEdPolys emit sequence (idx, surf) IDENTICAL — cleanup rule reproduces the editor.")
    else:
        print(f"first emit divergence at pos {diffs[0]}: NA{tn[diffs[0]]} ED{te[diffs[0]]}  ({len(diffs)} diffs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
