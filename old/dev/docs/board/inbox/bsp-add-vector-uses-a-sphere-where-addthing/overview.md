+++
priority = "p2"
kind = "debug"
summary = "`bsp_add_vector` accepts a pool entry within a EUCLIDEAN distance of the threshold; the editor's `AddThing` tests each component against it independently (a box, strictly looser). Same for `bsp_add_point_tol`'s repartition fallback."
spikes = ["dev/docs/spikes/2026-09-06-island-n6-vector-pool/"]
+++

# `bsp_add_vector` uses a sphere where `AddThing` uses a box

Found 2026-09-06 disassembling `AddThing` (`Editor.dll 0x10031ae0`) while root-causing Island N=6.

`bspAddVector` (`0x10035530`) calls `AddThing(&Model->Vectors, V, Thresh, Check=1)`. `AddThing`'s
scan loop (`0x10031b10`-`0x10031b4f`) accepts the first entry where, per component,
`-Thresh < V.c - P.c < Thresh` — three independent comparisons, i.e. an axis-aligned BOX.
`uedcli-native/src/bspcsg.rs::bsp_add_vector` (and `build.rs`'s copy) instead accepts on
`v.sub(p).size() < tol` — a SPHERE, which is strictly contained in that box, so native can push a
new pool entry where the editor would have merged.

Not the cause of any known divergence: the incremental Vectors pools measured so far match UED22
byte-for-byte. But it got MORE load-bearing on 2026-09-06 — `island-n6-vector-pool-order` made the
incremental pool the one that ships (it is no longer rebuilt from the final surfs), so this dedup now
decides on-disk pool order and length directly. Blast radius is corpus-wide — a looser dedup merges
vectors on every level at once — so closing it needs a full five-level ladder re-verification, not a
drive-by edit.

`bspAddPoint`'s own miss path calls the same `AddThing` (`0x100354ed`), which is the append the
standing stopgap `repartition-point-dedup-still-uses-a-linear` is about; check that item's fix does
not re-introduce a sphere test there either.
