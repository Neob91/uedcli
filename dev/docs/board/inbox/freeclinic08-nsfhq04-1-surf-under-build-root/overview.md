+++
priority = "p2"
kind = "debug"
summary = "freeclinic08/nsfhq04 +1-surf under-build root-caused to CSG classify_fragment approximation, distinct from UNATCO"
+++

# freeclinic08/nsfhq04 +1-surf under-build root-caused to CSG classify_fragment approximation, distinct from UNATCO

Follow-up to `breadth-geometry-re-check-across-11-og-levels-2`: dug into the two closest-to-exact
non-exact levels (freeclinic08 nodes -20/surfs +1/leaves -23, nsfhq04 nodes -78/surfs +1/leaves
-26). No fix shipped — root mechanism identified, but fixing it safely needs more than this
session's budget; see "Why not fixed" below.

## The +1 surf, precisely

Per-brush surf-count attribution (`_scratch/fc08_surf_diff.py`, matching native `BspSurf.i_actor`
— a 0-based world-CSG brush index — against golden's `i_actor` resolved via
`epkg.name_of_ref`) finds **exactly one** brush differs in both levels:

- freeclinic08: `Brush143` (world-csg idx 144) — native attributes 6 surfs to it, editor 5.
- nsfhq04: `Brush531` (world-csg idx 733) — same 6-vs-5 pattern.

Both are `CsgOper=CSG_Add`, `PolyFlags=32` (`PF_Semisolid`) brushes. For Brush143 (a 6-poly
beveled-corner wedge, ~72×72×2uu), native keeps its authored poly index 1 (the underside, base
point world `(1088, -2432, -274)`, normal `(0,0,-1)`) as a surf; the editor's built model has no
surf for that poly at all — every other poly (0, 2, 3, 4, 5) matches exactly (same base
point/normal on both sides).

## Root mechanism

`uedcli-native/src/csg.rs`'s `classify_fragment` classifies each face fragment by **nudging its
centroid ±0.5uu (`EPS_NUDGE`) along the winding normal and sampling point-in-solid** against the
accumulated world brushes — the file's own header comment states this REPLAYS CSG as a
point-in-solid test, explicitly *not* a port of the editor's real `bspBrushCSG` classify-BSP
filter (a different algorithm, kept only for splitting).

`LeafFunc::Add`'s classification-to-keep/discard mapping (`leaf_apply`, `csg.rs:214-231`): a
fragment classified `Outside` is always kept; one classified `CospatialFacingIn` (solid on both
nudge samples — buried) is kept **unless** `PF_SEMISOLID` is set, in which case it is discarded.
Brush143's poly1 is semisolid, so the only way native's `Add` keeps it is if `classify_fragment`
returned `Outside` rather than `CospatialFacingIn` — i.e. native's nudge sample landed in void
where the editor's real classify-BSP finds the face buried (or clips it away upstream). This is a
genuine face-survival divergence, not a downstream tree-shape artifact.

## The -20/-78 node and -23/-26 leaf deficit is diffuse, not localized

Per-brush BSP-node-plane-owner attribution (`_scratch/fc08_node_owner_diff.py`: for each node,
resolve its splitting surf's owning brush via `node.i_surf -> surf.i_actor`, Counter per brush,
diff native vs editor) on freeclinic08: **75 of 305 brushes** (25%) have differing node-plane-
owner counts, summing to 260 in absolute delta against a net of -20 — heavy cancellation, not one
or two brushes driving the total. Top individual deltas (Brush28 -17, Brush62 -17, Brush175 +13,
...) are semisolid-brush-heavy, but freeclinic08 is 164/305 (54%) semisolid brushes overall, so
that's roughly base rate, not enrichment — semisolid-ness alone doesn't isolate the affected set.

This spread is consistent with `classify_fragment`'s nudge-sample approximation disagreeing with
the editor's real classify-BSP on many individual near-boundary faces across the level (not just
Brush143's), each shift rippling through which face becomes a repartition split plane — the same
kind of tree-shape cascade the Wanchai `try_to_merge` NEAR-threshold fix (5b0a022) demonstrated
(one merge-threshold miss on Brush754 alone moved Wanchai's node count by 20).

## Distinct from UNATCO's paused residual — answers the task's open question

UNATCO's own mismatch (`unatco-verts-points-residual-after-the-zone`, paused) is **+7 nodes with
ZERO surf delta and ZERO leaf delta** — the same SET of surviving faces, only a different tree
SHAPE (a pure repartition/merge-shape issue). freeclinic08/nsfhq04 have a **nonzero surf delta**
(a literally different set of surviving faces, from `classify_fragment`) plus a leaf delta. These
are two distinct mechanisms sharing only the general "native's BSP build isn't a byte-exact port
of the editor's" nature — freeclinic08/nsfhq04's under-build is NOT the same bug as UNATCO's
over-build, and is not blocked on that investigation resolving.

## Why not fixed this session

`classify_fragment`'s nudge-based point-in-solid replay is shared by every level's CSG build.
Tuning it blindly (e.g. `EPS_NUDGE`) risks exactly the class of regression the `blanket_merge`
experiment already produced elsewhere (fixed one thing, regressed UNATCO 6321→5689 nodes,
findings ledger). A safe fix needs either instrumented live evidence of what the editor's real
classify-BSP does at this exact boundary (comparable live-tracing effort to the Area51/UNATCO
investigations) or porting the editor's actual classify-BSP filter instead of the point-in-solid
approximation — both larger than this session's budget. Stopping here per the task's explicit
"don't grind if architecturally stuck" instruction, since the affected code and blast radius look
comparable in size to the still-open UNATCO item, even though the specific mechanism differs.

## Harness

Scripts written this session (not yet promoted out of `_scratch/`, which is gitignored — rerun
against a clean tree before relying on them long-term):
`_scratch/fc08_surf_diff.py`, `_scratch/fc08_brush143.py`, `_scratch/fc08_poly1_verts.py`,
`_scratch/fc08_node_owner_diff.py`. Baseline re-confirmed via
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/breadth_gate.py` unchanged (3/13
exact) before starting; no source changes were made, so no re-run after.

## No level added

freeclinic08 and nsfhq04 remain not-exact. The breadth gate is unchanged: 3/13 (2/11 unique
levels + the trivial `DX.dx`) still exact, still below the 30% floor.
