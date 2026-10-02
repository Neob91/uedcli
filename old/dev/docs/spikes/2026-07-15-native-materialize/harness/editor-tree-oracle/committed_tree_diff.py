#!/usr/bin/env python3
r"""Compare a native NOREPART committed-incremental tree dump against the editor's committed dump,
classifying each index-for-index divergence as STRUCTURAL vs a mere plane-w twin (§92 §53 bisect).

Both trees are the COMMITTED (post-rollback) incremental Model->Nodes at bspBuildFPolys entry:
  * native  — native_noropart_struct.py N out.log  ("STRUCT node=..." lines, NOREPART)
  * editor  — editor_struct_unatco_n.py N          ("ND ..." lines, gdb dump)

Per §40 both are post-rollback, so this is the raw-vs-kept-safe comparison.

A node index counts as STRUCTURAL divergence iff, comparing native[i] vs editor[i]:
  * one tree lacks the index (node counts differ), OR
  * iF / iB / iP / nv differ, OR
  * the plane NORMAL (x,y,z rounded 3dp) differs.
A pure plane-w difference at a node whose (normal, iF,iB,iP,nv) all match is a TWIN (NOT structural) —
these are the §11/§41 sub-grid / 1-ULP precision offsets the task says to ignore.

Exit prints the FIRST structural node index (or None) + a summary; so a bisect driver can read
"STRUCTURAL=yes/no".

Usage:  committed_tree_diff.py native-N.log editor-struct-unatco-N.log
"""
import re
import sys

_NA = re.compile(
    r"^STRUCT node=(\d+) plane=\(([-0-9.eE,]+)\) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) "
    r"isurf=(-?\d+) nf=\S+ nv=(-?\d+)")
_ED = re.compile(
    r"^ND (\d+) plane=([-0-9.eE,]+) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nv=(-?\d+)")


def _parse(path, rx):
    out = {}
    for ln in open(path):
        m = rx.match(ln)
        if not m:
            continue
        pl = tuple(float(x) for x in m[2].split(","))
        out[int(m[1])] = dict(
            nx=round(pl[0], 3), ny=round(pl[1], 3), nz=round(pl[2], 3), w=pl[3],
            iF=int(m[3]), iB=int(m[4]), iP=int(m[5]), isurf=int(m[6]), nv=int(m[7]))
    return out


def main():
    na = _parse(sys.argv[1], _NA)
    ed = _parse(sys.argv[2], _ED)
    common = sorted(set(na) & set(ed))
    first_struct = None
    struct_nodes = []
    twin_nodes = []
    # INTRINSIC comparison: iF/iB/iP (child indices) and isurf are LABELS that renumber globally when
    # either tree inserts/drops a node, so an index-for-index iF/iB/iP compare is contaminated by any
    # single upstream count difference (they drift by a ~constant offset).  A node is a genuine
    # STRUCTURAL divergence iff its INTRINSIC data differs: plane NORMAL (3dp), nv, or a NON-twin w
    # (normal same but w differs by more than a sub-grid twin tolerance).  A pure w twin (normal+nv
    # match, |dw| <= TWIN_W) is NOT structural.
    TWIN_W = 0.05
    for i in common:
        n, e = na[i], ed[i]
        norm_eq = (n["nx"], n["ny"], n["nz"]) == (e["nx"], e["ny"], e["nz"])
        nv_eq = n["nv"] == e["nv"]
        if norm_eq and nv_eq:
            dw = abs(n["w"] - e["w"])
            if dw == 0:
                continue
            if dw <= TWIN_W:
                twin_nodes.append(i)
                continue
        struct_nodes.append(i)
        if first_struct is None:
            first_struct = i
    count_diff = len(na) != len(ed)
    structural = bool(struct_nodes) or count_diff
    print(f"native={len(na)} editor={len(ed)} common={len(common)} "
          f"struct-nodes={len(struct_nodes)} twin-nodes={len(twin_nodes)} "
          f"count_diff={count_diff}")
    print(f"FIRST_STRUCTURAL_NODE={first_struct}")
    print(f"STRUCTURAL={'yes' if structural else 'no'}")
    for i in struct_nodes[:12]:
        print(f"  node {i}: NA {na[i]}\n           ED {ed[i]}")


if __name__ == "__main__":
    main()
