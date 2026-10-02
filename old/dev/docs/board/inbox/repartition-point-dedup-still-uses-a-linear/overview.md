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

## The miss path is now decoded — there is no second rule (2026-09-06)

On an FNV miss `bspAddPoint` calls `AddThing(&Model->Points, V, Thresh, !FastRebuild)`
(`Editor.dll 0x354d1`-`0x354ed`), and `csgRebuild` sets `FastRebuild = 1` (`0x4a69f`-`0x4a6a8`,
`or eax,1` into `UEditorEngine+0x10c`). With the check argument 0, `AddThing` (`0x31ae0`) skips its
scan entirely and appends. So during a rebuild the editor's whole rule is: **descend, else append** —
the same rule native already runs under `FNV_DEDUP`. The linear scan has no counterpart in the
binary at either setting, so it is a STOPGAP over an algorithmic divergence, not an approximation of
something.

(`AddThing`'s scan, for when `FastRebuild` is 0: FIRST entry whose every component satisfies
`-Thresh < d < Thresh` — a per-axis box test, not a Euclidean ball and not a nearest-selection.
Native's `bsp_add_vector` uses a Euclidean ball; `bspAddVector` (`0x35530`) always passes
`Check = 1`, so that call site's predicate is genuinely `AddThing`'s box. Minor, latent, same item.)

`a762617` narrowed the stopgap — the scan now takes the NEAREST pool point rather than the first
inside the threshold, which is what the editor's descent would have returned for Island N=5's two
coplanar oblique-face bases — and that took Island to N=5, UNATCO to N=28 and OceanLab to N=33. It
does not make the branch faithful. The faithful fix is the one this item already names: run the
descent, and append on a miss. The earlier attempt at that over-created points on `DX.dx`
(`native-materialize-findings.md`, garage-pool-snap rounds 2-3) with a descent that was then missing
the surf-`pBase` and `i_plane`-chain candidates — both since ported — so it is worth retrying, and
appending on a miss is now known to be correct rather than a bug to avoid.
