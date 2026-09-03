+++
priority = "p1"
kind = "implement"
summary = "`Model.Lights` has two regions: the per-LEAF permeating light lists (5405 of UNATCO's 16263 entries) and the per-SURFACE shadow runs. Native emits only the surface runs; every leaf's `iPermeating` now correctly stubs to -1 (was a bogus 0, fixed 2026-08-29). The leaf region is produced by csgRebuild -> TestVisibility -> Portalize, i.e. it is a zones.rs port, not a lighting one. The full algorithm is decoded below."
spikes = ["dev/docs/spikes/2026-08-29-permeating-lights/"]
+++

## Status 2026-09-03: WIRED IN (`8bdb078`) — owner ruling reverses `8d7fe30`

Owner explicitly reversed the 2026-08-31 hold: the mechanism is fully disasm-confirmed and
reproduced, so `write_permeating_region` is now called from `light::bake`. Verified on an
isolated cube-subtract + one-light case (structurally exact, unlike UNATCO, so it isolates this
fix cleanly): the previously-divergent leaf record now matches the editor exactly, closing that
case to full byte parity (geometry 6/6, content byte-identical, lighting 100%). UNATCO's own
95.4%/4.6% split (below) is unchanged by this wiring — it only decides whether to SHIP that known
accuracy, not whether it's more accurate. cargo 112/112 (scoped run, not full pytest per standing
instruction). The remaining ~4.6%-mismatch leaves (over-inclusion, never missing lights) are still
open — not this item's remaining scope, see "Two things to verify" below for the one still-open
sub-mechanism (`SP_Coplanar` branch behavior).

## Status 2026-08-31: `SplitWithPlaneFast` decoded, content mostly fixed — still NOT wired into `light::bake`

Both "verify before porting" items below addressed — see updated bullets. `clip_beam`'s naive
Sutherland-Hodgman clip replaced with `split_with_plane_fast`, a disassembly-faithful port of the
real function (`uedcli-native/src/permeating_lights.rs`). Measured on UNATCO (`03_NYC_UNATCOHQ.dx`):
per-leaf exact-run matches went 675/762 → 727/762 (88.6% → 95.4%), mismatches 87 → 35, all remaining
mismatches one-directional (native has extra lights, never missing). Full numbers and the
disassembly evidence: `dev/docs/native-materialize-findings.md` "Round 8".

**`write_permeating_region` was NOT wired into `light::bake` this round**, though the dispatched
agent did wire it and the coordinating session reverted that part before committing. The owner's
original call to leave it unwired (commit `8d7fe30`, comment: "shipping wrong-but-plausible light
lists is worse than the current honest `iPermeating = -1` gap") still holds — 95.4% is real
progress but is still wrong-but-plausible, not wrong-but-absent, and this round's own measurement
shows wiring it in moves ZERO levels' byte-level parity (the comparison cascades on the first wrong
leaf regardless). Flipping that call needs the owner's explicit yes, asked for separately. No level
reaches FULL PARITY either way.

## Status 2026-08-29: first port attempt, NOT wired in — wrong per-leaf content

`uedcli-native/src/permeating_lights.rs` implements the flood below (portal collection reused from
`zones::collect_leaf_portals`), but is not called from `light::bake`. On UNATCO: leaf-reachability
SET matches the editor exactly (748/762, same leaves both sides) — the portal graph and per-light
radius reachability are sound — but per-leaf light CONTENT is wrong (only 4/762 leaves have an
exact-match run). Two suspects, neither isolated: the flood-direction orientation (derived from
`zones::Portal`'s a/b convention, not independently verified for this use), and `clip_beam` (a
from-scratch Sutherland-Hodgman clip standing in for the undecoded `FPoly::SplitWithPlaneFast`).
Full writeup: `dev/docs/spikes/2026-08-29-permeating-lights/README.md`. Separately fixed:
`zones.rs` no longer stubs every leaf's `iPermeating` to a bogus `0` (now the correct `-1`), which
was actively wrong regardless of this port's fate.

# Port the per-leaf permeating light lists (`Model.Lights` region 1)

`Model.Lights` (`UModel+0xe4`) is two arrays end to end. Measured on the editor's own build of the
UNATCO trunk (`harness/lights_regions.py` in
`spikes/2026-08-27-native-light-apply-parity/`):

