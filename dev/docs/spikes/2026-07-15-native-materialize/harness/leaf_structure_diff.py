#!/usr/bin/env python3
"""Section 91 — root-cause native leaf OVER-PRODUCTION vs the UnrealEd batch golden.

Native emits 3.6x the empty-leaf cells of UnrealEd's own batch build of the SAME trunk
(UNATCO world-only unlit: native 2759 vs golden 762) while Nodes are near-equal (+1.8%).
This decodes BOTH level Models and walks the front/back BSP tree to attribute WHERE the
extra empty terminal cells come from:

  - node count, coplanar-chain (iPlane) node count, tree-reachable node count,
  - terminal child slots reachable via front/back, split into EMPTY (iLeaf>=0) vs SOLID (-1),
  - empty-vs-solid terminal ratio (the leaf headline),
  - Verts (FVert pool) size + verts-per-node (the +24% Verts/Vectors question),
  - Vectors (plane) count,
  - solid-bound synthetic nodes (NF 0x40 is cleared on disk, so we infer via zero-volume slivers)
  - depth histogram of empty leaves (are native's empties deeper / more fragmented?).

Usage: leaf_structure_diff.py <native.dx> <golden.dx>
"""
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
from uedctl.native import umodel  # noqa: E402
import utexture_decode as UT  # noqa: E402


def load_model(path):
    pkg = UT.load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return umodel.parse_model_body(bytes(pkg.buf), e["soff"], e["ssize"])


def analyze(path):
    m = load_model(path)
    nodes = m.nodes
    N = len(nodes)
    # coplanar-chain members: reached only via iPlane, never via front/back.
    plane_linked = sum(1 for n in nodes if n.i_plane != -1)

    # Walk front/back tree from root 0. Count terminal slots + empty/solid split.
    empty_terms = 0
    solid_terms = 0
    reachable = set()
    empty_depth = Counter()
    # iterative DFS with depth
    stack = [(0, 0)]
    seen_edge = 0
    while stack:
        ni, depth = stack.pop()
        if ni < 0 or ni >= N:
            continue
        if ni in reachable:
            continue
        reachable.add(ni)
        n = nodes[ni]
        # engine order: i_back = FRONT (side1), i_front = BACK (side0). iLeaf[1]<->i_back, iLeaf[0]<->i_front
        for slot_child, slot_leaf in [(n.i_back, n.i_leaf[1]), (n.i_front, n.i_leaf[0])]:
            if slot_child == -1:
                if slot_leaf >= 0:
                    empty_terms += 1
                    empty_depth[depth] += 1
                else:
                    solid_terms += 1
            else:
                stack.append((slot_child, depth + 1))
        # also follow coplanar chain so those nodes counted reachable (they don't add terminals here)
        if n.i_plane != -1:
            stack.append((n.i_plane, depth))

    leaves = len(m.leaves)
    verts = len(m.verts)
    vectors = len(m.vectors)
    points = len(m.points)
    surfs = len(m.surfs)
    # zero-volume solid-bound slivers: a node whose plane ~coincides (opposite) with parent's.
    return {
        "path": Path(path).name,
        "nodes": N,
        "plane_linked": plane_linked,
        "reachable_fb": len(reachable),
        "empty_terms": empty_terms,
        "solid_terms": solid_terms,
        "leaves_array": leaves,
        "verts": verts,
        "verts_per_node": verts / N if N else 0,
        "vectors": vectors,
        "points": points,
        "surfs": surfs,
        "empty_depth": empty_depth,
    }


def main():
    na, ed = sys.argv[1], sys.argv[2]
    A = analyze(na)
    B = analyze(ed)
    keys = ["nodes", "plane_linked", "reachable_fb", "empty_terms", "solid_terms",
            "leaves_array", "verts", "verts_per_node", "vectors", "points", "surfs"]
    print(f"{'metric':<18} {'NATIVE':>12} {'GOLDEN':>12} {'ratio':>8}")
    print("-" * 54)
    for k in keys:
        av, bv = A[k], B[k]
        r = (av / bv) if bv else float("inf")
        print(f"{k:<18} {av:>12.3f} {bv:>12.3f} {r:>7.2f}x" if isinstance(av, float)
              else f"{k:<18} {av:>12} {bv:>12} {r:>7.2f}x")
    print("\nEmpty-leaf DEPTH histogram (depth: native / golden count):")
    alld = sorted(set(A["empty_depth"]) | set(B["empty_depth"]))
    for d in alld:
        print(f"  depth {d:>3}: {A['empty_depth'].get(d,0):>6} / {B['empty_depth'].get(d,0):>6}")
    # summary derived stats
    print("\nDerived:")
    print(f"  native empty/solid term ratio: {A['empty_terms']/max(1,A['solid_terms']):.2f}")
    print(f"  golden empty/solid term ratio: {B['empty_terms']/max(1,B['solid_terms']):.2f}")
    print(f"  native total terminals: {A['empty_terms']+A['solid_terms']}")
    print(f"  golden total terminals: {B['empty_terms']+B['solid_terms']}")


if __name__ == "__main__":
    main()
