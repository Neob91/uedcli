#!/usr/bin/env python3
r"""Diff the native INCREMENTAL world-tree STRUCTURE against the editor's, for a cached subset.

Two modes, one per target:

* ``--target castle`` (default) — the original §10.8 probe.  Native and the editor build trees of the
  SAME node COUNT for the castle (both 339 at N=33), so an INDEX-for-index compare of
  ``(plane, iFront, iBack, iPlane, iSurf)`` is meaningful and pins the first structural divergence
  (historically node 4, brush 0 — a coplanar-chain-head difference the leaf-add compare cannot see).

* ``--target unatco`` — §92 §23 (this decode refines it).  Here the two trees are DIFFERENT SIZES (native 69 vs editor 101
  at N=8), so an index-for-index compare is meaningless.  Instead this mode does a STRUCTURAL analysis:
  it walks each tree from the root, reports node counts + root planes, the per-FIRST-BRUSH node
  contribution, and the reachable x=448 splitter's ORIENTATION in each — which is what actually
  diverges (see below).

**WHAT §92 §23–§24 DECODED WITH THIS TOOL (UNATCO N=8, editor order == TRUNK order — Brush74 first).**
The editor's golden8 processes brushes in trunk order, so the editor's incremental-tree ROOT is the
first-processed brush's first face.  Editor nodes 0..5 are Brush74's six bar faces (x=448/452,
z=414/416, y=48/64) — i.e. the editor KEEPS the leading Add brush (a thin bar buried in solid).
Native DROPS it entirely: `build_geometry_bspcsg([Brush74])` alone yields **0 nodes**, because native
hardcodes `model.root_outside = false` (bspcsg.rs:2009 — "DX level: solid world, Subtract carves"),
so `bspFilterFPoly`'s empty-tree case classifies the empty world F_INSIDE, and `leaf_func::Add` adds
only on F_OUTSIDE/F_COPLANAR_OUTSIDE → all six bar faces classify F_INSIDE and are dropped.  The
castle stays byte-exact because its FIRST brush is a *Subtract* (`World_7e9y81`), which IS kept on
F_INSIDE; UNATCO simply LEADS with an Add where the castle leads with a Subtract.  That single leading
divergence cascades: the editor's kept bar becomes a permanent solid divider, so the editor's tree
carries the bar's own dead +1,0,0 west face (node 3, nv=0, spliced by bspCleanup into unreachable
garbage) PLUS extra x=448 room-wall fragments (6 vs native's), where native — having dropped the bar —
has only the room-subtract's −1,0,0 wall.  (Both trees' REACHABLE x=448 splitter is −1,0,0 after
cleanup, so even §23's "reachable orientation flip" is imprecise; the robust, reproducible difference
is the 6 kept bar faces.)  Every later subtract touching the bar region then partitions differently
(editor 101 nodes vs native 69).

**This CORRECTS §23's specific "node-33 chain-head" mechanism**, which was measured with native built in
the wrong order (`EDITOR_ORDER=[Brush82,…,Brush74,Brush324]`, Brush74 SEVENTH — the saved-`.dx` iActor
order, not the CSG-processing order).  Under the correct trunk order the divergence is the leading-Add
empty-world seed, not a node-33 descent.  §23's high-level conclusion (native's tree is leaner because
it drops the bar the editor over-keeps) stands; the exact first-divergence is the `root_outside` seed
of the first brush.  §23's "native 52" was the wrong-order build; trunk-order native is **69**.

Inputs:
  * NATIVE  — built in-process with `UEDCLI_BSPCSG_TREE_STRUCT=1` (bspcsg.rs dumps every node's
              plane + child/plane links + surf + nv to stderr, pre-repartition), captured by
              redirecting fd 2 around the (GIL-releasing) build.
  * EDITOR  — `logs/editor-struct-N.log` (castle) or `logs/editor-struct-unatco-N.log` (unatco),
              produced by `editor_struct.py N` / `editor_struct_unatco.py` (gdb dumps `Model->Nodes`
              at the entry to `bspBuildFPolys`, i.e. the incremental tree just before repartition).

Usage:
  tree_struct_diff.py N                       # castle index-diff (needs logs/editor-struct-N.log)
  tree_struct_diff.py N --target unatco       # UNATCO structural analysis (needs the unatco log)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

_NA = re.compile(
    r"STRUCT node=(\d+) plane=\(([-0-9.,]+)\) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) "
    r"isurf=(-?\d+) nf=(\S+) nv=(-?\d+)")
_ED = re.compile(
    r"ND (\d+) plane=([-0-9.,]+) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nv=(-?\d+) nf=(\S+)")

FULL_TRUNK_UNATCO = Path(
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedcli/maps/unatco")


def _native_inputs(n: int, target: str):
    from spike_classindex import class_index   # the schema-aware mover gate's ClassIndex
    from uedcli import trunk
    from uedcli.native import materialize as M
    if target == "castle":
        import castle_build
        level, _ = trunk.read_level(Path(castle_build.TRUNK))
        names = [nm for nm in level.order if level.actors[nm].brush is not None][:n]
    else:  # unatco — TRUNK order, movers dropped (mirrors unatco_subset.native_surfs / the editor golden)
        level, _ = trunk.read_level(FULL_TRUNK_UNATCO)
        order = [nm for nm in level.order if level.actors[nm].brush is not None][:n]
        names = [nm for nm in order if M._in_world_csg(level.actors[nm], class_index())]
    inputs = [M._build_brush_input(nm, level.actors[nm]) for nm in names]
    return names, inputs


def native_struct(n: int, target: str) -> dict[int, tuple]:
    """Build the N-brush native subset with the struct-dump hook; {idx: (plane,iF,iB,iP,isurf,nv)}."""
    import uedcli_native
    _, inputs = _native_inputs(n, target)
    raw = HERE / "logs" / f"native-struct-{target}-{n}.raw"
    raw.parent.mkdir(parents=True, exist_ok=True)
    saved = os.dup(2)
    fd = os.open(str(raw), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.environ["UEDCLI_BSPCSG_TREE_STRUCT"] = "1"
    os.environ["UEDCLI_BSPCSG_NOREPART"] = "1"  # dump fires before repartition regardless; keeps it short
    try:
        os.dup2(fd, 2)
        uedcli_native.build_geometry_bspcsg(inputs)
    finally:
        os.dup2(saved, 2)
        os.close(fd)
        os.close(saved)
    out = {}
    for ln in raw.read_text(errors="replace").splitlines():
        m = _NA.match(ln)
        if m:
            pl = tuple(round(float(x), 2) for x in m[2].split(","))
            out[int(m[1])] = (pl, int(m[3]), int(m[4]), int(m[5]), int(m[6]), int(m[8]))
    raw.unlink(missing_ok=True)
    return out


def editor_struct(n: int, target: str) -> dict[int, tuple]:
    stem = f"editor-struct-{n}.log" if target == "castle" else f"editor-struct-unatco-{n}.log"
    out = {}
    for ln in (HERE / "logs" / stem).read_text().splitlines():
        m = _ED.match(ln)
        if m:
            pl = tuple(round(float(x), 2) for x in m[2].split(","))
            out[int(m[1])] = (pl, int(m[3]), int(m[4]), int(m[5]), int(m[6]), int(m[7]))
    return out


def _reachable(tree: dict[int, tuple], root: int = 0) -> set[int]:
    """Nodes reachable from `root` following iFront/iBack/iPlane (dead nodes stay in the array but
    become unreachable garbage after bspCleanup splices them — §10.9)."""
    seen, stack = set(), [root]
    while stack:
        i = stack.pop()
        if i in seen or i not in tree:
            continue
        seen.add(i)
        _, iF, iB, iP, _, _ = tree[i]
        stack += [c for c in (iF, iB, iP) if c != -1]
    return seen


def _x448(tree: dict[int, tuple], reach: set[int]):
    """The reachable node(s) whose plane is x=448 (either orientation), and the chain-HEAD (the one a
    parent links via iF/iB/iP, i.e. the descent splitter at that plane)."""
    hits = [i for i in reach if abs(abs(tree[i][0][3]) - 448.0) < 0.5
            and abs(tree[i][0][0]) > 0.9 and abs(tree[i][0][1]) < 0.1]
    heads = []
    for i in hits:
        head = any(tree[p][1] == i or tree[p][2] == i or tree[p][3] == i
                   for p in reach if p != i)
        heads.append((i, tree[i][0][0], tree[i][5], "HEAD" if head else "chain"))
    return heads


def _index_diff(na, ed):
    lab = ["plane", "iF", "iB", "iP", "isurf", "nv"]
    first, shown = None, 0
    for i in range(min(len(na), len(ed))):
        if i not in na or i not in ed:
            continue
        n, e = na[i], ed[i]
        diffs = [lab[k] for k in range(6) if n[k] != e[k]]
        struct = [d for d in diffs if d != "nv"]
        if struct and first is None:
            first = i
        if diffs and shown < 8:
            print(f"node {i}: NA {n}  ED {e}  diff={diffs}")
            shown += 1
    print("FIRST STRUCTURAL (non-nv) divergence node:", first)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int)
    ap.add_argument("--target", choices=["castle", "unatco"], default="castle")
    args = ap.parse_args()

    na = native_struct(args.n, args.target)
    ed = editor_struct(args.n, args.target)
    print(f"[{args.target} N={args.n}] native nodes={len(na)}  editor nodes={len(ed)}")

    if args.target == "castle":
        _index_diff(na, ed)
        return 0

    # --- UNATCO structural analysis (sizes differ; index-diff is meaningless) ---
    names, _ = _native_inputs(args.n, args.target)
    print(f"native brush order (trunk, movers dropped): {names}")
    print(f"native root plane: {na.get(0, ('?',))[0]}")
    print(f"editor root plane: {ed.get(0, ('?',))[0]}")

    # Per-first-brush node contribution: build native with ONLY brush[0], count nodes.
    import uedcli_native
    from uedcli import trunk
    from uedcli.native import materialize as M
    level, _ = trunk.read_level(FULL_TRUNK_UNATCO)
    b0 = M._build_brush_input(names[0], level.actors[names[0]])
    raw = HERE / "logs" / "native-struct-unatco-b0.raw"
    saved = os.dup(2); fd = os.open(str(raw), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.environ["UEDCLI_BSPCSG_TREE_STRUCT"] = "1"; os.environ["UEDCLI_BSPCSG_NOREPART"] = "1"
    try:
        os.dup2(fd, 2); uedcli_native.build_geometry_bspcsg([b0])
    finally:
        os.dup2(saved, 2); os.close(fd); os.close(saved)
    b0_nodes = sum(1 for ln in raw.read_text(errors="replace").splitlines() if ln.startswith("STRUCT"))
    raw.unlink(missing_ok=True)
    oper = dict(level.actors[names[0]].props).get("CsgOper", "(absent->Add)")
    print(f"\nFIRST-BRUSH ({names[0]}, oper={oper}) contribution:")
    print(f"  native: {b0_nodes} nodes (0 == the leading Add is DROPPED: root_outside=false → "
          f"empty world F_INSIDE → Add adds only on F_OUTSIDE)")
    print(f"  editor: 6 nodes 0..5 (the bar's faces are KEPT — the leading Add is bootstrapped)")

    nr, er = _reachable(na), _reachable(ed)
    print(f"\nreachable nodes: native {len(nr)}  editor {len(er)}")
    print("x=448 reachable splitters (idx, normal.x, nv, role):")
    print(f"  native: {_x448(na, nr)}")
    print(f"  editor: {_x448(ed, er)}")
    print("\n=> FIRST DIVERGENCE: the leading Add brush (Brush74). native drops it (root_outside=false);"
          "\n   the editor keeps its 6 faces. Everything downstream (x=448 orientation, node count 69 vs"
          "\n   101) cascades from this. See the module docstring / §92 §23 + this module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
