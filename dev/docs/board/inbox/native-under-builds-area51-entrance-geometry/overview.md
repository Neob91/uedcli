+++
priority = "p1"
kind = "finding"
summary = "native under-builds Area51 Entrance geometry far below editor golden"
+++

# native under-builds Area51 Entrance geometry far below editor golden

Found while confirming the NEAR merge-tolerance fix across 10 seeded random OG retail levels
(seed 20260828). Area51 Entrance is the lone level where native is FAR below the editor golden
— the over-fusion signature — unlike the other 9 levels where native is at or above editor.

## Measured (bare `MAP REBUILD` golden = editor's own build of the same trunk vs native)

| | nodes | surfs | points |
|---|---|---|---|
| editor golden | 12630 | 6058 | 17619 |
| native (master incl. fix) | 9252 | 5547 | 13332 |
| delta | −3378 | −511 | −4287 |

−26.7% nodes / −8.4% surfs / −24.3% points. 1343 CSG brushes.

## Why the fix is not the cause

The merge-tolerance change's measured net effect is tiny by comparison: Wanchai −2 soup polys /
−20 nodes; UNATCO control unchanged (6314/3616). Area51's −3378 is ~150x larger and is an
independent native-only under-build on this specific map. No pre-fix counterfactual was run, so
attribution is unproven — but the magnitude rules out the 0.015-NEAR tolerance as the cause.

## Direction for the spike

Plausible (unproven) confound: Area51 is the densest **scaled-brush** map of the 10-level set
(359/1343 = 27% of CSG brushes scaled, vs UNATCO 12%). Likely the native scaled-brush path
drops or misbuilds geometry here. Next step: run a pre-fix native counterfactual on Area51 to
attribute the −3378 exactly (needs a Rust checkout at the pre-merge state; no goldens re-run).

## Investigation result 2026-08-29 (owner ruling current-tree rule, re-measured on master)

Deliverable 1 — counterfactual (conclusive): pre-fix `dad4563` and post-fix `5b0a022` both build
9252/5547/13332. The 0.015-NEAR merge-tolerance change contributes 0 of the −3378.

Deliverable 2 — attribution: `a51_per_brush_attr.py`. Golden 6058 surfs → 1315 named brushes
(0 unresolved); native 5547 → 1146. 285 brushes lose (+1288 surfs), 461 gain (−777), 579 equal
(+511 net = −511 native). Scaled over-representation in losses: 108/285 (38%) vs 27% base.
Cumulative gap (golden−native per-brush, final counts) opens at brush 0 (Brush529 +4) and jams
across indices 0–48 (+340), especially the 46-poly subtract lofts (28→0: Brush3256/3254/3246/
3244, etc.); indices 60–86 over-produce (Brush78 0→19). So the under-build concentrates in the
first 49 CSG brushes — the entrance-room structural build both golden and native do identically
ordered.

