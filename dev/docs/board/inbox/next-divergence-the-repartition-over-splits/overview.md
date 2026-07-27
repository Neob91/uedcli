+++
priority = "p2"
kind = "owner-question"
summary = "NEXT DIVERGENCE — the REPARTITION over-splits from a soup-ORDER gap (`FindBestSplit`), not the incremental soup"
+++

# NEXT DIVERGENCE — the REPARTITION over-splits from a soup-ORDER gap (`FindBestSplit`), not the incremental soup

With the soup multiset now exact, `node_diff.py` is
still **0/1156**: native's final tree is **1251 nodes vs editor 1156** (plane multiset 1058 shared /
193 only-native / 98 only-editor — native OVER-splits). The divergence is entirely in
`bspBuild`/`SplitPolyList`/`FindBestSplit`, which consumes the exact soup in a still-different ORDER
→ picks different partition planes. The order gap traces to ~37 residual incremental
fragment-CREATION-order swaps (the `119`/`120`-type coplanar surf-28 pair; and the `#184`
`compare_trees` swap, now a raw-leaf-add artifact the per-brush cleanup reconciles in the final
structure but not in creation order) — §10.8's distinct "byte-identity tree-order" residue.
**Caveat for whoever picks this up:** the golden `Model.Polys` is the POST-`SplitPolyList` array
(reordered in place), NOT a valid oracle for the `SplitPolyList` INPUT order. Build an editor oracle
that dumps `Model->Polys` at the `bspBuild` entry (right after `bspMergeCoplanars` inside
`bspRepartition 0x49fc0`) to compare the true input order, then decide: last incremental emit-order
swaps, or a `FindBestSplit` stride/tie residue. `sections/82 §10.9`.
