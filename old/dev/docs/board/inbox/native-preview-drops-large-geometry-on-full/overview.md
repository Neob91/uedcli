+++
priority = "p1"
kind = "debug"
summary = "Native preview drops large geometry on full retail levels (Wanchai) — CSG solidity divergence far beyond the castle ~11%"
+++

# Native preview drops large geometry on full retail levels

`level photo --native` on **Wanchai Market** (retail DX, 1304 brushes, ~75% scaled) renders only a
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
level photo --native --tree level/tmp-wanchai-market --out-dir OUT "at:@PlayerStart1;rot:0,0"
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

## Root cause (spike 2026-08-24, verified): preview uses the WRONG CSG core
`preview_native.build_scene` calls `uedcli_native.build_geometry` (the `build.rs` coarse core:
convex-hull point-in-solid oracle + batch single-partition). The faithful editor-parity incremental
core `build_geometry_bspcsg` (`bspcsg.rs`, grows the BSP node-by-node like UnrealEd) is **never used
by `level photo`** — even though `actor diagram --faces textured` already uses it via
`solve_world_surfaces`.

Native-vs-editor surf ratio (editor `.dx` UModel = ground truth):

| map | brushes | scaled% | `build_geometry` (preview) | `build_geometry_bspcsg` | editor |
|---|--:|--:|--:|--:|--:|
| NYC Bar (control) | 203 | 2.5% | 938 / **0.98** | — | 953 |
| WanChai Garage | 198 | 60% | 635 / **0.63** | 931 / **0.93** | 1004 |
| WanChai Market | 1304 | 75% | 1615 / **0.31** (366s) | 5285 / **1.01** (31s) | 5224 |

The faithful core reproduces the editor essentially exactly AND is ~12× faster. Ranked causes:
1. **Wrong core = ≈all of the drop** (swap alone: Market 0.31→1.01, Garage 0.63→0.93 on identical input).
2. **Scaled brushes are the trigger** that exposes `build.rs`'s non-watertight batch oracle (Garage
   198 brushes/60% scaled → 0.63 vs NYC 203/2.5% → 0.98). The scale-baked geometry is fine — bspcsg
   builds it correctly; `build.rs` annihilates fragments on dense scaled geometry.
3. **Non-convex brushes (minor)**: 34/1304, top face-droppers under the convex-hull oracle; moot on bspcsg.
Ruled out: coplanar merge (`same_surface` only reassembles a face's own fragments) and the NotSolid sheets.

## Fix direction
**Quick win, drop-in:** point `build_scene` at `build_geometry_bspcsg` (same `Built`/`serialize_model`/
`_node_polys` join path — it's already the `except BuildError` fallback and the `--faces textured`
primary). Recovers the geometry and is far faster; no `csg.rs`/`build.rs` change. `build.rs`'s coarse
core is superseded — not worth deep-fixing. **Verify with a visual PNG spot-check** (the spike confirmed
surf/node counts + join tags but did not render).

Spike scripts under the job tmp (`cores.py <dx>`, `control.py`, `convexity.py`, `scaled.py`, `RESULTS.md`).
