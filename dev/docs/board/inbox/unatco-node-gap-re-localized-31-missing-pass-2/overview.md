+++
priority = "p2"
kind = "debug"
summary = "UNATCO 6364-vs-6314 gap re-localized: the repartition now matches exactly; 31 nodes are missing in pass 2 on one brush (Brush507), and the +81 Pass-D zone-split nodes are a golden-baseline mismatch, not a bug"
+++

# UNATCO node gap re-localized after the `RemoveColinears` fix

Continues `findbestsplit-divergence-forensic-dive-17-real` and
`bspmergecoplanars-8-case-merge-gap-live-traced`. Re-measured the full 734-brush UNATCO build on
master (`7f4a773`) and the picture changed completely: the divergence the earlier items chased
(`bspMergeCoplanars` fragment shape → `FindBestSplit` stride sensitivity) is **gone**.

## The repartition input and the repartition tree now match the editor exactly

Re-ran the poly-for-poly soup comparison (native `UEDCLI_BSPCSG_SOUP_ORDER` vs the cached live
capture `harness/editor-tree-oracle/logs/repart-soup-full-unatco.log`):

- 2514 vs 2514 polys, 1633 vs 1633 distinct `iLink`s, 0 only-native, 0 only-editor.
- **Every one of the 2514 array positions agrees on `(iLink, NumVertices)`** — not just the multiset,
  the ORDER. The earlier "8 surfaces grouped differently" and "~5 local reorder perturbations" are
  both fully closed.
- Only 2 of 2514 positions differ at all, and only in `Normal`/`Base` at the ~1e-5 level — the
  already-filed separate ~100-ULP rotated-brush normal drift, unrelated.

A tree-structural synchronized walk (plane compare, tolerance 0.05 to look past that same normal
drift) now matches **6314 of the editor's 6314 nodes**, max depth 68, with only 3 divergence points
left — all of the form "native's coplanar chain has extra trailing entries".

## Where the remaining nodes actually are

Per-surf node counts, native final vs golden: exactly **3 surfs differ, total +50** — surfs 550, 552,
553, all faces of one actor (native brush index 106 = `Brush507`, a `CSG_Subtract` box; the golden's
own `iActor` for it is 418). Every one of the other 3613 surfs matches the golden exactly.

Instrumented native's node count per build stage (`UEDCLI_BSPCSG_STAGE_COUNTS`, added to
`bspcsg.rs`):

| stage | native nodes |
|---|---:|
| post-repartition | 2953 |
| post-pass-2 (semisolid/detail brush CSG) | 6283 |
| post-finalize (zones Pass D fragment split) | 6364 |

Comparing the **post-pass-2** state per surf against the golden isolates two separate things:

- **Real gap, −31 nodes**: surfs 550/551/552/553 (`Brush507` polys 0/1/2/3) carry 2/5/9/3 nodes in
  native where the golden has 5/8/25/12. Every other surf matches. Since the repartition soup and
  order are exact, this divergence is created in **pass 2** — the detail/semisolid brush CSG layer
  fails to fragment this one subtract brush's faces as much as the editor does.
- **Wrong-place zone pass, +81 nodes**: native's zone Pass D (`AssignAllZones`) appends 81 coplanar
  fragment nodes, 78 of them on surfs 552/553, where the editor's appends 31. The golden
  (`/tmp/UEDGolden_unatco_full.dx`) is a bare `MAP REBUILD` capture — spec §1.1/§14: 6314 nodes /
  3616 surfs / 599 vectors and *stale* leaves, confirmed directly from the file (762 leaves carrying
  7204 node `iLeaf` references = 9.45 refs/leaf, the spec's stale-leaf signature, versus native's
  2739 leaves at 1.00).

  The first read of that was wrong and is corrected here: the stale leaves do NOT mean the golden
  skipped the zone pass. `csgRebuild` calls `TestVisibility` unconditionally, mid-pipeline; the
  leaves go stale because the detail-brush loop adds ~3300 nodes AFTER it. Both halves above are the
  same bug — see below.

Net: `6283 − 31 + 81 = 6364` vs the golden's `6314`.

## Resolved by

Both halves turned out to be the same bug — native ran the zone pass at the wrong point in the
pipeline. See `csgrebuild-runs-testvisibility-between-the`.