| region | span | indexed by | entries |
|---|---|---|---:|
| 1 — per-LEAF permeating lights | `[0, 5405)` | `FLeaf.iPermeating` (761 of 776 leaves) | 4644 + 761 NULLs |
| 2 — per-SURFACE shadow runs | `[5405, 16263)` | `FLightMapIndex.iLightActors` | 10858 |

Native emits region 2 only, and `zones.rs` stubs **every** leaf's `iPermeating` to `0` — which points
each leaf at a *surface* shadow run. The game `AddLight`s a leaf's permeating list onto any dynamic
actor standing in it, so that stub is not merely missing data, it is wrong data.

**It is not a lighting-bake job.** `shadowIlluminateBsp` empties only `Model->LightMap` (`0x100a5eb3`)
and `Model->LightBits` (`0x100a5ee0`) and never touches `Model->Lights` or `Model->Leaves` for the
level model; region 1 survives into the `LIGHT APPLY` output because the bake APPENDS after it.
Region 1's producer is `csgRebuild` (`0x1004a650`) → `TestVisibility` (`0x100aa940`, vtable `+0x264`)
→ `FEditorVisibility::Portalize` (`0x100aa370`), i.e. the zoning/portalization build. So this belongs
with `zones.rs`.

One engine quirk that follows: because the bake never empties `Model->Lights`, running `LIGHT APPLY`
twice without an intervening `csgRebuild` appends a THIRD region and orphans the previous region 2.
Any golden must come from a full rebuild.

## The algorithm (disassembled 2026-08-27, `Editor.dll`, image base `0x10000000`)

```
for pass in 0..1:                                      # 0x100aa5af
  for iActor in 0 .. Level->Actors.Num-1:              # ascending ARRAY order
     A = Actors[iActor]; if !A: continue
     if A->LightType (byte A+0x19c) == 0: continue     # 0x100aa5d6
     if (A+0x28 & 5) == 0: continue                    # 0x100aa5df -- bStatic|bNoDelete
     if pass == 1: ActorVisibility(A, iLeaf=-1, ClipPoly=NULL)     # 0x100aa611
for iLeaf in 0 .. Model->Leaves.Num-1:                 # 0x100aa6af..0x100aa73c
   if LightsPerLeaf[iLeaf] == NULL: continue           # leaf keeps iPermeating = -1
   Leaves[iLeaf].iPermeating = Model->Lights.Num
   for n = LightsPerLeaf[iLeaf]; n; n = n->Next: AddItem(&Model->Lights, n->Actor)
   AddItem(&Model->Lights, NULL)                       # the run terminator
```

`ActorVisibility` (`0x100a6d00`) is a recursive **portal-beam flood**, not a radius test and not a
`LineCheck` — its body contains no call to either line-check function:

* **Seed** (`iLeaf == -1`): a plain BSP descent from node 0 on `Plane.PlaneDot(A->Location) > 0`
  (`0x100a6d7d`/`0x100a6d9a`), taking `iChild[Side]` then `iLeaf[Side]`; a solid terminal
  (`iLeaf == -1`) returns 0. The seed leaf **skips the radius gate entirely** (`0x100a6dd2` jumps
  past it).
* **Re-entry gate** (recursive entries only, `0x100a6dfc`–`0x100a6ecb`): walk the leaf's portal list,
  and for each portal's `GetPolyForLeaf(iLeaf)` test every vertex — qualify on the FIRST vertex with
  `WorldLightRadius()^2 > |vertex - Location|^2` (strict). No qualifying vertex on any portal → the
  leaf is not marked. A portal-less leaf returns immediately.
* **Mark** (`0x100a6edd`): dedupe on actor-pointer identity, then **PREPEND** a
  `{AActor*, Next}` cell from `FMemStack`. Traversal continues even on a duplicate.
