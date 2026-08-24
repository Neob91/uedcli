+++
priority = "p1"
kind = "debug"
summary = "Native preview drops large geometry on full retail levels (Wanchai) — CSG solidity divergence far beyond the castle ~11%"
+++

# Native preview drops large geometry on full retail levels

`level preview --native` on **Wanchai Market** (retail DX, 1304 brushes, ~75% scaled) renders only a
partial world: whole walls/ceilings/floors are MISSING (rays pass into void → the flat grey
background), disconnected surface fragments float in mid-air, and coplanar residuals speckle the
surfaces that do build. A 360° sweep from `PlayerStart1` and several teleporters (2026-08-24) shows
most view directions are void or fragmentary — one frame came back at 2.8 KB (near-blank). By
contrast **NYC Bar** (203 brushes) renders a fully-enclosed, correct interior. So fidelity holds on
small/simple maps and collapses on large complex retail geometry.

**Not the scale support.** The transform-unification (`unify-transform-application-logic-into-one-home`)
places/sizes scaled brushes correctly as CSG INPUT — the bar proves it. This is CSG **solidity
accuracy**: the core mis-classifies solid/void and drops surfaces. Separate problem, pre-existing.

## Repro
```
level import dev/games/deusex/Maps/02_NYC_Bar.dx --tree level/nyc-bar   # clean (203 brushes)
# Wanchai trunk: dev/games/trunks/tmp-wanchai-market/ (1304 brushes) — largely holed
level preview --native --tree level/tmp-wanchai-market --out-dir OUT "at:@PlayerStart1;rot:0,0"
```

## Suspected mechanism (confirm in the spike)
The coarse CSG core has documented solidity divergence (~11% on the 95-brush castle;
`architecture.md` "KNOWN GAP — CSG geometry parity"). On a 1304-brush level the per-brush errors
compound. Candidate dominant causes, to quantify + rank:
- **Convex-only `point_in_solid`** (`csg.rs` `point_in_convex` tests "behind every face" = the convex
  hull, not the true solid) — concave / non-convex brushes mis-classify.
- **`bspMergeCoplanars` is a no-op** (`build.rs merge_coplanars`) — coplanar residuals (the speckle)
  + under-merged faces.
- **Cascading face-discard**: a mis-solidified region over-discards the next brush's faces (the CSG
  leaf filter drops fragments behind "solid"), so one bad brush guts its neighbours → holes spread.
- **`build_geometry` vs `build_geometry_bspcsg`**: preview tries the coarse core then falls back —
  determine which one renders Wanchai and whether the other is better/worse.

## Scope / relations
Distinct from `--game` (real engine). Related boarded gaps: `bspcsg-core-apply-scaled-brushes`,
`the-native-over-produces-leaves-3-6-gap` (done), the b/f CSG-differential xfail residuals. This item
is the RETAIL-scale severity + a directed root-cause investigation (findings fold in below).

## Investigation
Spike launched 2026-08-24 (subagent) — quantify dropped-surf count on Wanchai, localise the dominant
cause, recommend a fix direction. Findings append here.
