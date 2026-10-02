#!/usr/bin/env python3
"""Pins Pass D's kill-the-original rule and its `bspCleanup` promotion — the OceanLab N=46 fix.

`AssignAllZones` (`Editor.dll 0xa7400`, `re-raw-zones/passD-assignzones-7400.md` §1) ends a
zone-SPLIT with `Nodes[i].NumVertices = 0` on the ORIGINAL chain node and keeps one freshly
`bspAddNode`d fragment per surviving zone — appended at the tail of the owner's coplanar (`iPlane`)
chain. The post-Pass-D `bspCleanup` (§70 §1 pass table) then splices the dead original out via
`cleanup_nodes` Case A: its coplanar successor is PROMOTED into its place and inherits its
`iFront`/`iBack`, swapped when the two planes face opposite ways.

Native used to skip both steps — it kept the original alive and reused it as the first fragment. On
OceanLab N=46 the original was a chain HEAD, so native shipped the chain headed by the split node
(with its children) where UED22 ships it headed by the promoted successor, and the two `Bounds` /
`LeafHulls` / `LightMap` walks diverged from there.

Checked against the cached built packages (no editor, no build): on OceanLab N=46 the split group
(the two nodes sharing surf 198) is the chain TAIL and the array's last two nodes — the exact shape
the old code got backwards, in UED22's own output and in native's alike.

Run: python3 test_passd_kills_the_split_original.py     (or via pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

import parity_gate as G              # noqa: E402
from model_dump import decode, find  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity"
# model_dump's node tuple: (plane, zone_mask, node_flags, cis, iLeaf-bytes); cis positions:
I_SURF, I_FRONT, I_PLANE = 1, 3, 4


def world_nodes(pkg: Path) -> list:
    p = G.load_package(str(pkg))
    return decode(p, find(p, "model2"))["nodes"]


def test_oceanlab_n46_split_group_is_the_chain_tail():
    for name in ("ref_N46.dx", "native_N46.dx"):
        pkg = CACHE / "14_oceanlab_lab" / name
        if not pkg.exists():
            print(f"{pkg} absent — skipped")
            continue
        nodes = world_nodes(pkg)
        # The x=-64 chain the fix moved: walk it from its head (node 50's front child).
        chain, i = [], nodes[50][3][I_FRONT]
        while i != -1:
            chain.append(i)
            i = nodes[i][3][I_PLANE]
        surfs = [nodes[i][3][I_SURF] for i in chain]
        # Old (retain-the-original) behaviour put surf 198 first; the editor puts it last.
        assert surfs == [183, 187, 213, 198, 198], (
            f"{name}: the Pass-D split group must be the chain TAIL, got {surfs}"
        )
        assert chain[-2:] == [len(nodes) - 2, len(nodes) - 1], (
            f"{name}: the split fragments must be the node array's tail cluster, got {chain}"
        )


if __name__ == "__main__":
    test_oceanlab_n46_split_group_is_the_chain_tail()
    print("OK")
