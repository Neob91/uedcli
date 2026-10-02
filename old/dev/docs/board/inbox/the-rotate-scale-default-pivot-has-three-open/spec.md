# Spec: the `--by` pivot is a member's OWN LOCATION, nearest the bbox center

**Date:** 2026-07-26 · **Status:** BUILT (owner said build; spec gate not run) · **Owner:** Andrzej

Supersedes the pivot behaviour landed in `5d4506e` (bbox centre as a scored candidate).

---

## 0. The problem

> "I basically don't want to rotate around a non-grid-aligned pivot automatically when rotating
> multiple actors. That's the main concern. It'll leave the brushes misaligned." — owner, 2026-07-26

Two goals the old rule could not hold at once: the pivot must be **grid-aligned** (rotating about a
poorly-aligned point walks on-grid geometry onto a coarser grid, and off-grid geometry is the main
cause of BSP holes), and it should be near the **center** (a selection should turn about its middle,
not swing). `rotation.best_grid_pivot` maximised alignment and sacrificed centring, so a multi-actor
selection pivoted about a *vertex* and displaced:

```
before   min -64,-64,-64   max 576,576,128      center 256,256,32
rotated 4 actor(s) about 192,64,64              # a vertex won on 2-adic alignment
after    min -320,-192,-64  max 320,448,128     # the group swung
```

## 1. The rule as built

**The pivot is the `Location` of the set member nearest the selection's bbox center.**

A brush's `Location` is the point that stays fixed when it turns about itself — set `v == PrePivot`
in `world = Location + PostScale·R·MainScale·(v − PrePivot)` and everything after `Location` cancels.

**The load-bearing property is that a `Location` is AUTHORED.** Whatever grid the designer built on,
it is already on it, so grid alignment is *inherited rather than computed*. This is why the rule works
where the alternatives did not: every rule that **derives** a pivot must round it back onto some grid,
and choosing that grid is where it goes wrong (§4).

Precedence:

1. **Brushes first.** If the set has any brush, only brush Locations are candidates.
2. **Otherwise point actors.** Their Locations are candidates, which is what gives a lone decoration
   its exact in-place rotation.