Deliverable 3 — mechanism:
- Order is NOT it: `a51_order.py` — golden surf-pool order == trunk CSG order for the first 60
  brushes (Brush1178 #16=#16, Brush323 #48=#48).
- Native over-retains early subtract faces, it does not drop them: `a51_fixture_iso.py` —
  [Brush3257] alone → 26 surfs (all polys), [529+3257] → 26, [529+3257+3256] → 18/36; golden
  final per-brush is 10/28. Native's own later carves strip the fixture faces down to 0 by the
  end of the world; the editor's tree strips them only to 10.
- The dome: `a51_isolate.py` [big box + Brush323] → 43 surfs (golden 42), so dome geometry and
  filter are sound in isolation; `a51_ablate.py` removing Brush1178 restores only 13/42 and
  removing Brush27 restores 0; `a51_faceprobe.py` — the 42 golden dome faces are void (zone 1)
  at every native prefix and in the full tree; `a51_goldenprobe.py` — the golden tree keeps a
  real zone boundary at exactly those faces (zone 0 behind, zone 1 in front). Native fuses the
  two sides into one zone: the walls never form.
- Scaled confound ruled out as the mechanism: the only large loss where removal helps is
  Brush1178 (a MainScale=(1,1,-1) mirrored subtract), and its mirror bake is geometrically
  correct — `a51_no1178mirror.py` R=I returns nothing extra (13 faces, same as removal), while
  `a51_geom.py`/golden show the editor's carve IS at the mirrored location. Native's scale path
  is not the under-build source.

Deliverable 4 — synthetic repro: partial. `a51_fixture_iso.py` builds the first three brushes
in the exact trunk order and shows native's per-brush retention diverging from golden already at
brush 1 (26 vs 10); a fully faithful repro needs the editor rule below.

Residual (open): WHY the editor strips the early subtract lofts' faces to 10 while native keeps
26 and then over-carves to 0 — the per-brush retention rule at indices 0–48. Needs a live
differential trace, not a guess (there is no angle to atomize it further from the retail golden,
which has no intermediate states beyond the final tree).

## Live differential editor trace 2026-08-29 (root cause located)

Drove the real editor (`dx-lum-uned-dbg`) through incremental prefixes: `MAP NEW` + `EDIT PASTE`
first N world-CSG brushes + `MAP REBUILD`, parsing world surf count per brush, diffed against
native. Divergence brush is **index 5 — Brush3252** (6th world-CSG brush, a 26-poly CSG_Subtract
loft). Through N=5 editor and native are IDENTICAL for every brush; at N=6 native over-carves:

| brush | editor (N=6→48) | native (N=6→48) |
|---|---|---|
| Brush3257 (#1) | 10 (holds) | 10→5→0 |
| Brush3256 (#2) | 28 (holds) | 36→12→0 |
| Brush3252 (#5) | 18 | 0 |

Root cause (measured, code path localizable): editor and native share the CSG core
(`filter_world_through_brush` → `wtb_filter_ed_poly`). When a new subtract brush arrives, each
existing world face whose plane straddles its bound sphere is split and fragments strictly inside
the new subtract volume are discarded (`g_discarded > 0`); if nothing is interior the carve rolls
back and the face survives. The EDITOR plateaus: once faces are carved to their coplanar-fused
boundary, every later subtract finds them outside/on-boundary, the carve rolls back, and the count
never drops below golden. NATIVE misclassifies 5–10 of those same surviving faces as interior at
N=6/7 and carves them away, collapsing Brush3257/3256/3252 to 0 and the entrance room with them.

Not yet atomized: the exact misclassified face at the N=5→N=6 transition (coplanar-sign vs a
NEAR-type epsilon in `split_with_plane`/`wtb_filter_ed_poly`; the rollback gate `g_discarded == 0`
is the exact place the two must differ). Needed: a node-level diff of named N=5→N=6.

Separate editor-self residual (not native's fault): Brush3254 (#4) holds 36 through N=48 while the
full-1343 golden reads 28 — an editor incremental-vs-final inconsistency, unresolved, distinct from
the −511 gap (which is dominated by the native over-carve above).

Minimal repro: first 7 world-CSG brushes in CSG order
`Brush529, Brush3257, Brush3256, Brush3255, Brush3254, Brush3252, Brush3245`; N=7 editor keeps
{10,28,18} for 3257/3256/3252, native gives {0,0,0}. Native mirror probe `a51_native_prefix.py`,
editor probe `a51_editor_prefix.py` (`_scratch/a51-editor-trace/`).

Evidence scripts (to move to `dev/docs/spikes/<slug>/` before closing): `a51_cumgap.py`,
`a51_fixture_iso.py`, `a51_per_brush_attr.py`, `a51_norepart_bisect.py`, `a51_isolate.py`,
`a51_overlap.py`, `a51_ablate.py`, `a51_geom.py`, `a51_faceprobe.py`, `a51_goldenprobe.py`,
`a51_dome_walls.py`, `a51_order.py`, `a51_golden_geom.py`, `a51_no1178mirror.py`,
`a51_progress.py`, `a51_grid.py`, `a51_first20.py`, `a51_firstbrush.py`.
