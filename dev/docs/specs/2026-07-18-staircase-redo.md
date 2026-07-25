# Spec: `brush build staircase` redo (box-per-step, watertight)

**Status:** ephemeral design scratch. The durable record of what was built lands in
`architecture.md` (builder module) + `docs/usage.md`; the load-bearing *choice* + rejected
alternatives go in `decisions.md` (dated entry linked below).

**Board item:** `to-build.md` Geometry #8. **Decision:** `decisions.md` 2026-07-18 20:09 UTC.

---

## Problem

The current `builders.staircase` emits **ONE non-convex brush** that faithfully replicates
UnrealEd's `LinearStairBuilder` face-for-face (a `Base` slab + `back` wall + per-step `Step`/`Rise`
treads/risers + tiled `Side` strips). Two defects make it unusable in the trunk:

1. **Fails `level doctor`.** The stepped profile is a valid closed solid *in reality* (UED builds
   it), but it is riddled with **T-junctions**: a tread edge, a riser edge, and a side-strip edge
   meet at a step corner where an edge is used by only one face. `doctor.check_watertight` keys
   edges by welded coordinate and demands every edge be shared by exactly two oppositely-wound
   faces, so it reports **60+ `watertight` "open edge" errors** on a real staircase. The static
   validator is T-junction-naive by design (it is high-recall on single-brush hole causes), so a
   T-junctioned-but-real solid trips it.
