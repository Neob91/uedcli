+++
priority = "p2"
kind = "debug"
summary = "Repartition point dedup still uses a linear scan, not FindNearestVertex"
+++

# Repartition point dedup still uses a linear scan, not FindNearestVertex

Native runs the editor's radius-pruned `FindNearestVertex` descent only inside `bsp_brush_csg`
(`FNV_DEDUP`, `bspcsg.rs`). Repartition (`bsp_build`) falls back to a linear scan over the retained
points pool. `bsp_add_point_tol`'s comment justifies that with "a descent over the empty rebuilding
tree would append duplicates".

The disasm says otherwise. `bspAddPoint` (Editor.dll `0x35430`) calls `FindNearestVertex`
unconditionally for every caller, and `bspBuild` (`0x35ef0`) calls `EmptyModel(0,0)` (`0x35f68`) and
then grows nodes through `bspAddNode` → `bspAddPoint`. So the editor DOES descend the emptied tree
and DOES append the duplicates native's comment treats as a reason to avoid it — that is the
editor's behaviour, not an artifact.

Consequence: a repartition re-add landing in a near-tie snaps to a sibling the editor's descent
could not reach — the same class fixed for incremental CSG when WanChai N20 exposed it (commit
"Dedup the CSG ring point add through FindNearestVertex too"). Latent: near-ties are rare at low N,
and the ladder is green to WanChai N30 / UNATCO N24 / Bar N24 / Island N16 with the scan in place.

Found by an opus review of that commit, 2026-09-05. Out of scope there (one-line change). Needs a
measurement (does routing repartition through the descent hold the ladder?) before any change —
and, per the prime directive, the faithful answer is probably yes.