3. **Nearest the bbox center wins** (Euclidean, over the selection's full-transform world AABB).
4. **Ties take the alphabetically first Name** (owner ruling, superseding an earlier "average the
   tied members"), see §2.
5. **No fallback rule, and none is needed.** Every actor has an **effective** Location: an unauthored
   property takes its **class default**, resolved from the schema — *not* assumed to be zero.
   `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)` (verified live), and
   `architecture.md` names assuming zero as the bug the typed compare exists to remove. So an actor
   carrying no `Location` is wherever its class puts it, not missing a pivot, and a non-empty
   selection always has one. `best_grid_pivot(actors, class_default)` takes the lookup as a
   parameter and consults it ONLY for an actor that states no Location, so an ordinary rotate stays
   offline and schema-free. *(Owner ruling, 2026-07-26, choosing this over keeping the zero
   assumption or refusing to guess.)* The old most-grid-aligned-candidate scoring (and the `_v2` 2-adic helper that served only it)
   is **deleted**, not kept as a dead branch — a fallback here would also have broken
   `direction/conventions.md` "No fallbacks, anywhere".

   Stated as an effective-value rule on purpose: *"the emitter always writes a Location line"* is
   true of uedcli's own output but is an emission detail, and the behaviour must not rest on it —
   `level import` reads T3D from UnrealEd, which omits default-valued properties as a matter of
   course. Reasoning from effective values holds for a T3D from any source.

`--pivot X,Y,Z` and `--pivot-actor NAME` override it entirely. There is no `--pivot center` keyword
and none is added: `actor rotate --pivot` takes coordinates only.

### Degenerate selections, which now need no special case

- **A lone point actor** is the only candidate, so the pivot is its Location verbatim — a prop at
  `(1013.5, 227.25, 41)` turns in place and is **not** dragged onto the grid.
- **N actors sharing a Location** give that same Location exactly, with no snap to 1 uu.
- **A lone brush** pivots on its own Location, i.e. in place.

Both of the owner's degenerate requirements fall out of the rule instead of being written into it.

### Locations are used AS AUTHORED — no filtering

**Owner decision, 2026-07-26: use the Location of the closest brush in the set.** There is no test for
whether a Location sits near the actor's own geometry.

The accepted cost: `Location=(0,0,0)` with **world-space** vertices (`docs/usage.md`) has its fixed
point at the world origin, which can sit thousands of uu from the geometry. Real — the shipped
TubePlatform trunk holds five such `revolve` brushes (`StationBore_6cuhtp`, `Train_5o0jm3`,
`EdgeLine_7o5rmv`, …) with `Location=(0,0,0)` and vertices at Y≈1300, so a selection of only those
turns about the origin and swings across the map. `--pivot X,Y,Z` / `--pivot-actor` is the override.
Pinned by `test_a_raw_csg_brush_contributes_its_location_unfiltered`.

## 2. Ties: the alphabetically first actor Name

**Owner ruling, 2026-07-26: no average — take one member's Location. Alphabetical by Name**, offered
as the easier alternative to CSG order and taken as such: it needs no `Level.order` plumbing, so
`best_grid_pivot(actors)` keeps its one-argument signature and both call sites are untouched.
Casefolded first (names resolve case-insensitively everywhere else), raw Name as the final
discriminator.

It also does not depend on the order the set arrived in, so a pipe that reorders names cannot change
the pivot. The cost, worth stating: generated names carry random suffixes (`Cube_73q1az`), so among
tied *generated* brushes the winner is deterministic but arbitrary — it is not "the first one you
drew".

This supersedes an earlier "average the tied members" ruling, which was measured to divide by the
number tied and land off-grid:

| tied | average | effect |
|---|---|---|
| 3 (four-cube set) | `341.333333, 256, 21.333333` | **every brush off-grid** |
| 2, spaced 256 | `128,0,0` | fine — stays on the 128-grid |
| 2, spaced 16 | `8,0,0` | drops one power of two |

`(a+b)/2` of two multiples of `2^k` is only a multiple of `2^(k-1)`, and an N-way average with N not
a power of two lands anywhere at all. Taking an authored Location avoids the question entirely.

### Why an authored Location is the right kind of pivot

For a rotation by a multiple of 90°, if `align(P) >= align(v)` for every contributing coordinate,
then `align(v') >= align(v)`: offsets satisfy `v2(v−P) >= min(v2(v), v2(P))` (ultrametric), a
90° multiple only swaps and negates offset components (preserving each valuation), and re-adding `P`
cannot lower it.

This rule does not *enforce* that condition — it makes it hold in practice, which is the point. A
Location is on whatever grid the designer built on, so it is normally at least as aligned as the
geometry placed relative to it; a **derived** pivot has no such property and must be rounded onto a
grid chosen by the tool, which is where the rejected designs went wrong (§4). A deliberately
off-grid Location still yields an off-grid pivot — `--pivot X,Y,Z` is the override.

Note what governs it: a 90° yaw gives `x' = (px + py) − y`, so the result depends on `v2(px ± py)`,
not on `v2(px)` and `v2(py)` separately. Equal components cancel — pivot `(264,264)` yields
`v2(528)=4` and coarsens nothing — so the failure mode needs the pivot's components to be *unequally*
aligned. Pivoting on an authored Location avoids the whole question.

## 3. Measured behaviour

```
lone brush at 512,512,64          pivot 512,512,64        Location untouched, bbox unmoved
4 cubes, 3-way tie                pivot 256,0,0           an authored Location; all stay 256-aligned
symmetric pair "Bravo"@0/"Alpha"@256   pivot 256,0,0      Alpha's Location — Name, not position
lone prop at 1013.5,227.25,41     pivot 1013.5,227.25,41  exact; never snapped
verts off Location (ctr 1064)     pivot 1000,0,0          the Location, NOT the bbox centre
```

## 4. Rejected: a size-derived snapped center

An earlier draft computed `pivot = snap(center, ROUND_TO_POWER_OF_2(size / 256))`. Rejected because a
size-derived grid is **not tied to the geometry's own alignment**: a 640-uu selection yields grid 2 —
"the pivot must be even" — while 16-grid geometry needs a pivot aligned to 16. Worked case, a 528×512
footprint on the 16-grid:

```
g_size = 2, 2      pivot (264, 256)      # already even; the snap is a no-op
v2(px+py) = v2(520) = 3
  vertex (16,0) -> (520, 8)     vertex (0,16) -> (504, -8)
  every result 8-aligned: the 16-grid structure dropped to the 8-GRID
```

It could be repaired with a floor (`g = max(g_size, 2^k_geom)`), but that is machinery in service of
re-deriving a coordinate the trunk already contains. Rejected in favour of the authored Location.

## 5. Code

- `rotation.actor_own_pivot(actor)` — new. The Location as `Decimal` (normalised: an in-memory Actor
  may hold floats). Never `None`; an actor with no authored Location resolves to the origin.
- `rotation.best_grid_pivot(actors)` — same name and signature, so both callers
  (`dispatch.py` rotate and scale) are untouched. One path, no branches: bbox centre → nearest
  member's Location → Name breaks ties. The old candidate-scoring rule and its `_v2` helper are
  deleted — keeping them as a fallback also violated `direction/conventions.md` "No fallbacks,
  anywhere".
- `docs/usage.md`, both `--pivot` help strings, `dev/docs/direction/conventions.md` and
  `dev/docs/architecture.md` updated.

## 6. Tests

`uedcli/tests/test_rotate_pivot.py`, 11 passing: own-pivot in place; a raw-CSG brush contributing its
Location unfiltered; lone point actor exact and unsnapped; actors sharing a Location; nearest-member
selection; 2-way and 3-way ties taking the alphabetically first Name (the `341.333333` regression).
Dispatch-level cover in `test_scale_verbs.py` uses a brush whose Location is NOT its bbox centre, the
only shape that separates this rule from the superseded one.
Full suite green — 3412 passed, 13 skipped, 1 xfailed.

## 7. Still open

1. **Scope.** The rule is live on **both** `actor rotate --by` and `brush scale --by`, since they
   share `best_grid_pivot` — never explicitly confirmed by the owner (splitting them would be the
   larger change, so sharing was kept).
2. ~~**Fallback choice.**~~ Closed 2026-07-26: there is no fallback. Every actor has a Location.
3. **Residual displacement.** The pivot is a member's Location, not the center, so a group still
   swings by that member's offset from the center — zero for a single actor, bounded by roughly half
   the inter-member spacing otherwise. Accepted implicitly; not measured against a target.
4. **Long-lever residue** (pre-existing, orthogonal): beyond ~11,438 uu from the pivot the GMath
   rotator dust exceeds `CLEAN_EPS` and a rotated Location lands genuinely off-grid.

## 8. Not in scope

- **Placement** keeps the bbox-min corner (`direction/conventions.md`).
- Non-90° rotations are off-grid by nature; nothing should snap the result.
- Build-review finding **#1** (`actor bbox` vs `--within-bbox`) is FIXED in the same tree:
  `writes.aabb_within` compares within `emit.CLEAN_EPS`. See
  [`dev/docs/rationale/reported-coordinates.md`](../../../rationale/reported-coordinates.md).