2. **Sits below the floor.** Local Z spans `[-rise, (steps-1)*rise]` (the `Base` slab is one
   `rise` *below* the first tread, UED's convention), so `--at` places a corner that is `rise`
   below the requested world Z — the geometry hangs under the floor.
3. **One brush, not one-per-step** — inconsistent with `spiral` (one slab per step) and harder to
   edit/retexture per step.

## Decision (what we build)

Emit the staircase as a **`list[Brush]` — ONE axis-aligned convex box per step**, like
`spiral_staircase` emits one slab per step. Each box is a clean convex solid, so the whole set
passes `level doctor` with **zero** `watertight`/`convex`/`degenerate`/`planar`/`fallthrough`/`csg_order`
findings. The CSG union of the boxes has the **same stepped profile** as UED's `LinearStairBuilder`,
**re-anchored to sit at/above `z=0`** (see Anchoring) — we change the brush *decomposition* and the
Z-placement, not the stair shape.

### Dispatch plumbing (load-bearing — flagged by both reviewers)

`dispatch._build_brushes` currently **wraps** the single-brush staircase return: `return
[builders.staircase(...)]`. When `staircase` returns a `list[Brush]`, that wrap must be **removed**
so it returns the list unwrapped (mirroring the `spiral` line right below it). Left as-is,
`_build_brushes` returns `[[Brush, …]]`, the `len == 1` branch in the build handler unwraps to the
inner *list*, and `make_brush_actor` raises `AttributeError` on `list.polys` — a raw traceback to the
user. A regression asserts `brush build staircase --steps N` emits **N** actors named
`Staircase0…Staircase{N-1}`.

### Geometry (local vertex space, ascends +X)

For `staircase(steps, depth, rise, breadth)`, step `k` (`k = 0 … steps-1`) is the box:

- **X**: `[k*depth, (k+1)*depth]` — each step owns its own depth slot (boxes are **disjoint in X**).
- **Y**: `[0, breadth]`.
- **Z**: `[0, (k+1)*rise]` — a **solid column from the floor up to that step's tread top**.

So the tread (walkable top) of step `k` is at `z = (k+1)*rise`; step 0's tread is one `rise` above
the floor (you climb one riser to reach it), the top tread is at `z = steps*rise`. The whole set
occupies local `X ∈ [0, steps*depth]`, `Y ∈ [0, breadth]`, `Z ∈ [0, steps*rise]` — **entirely at or
above `Z = 0`**.

**Filled columns, not floating treads:** box `k` runs the *full height* from the floor (`z=0`) to
its tread, so the underside is a solid stepped wedge (a masonry staircase), matching the volume of
UED's `LinearStairBuilder`. Adjacent boxes are disjoint in X and touch only on the shared plane
`x=(k+1)*depth`; they are independent `CSG_Add` actors (BSP merges the coplanar seam), so no box
overlaps another's interior.

### Anchoring: front-bottom corner (realizes the build-#1 decision)

The local origin `(0,0,0)` is the staircase's **front-bottom corner** (min-X, min-Y, min-Z — the
bottom of step 0's riser). `--at` sets the actor `Location`, so `--at X Y Z` places that corner at
world `(X,Y,Z)` and the staircase rises to `(X+steps*depth, Y+breadth, Z+steps*rise)`. This fixes
defect #2 (the old `Base` was `rise` below the corner) and matches the front-bottom-corner semantics
the build-#1 help text already advertises (`--at` help: "the staircase anchors at its front-bottom
corner").

### Winding & item labels

- **Winding** stays load-bearing: each box's six faces are built through the same `_face(ring,
  outward, …)` helper `cube`/`cylinder`/`cone` use, so every face winds CCW-from-outside (the
  importer derives the face from the winding; a flipped face inverts the solid). We do **not** call
  `cube()` (it hard-codes `item="OUTSIDE"` on all six faces); instead a small local labeled-box
  helper `_step_box(x0, x1, breadth, z_top, items, texture, flags)` builds the six faces directly
  through `_face`, taking a per-face ItemName. Winding safety is identical to `cube` (same helper,
  same axis-aligned rings).
- **Item labels** — each box carries semantic ItemName tags so `brush poly` can select a class of
  faces across the set (UED's "Select Surfaces → Matching Item"):
  - `+Z` (top / tread) → **`Step`**
  - `-X` (front face; its top `rise` is the visible riser above the previous step, the rest is
    buried against box `k-1`) → **`Rise`**
  - `+X` (back, coincident with the next step's `-X` face) → **`back`**
  - `±Y` (the two sides) → **`Side`**
  - `-Z` (bottom, on the floor) → **`Base`**

  These are the same UED vocabulary the old single-brush staircase used, so no doc/vocabulary churn.
  (The `spiral` builder still tags all faces `OUTSIDE` — it calls `cube()`. That divergence is
  deliberate for now and noted for Andrzej; the spiral redo is a separate item.)

### Side-face T-junctions — accepted, standard UE1 cross-brush behaviour

Because box `k` (height `(k+1)*rise`) is shorter than box `k+1` (height `(k+2)*rise`) and they abut
on the plane `x=(k+1)*depth`, box `k`'s top-outer side corner lands **mid-edge** on box `k+1`'s
taller `±Y` side face → an N−1-per-side **T-junction** between the two `CSG_Add` brushes. This is
**accepted**: cross-brush T-junctions between adjacent CSG solids of different heights are ubiquitous
and tolerated in UE1 (any two abutting walls of unequal height make them), and the `spiral` builder's
adjacent slabs already have the same property. UED's `LinearStairBuilder` tiled the sides into
per-step strips only because it was **one** brush (intra-brush manifoldness matters more); across
separate add-brushes the strips buy nothing and would defeat the "clean convex box per step" goal.
`level doctor` is T-junction-naive **by design** (its footer: it does not find T-junction cracks —
those are Phase-2 build-emergent), so a doctor-clean staircase can still show a hairline seam on its
sides. Verifying the union renders cleanly is a `level preview` follow-up (flagged for Andrzej; no
live editor this session). The `x=(k+1)*depth` back seam is **not** a T-junction: box `k`'s `+X`
face and box `k+1`'s `-X` face are coincident, corner-matched over `Z∈[0,(k+1)*rise]`, and
opposite-wound, so CSG culls them as interior (no z-fighting).

### Deviation from UED `LinearStairBuilder` (recorded, intentional)

The old builder's whole purpose was **face-for-face parity with UED's `LinearStairBuilder`** (a
single non-convex brush), pinned by `test_staircase_matches_ued_reference` against `Brush5` in
`level_small.t3d`. This redo **abandons that single-brush parity** in favour of the box-per-step
decomposition — the same trade-off `spiral_staircase` already makes ("Non-convex solids (stairs,
spirals) are emitted as a LIST of convex boxes rather than one non-convex brush" — the docstring
already said this; the implementation just hadn't followed for the linear stair). The resulting
*world solid* has the same stepped **profile** but is re-anchored up by one `rise` (old span
`Z∈[-rise,(steps-1)*rise]`, new `Z∈[0, steps*rise]`), so the same inputs now produce a
first-tread-one-rise-above-floor placement with nothing below the floor. Only the brush
count/decomposition and Z-placement change.

**Preserve the UED engine-fact.** `test_staircase_matches_ued_reference` was the sole executable
guard on the engine fact "UED's `LinearStairBuilder` emits ONE non-convex brush with the
`Base`/`back`/`Step`/`Rise`/`Side` face taxonomy" (captured as `Brush5` in `level_small.t3d`). Rather
than delete that knowledge (relevant to the native `bspBrushCSG` port that must reproduce UED
builds), it is **repurposed** into `test_ued_linear_stair_reference_is_one_nonconvex_brush`, which
asserts the `Brush5` fixture is a single brush with that item histogram and documents (in a comment)
that our builder deliberately diverges to box-per-step. The `Brush5` fixture stays.

### Tests to rewrite (complete list — flagged by both reviewers)

The redo breaks every test that assumed a single `Brush` return / old geometry. All are rewritten:
- `test_builders.py::test_staircase_single_brush_facecount_and_items` → per-box: `steps` boxes ×
  6 polys, item histogram `{Step, Rise, back} = 1 each, Side = 2` **per box**.
- `test_builders.py::test_staircase_corner_pivot_and_bounds` → union bounds `X∈[0,W]`, `Y∈[0,B]`,
  `Z∈[0, steps*rise]`; front-bottom corner at local origin.
- `test_builders.py::test_staircase_treads_ascend` → `Step` face Z at `(k+1)*rise`
  (`[16,32,48,64]` for rise 16, 4 steps).
- `test_builders.py::test_staircase_matches_ued_reference` → repurposed as the engine-fact guard
  above (asserts the UED *reference* shape, not our builder).
- `test_dispatch.py::test_dispatch_build_staircase_*` (hard-asserts 1 actor / `2+4*4` polys) →
  N actors named `Staircase0…N-1`, each 6 polys.
- **New:** a `level doctor`-clean test — run `run_doctor` over the generated staircase actors and
  assert **zero** error findings (watertight/convex/degenerate/fallthrough).

## Re-blessing the frozen parity goldens

`fixtures/builder_parity.json` freezes `stair_1/2/4/8` as the OLD single-brush output (blessed
against the live editor's DEINTERSECTION reconstruction). They must be regenerated for the new
geometry.

- **Documented re-bless path:** `python -m uedctl.tests.builder_parity_cases` drives the **live
  editor** (`regenerate(driver)`), captures each case per-slab, and refuses to bless a case whose
  live capture disagrees with the builder. `staircase` returning a `list[Brush]` is captured
  per-slab automatically (`capture_world_verts` already loops `_as_brushes`), exactly like
  `spiral`.
- **This session has no live editor** (integration container unavailable; native suite is red from a
  concurrent agent). The stair cases are **axis-aligned integer-coordinate boxes**, for which the
  editor's world-corner reconstruction is provably **identical** to the builder's own claimed world
  vertices — this is exactly why the `cube_*` goldens are exact integers. So the `stair_*` goldens
  are regenerated **offline from the same `builder_world_verts`/`builder_poly_count` machinery** the
  live path blesses through — no hand-typed coordinates — updating **only** the four `stair_*`
  entries and leaving every editor-blessed (rotated: cyl/cone/spiral) entry untouched.
  The offline goldens' safety against a **winding** regression rests entirely on **reusing the
  live-blessed `_face` winding logic** (the `cube_*` cases already bless it end-to-end, and
  `translate_brush` preserves winding) — the offline set-match is winding-blind by construction. So
  until the live re-bless runs, the regenerated `stair_*` goldens are a **change-detector**, not an
  editor oracle; the fixture `_meta` note's "EDITOR's reconstruction" provenance is aspirational for
  these four entries until then.
- **Flagged for Andrzej:** a live `python -m uedctl.tests.builder_parity_cases` re-bless should be
  run when the container is available to reconfirm the stair goldens end-to-end (recorded in
  `board/inbox.md`). For axis-aligned boxes this is expected to be a no-op.

A `level doctor`-clean test (zero error findings over the generated staircase actors) is the
watertightness gate. Note it is **necessary, not sufficient**: `doctor` rules out single-brush hole
causes but not build-emergent seams (the side T-junctions above) — a `level preview` of a multi-step
staircase is the deferred visual confirmation (flagged for Andrzej; no live editor this session).

### User-facing doc changes (`docs/usage.md`)

- Staircase help/behaviour: "one brush per step" (already in the help), **at/above floor**,
  front-bottom-corner `--at`, first tread one `rise` above the anchor. Remove the stale "one brush,
  matches UED's `LinearStairBuilder` face-for-face" claim and the "spiral is rough" aside if
  addressed; keep the item-label vocabulary line.
- Pivots line: staircase spans `0..W` in X, `0..breadth` in Y, **`0..steps*rise` in Z** (no longer
  "base one rise below the first tread").

## Out of scope

Spiral staircase redo (a separate `to-spec.md` item), any change to the rotated/cyl/cone goldens,
and any change to `--at`/`--rotate`/solidity flag semantics.