* **Flood** (`0x100a6f4b`–`0x100a71f3`): per portal, `d = (Location - Poly.Base) · Poly.Normal`;
  require `d < 0` (light on this leaf's side) and `d > -WorldLightRadius()`; then, if a `ClipPoly`
  was passed, clip the portal polygon against the beam planes `FPlane(Location, CP.V[j],
  CP.V[jPrev])` with `FPoly::SplitWithPlaneFast`, stopping the clip once the polygon reaches 14
  vertices (`0x100a7083`); recurse into `GetOtherLeaf(iLeaf)` with the clipped polygon.
  `GetPolyForLeaf` reverses the portal polygon when `iLeaf == portal->iFrontLeaf`, so the oriented
  normal always points out of the queried leaf.

The adjacency it walks is the `FEditorVisibility` portal graph — **every** empty-leaf-to-empty-leaf
face, not only `PF_Portal` surfaces — and it never consults `iZonePortalSurf` or zone
`Connectivity`/`Visibility`, so zone boundaries are transparent to it. There is no depth cap and no
visited-pruning; geometry alone terminates it. Every comparison is against exact `0.0f` / `±R` with
no epsilon.

**Within-run order is therefore pinnable exactly**: lights are the outer loop in ascending
`Level->Actors` index order, one light's whole flood completes before the next starts, the dedupe
allows at most one entry per (leaf, light), and the mark prepends — so a leaf's run is the lights that
reached it in **DESCENDING `Level->Actors` index order**. The measured leaf-0 run
`[44,43,42,39,19,13,12]` is exactly that. (This corrects
`2026-07-15-native-materialize/sections/20-lighting-bake.md` §21 (A), which called it an unsorted
"gather-discovery order" — a doc correction needing the owner's yes.)

`iPermeating = -1` ⇔ no participating light marked that leaf (hence 761 terminators for 776 leaves).

## Also decoded while here (same pass, same file)

* `iVolumetric` comes from a SECOND flood (`0x100aa74e`–`0x100aa869`, flood `0x100a9290`) appending
  into the same `Model.Lights`, so a fog map has a THIRD region. Its filter is not a
  "volumetric light" bit: it requires the light's own `Region.Zone` to have `bFogZone`
  (`zone+0x27c & 2`), plus non-zero `VolumeRadius` (`A+0x1a6`) and `VolumeBrightness` (`A+0x1a5`),
  plus the same `LightType`/`bStatic|bNoDelete` gate. `WorldVolumetricRadius` (`Engine 0x10116bb0`)
  is `25*(VolumeRadius+1)`. The flood itself is a plain sphere-vs-BSP descent — no portals, no
  shadowing, unconditional prepend. UNATCO has `iVolumetric = -1` on every leaf simply because no
  light passes that filter.
* `iVisibilityMask` is set once to all-ones in the pass-A leaf template (`0x100a77f2`/`0x100a77f9`)
  and never written again.
* `FLeaf`'s serialized order equals its memory order (element serializer `Engine 0x1016f930`):
  `iZone` (ci), `iPermeating` (ci), `iVolumetric` (ci), `iVisibilityMask` (8 raw bytes) — 0x14 bytes.

## Two things to verify BEFORE porting

1. **Which filter result lands in `FPortal.iFrontLeaf` (`+0x1d8`) vs `iBackLeaf` (`+0x1dc`)** in
   `MakePortals` (`0x100a9750`). Get it backwards and the `d < 0` gate inverts, the flood runs the
   wrong way, and every leaf set is garbage. Only `AddPortal`'s arg→slot mapping (`0x100a72a0` →
   ctor `0x100a7344`) was confirmed. — **2026-08-31: trusted, not independently gdb-verified.** No
   fresh `MakePortals` capture was done. Resolved instead by measurement: rebuilding the existing
   `a`=front/`b`=back convention against `zones.rs`'s already-fixed DFS order (`a999b30`) reproduces
   88.6% of UNATCO's leaves exactly, including the leaf-0 reference run — a backward orientation
   would invert the flood globally and collapse it to near-nothing, not produce a mostly-correct
   result with a narrow residual. Weaker evidence than a live capture; still open if stronger proof
   is wanted later.
2. **`FPoly::SplitWithPlaneFast`** (an `Engine` import at `[0x100cee30]`) is undecoded. Its coplanar
   handling and epsilons shape the beam clip directly, so a port must mirror it exactly. —
   **2026-08-31: RESOLVED by static disassembly.** Found in `Engine.dll` (export
   `?SplitWithPlaneFast@FPoly@@QBEHVFPlane@@PAV1@1@Z`, RVA `0x151f90`); it classifies each vertex by
   the SIGN of its plane distance (ties go front) but only treats the split as decisive once some
   vertex passes `+0.25`/`-0.25` (`THRESH_SPLIT_POLY_WITH_PLANE`, `.rdata` constants at RVA
   `0x206780`/`0x20b580`, extracted directly from the binary) on BOTH sides — short of that it
   returns the polygon WHOLE or REJECTS it wholesale, never a naive per-edge sliver. Ported as
   `split_with_plane_fast` in `permeating_lights.rs`. One branch (`SP_Coplanar`) has no confirmed
   caller behavior — defaulted to "kept whole", flagged in the code and in
   `native-materialize-findings.md` "Round 8" as the one remaining open item.
