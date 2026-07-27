# `brush build extrude` / `brush build revolve` — 2D-profile shape generators

**Status:** spec (ephemeral — on completion fold the built behaviour into `architecture.md` +
`unrealed/leveldesign/kb/geometry-builders.md`, then delete this file).
**Cold-review gate: PASSED (2026-07-25, two reviewers, all findings folded)** — the review corrected
real defects: the per-face outward directions were extrude-only and would have emitted inverted
revolve faces (§5.7); the prescribed UU conversion silently destroyed `--angle 65536` (§7); the
coplanar-merge gate was restated backwards (§6.1); `--at`'s new anchoring changes what `--rotate`
pivots about (§2.3); a solid off-grid revolve is a BSP-hole risk the spec had not mentioned (§4.5);
and revolve needed per-edge `ItemName`s to stay selectable (§4.4). Review-driven changes are recorded
in the `decisions.md` addendum cited below.
**Decisions ledger:** [`decisions.md` 2026-07-25 00:14 UTC](../decisions.md) (D1–D9),
[2026-07-25 01:05 UTC](../decisions.md) (D10), the 01:40 UTC spec-review addendum, and the 02:30 UTC
plan-review addendum (D11–D12). D1–D10 are Andrzej's, made in the speccing Q&A; those entries are the durable record of the choices
*and the alternatives rejected*.
**Board item:** [`to-build/`](../board/to-build/) #12 — on-deck, both gates passed. Triaged
forward through `to-plan.md` from [`to-spec.md`](../board/to-spec.md), where it
was raised by the corpus brush-idiom study
([`specs/2026-07-24-corpus-brush-idioms.md`](2026-07-24-corpus-brush-idioms.md) §7 gap 6).

---

## 1. The gap, in one paragraph

`brush build` today offers six shapes — `cube`, `cylinder`, `cone`, `sheet`, `staircase`, `spiral`
(`cli.py`, `builders.py`). Every one of them is a *fixed parametric* shape: you choose sizes, not a
silhouette. But one of UnrealEd's two standard ways to build geometry is the **2D shape editor**: draw
a closed polygon in a 2D viewport, then **Extrude** it (sweep it in a straight line) or **Revolve** it
(sweep it around a pivot axis). uedcli has no equivalent, so any shape whose cross-section is not a
box, an n-gon, or a stair — an arch voussoir, an L-shaped ledge, a moulded cornice, a chamfered
pillar, a curved corridor — is unbuildable except by hand-authoring T3D or chaining `brush clip`
planes. The corpus brush-idiom study named this the single biggest capability gap it surfaced, because
it expects extruded profiles to dominate real Deus Ex brushwork.

*(Evidence note: our own kb documents the native `BrushBuilders` in full detail
([`kb/geometry-builders.md`](../unrealed/leveldesign/kb/geometry-builders.md) §1) and covers the 2D
shape editor only under §4 "Curved geometry", which is tagged **📖** — extracted from the binary string
table, semantics inferred — apart from the one-brush fact of §4.3, which Andrzej attested directly
(✅). So "one of the two standard ways" is as strong a claim as the repo's evidence supports for the
workflow's *prevalence*; the earlier draft's "*the* canonical method" was not.)*

This spec defines **two new generators** that close it, plus the small shared vocabulary they need.

**Terms used throughout.** A **profile** is the closed 2D polygon you draw. A **generator** is a
stateless uedcli verb that prints a T3D snippet to stdout and touches no level (`brush build …`); the
caller pipes it into `actor add -`. A **brush** is one CSG solid; a **face** (the engine's `FPoly`) is
one flat polygon of that solid. **Convex** means no interior angle exceeds 180°. **UU** = unreal
rotation units, the engine's 16-bit angle field: `65536` = a full turn, `16384` = 90°, `4096` = 22.5°.
The **sweep frame** is the right-handed triple `(u, v, w)` where `u`,`v` are the profile's own 2D axes
and `w` = the `--axis` direction (§2.2).

---

## 2. The shared profile vocabulary

Both verbs take the *same* profile grammar, orientation rule, and anchor rule. That sharing is the
reason they are specced together (**D1**): two verbs invented separately would have drifted into two
incompatible ways of describing the same 2D polygon.

### 2.1 The profile: repeatable `--point U,V` (**D2**)

The profile is given as a **repeatable `--point U,V` flag**; argument order is ring order.

```
brush build extrude --axis y \
  --point 0,0 --point 128,0 --point 128,64 --point 0,64 \
  --depth 32 --at 512,0,64 | actor add -
```

The ring is **implicitly closed** — do not repeat the first point as the last (a repeated final point
is welded away by §5 rather than erroring, so it is harmless if a caller does).

**Parsing and arity — specified, because `argparse` cannot express any of it.** `--point` uses
`action="append"` with a dedicated 2D parser (the existing `parse_coord` is a 3-tuple parser and is
not reused). Each token is split on a single comma into exactly two fields and parsed to `Decimal`
for validation and error text, then **converted to `float` at the builder boundary** like every other
shape — the builders' vector maths (`_newell`, `_tex_basis`) is float-only and raises `TypeError` on
mixed Decimal/float operands, and revolve's trig cannot stay exact anyway. Nothing is lost:
`make_brush_actor` re-Decimalizes via `emit.clean`, whose `_to_decimal` is `Decimal(str(value))`, so
an authored `12.5` round-trips unchanged. Every one of the following exits **2** with a message
naming the offending token, never a traceback
(`CLAUDE.md`: "Never let a Python exception reach the CLI user … Cover each path with a regression
test"):

| Input | Result |
|-----------------------|---|
| `--point 128`         | exit 2: `--point needs U,V (two comma-separated numbers), got: '128'` |
| `--point 1,2,3`       | exit 2, same message, naming the token |
| `--point a,b`         | exit 2: `--point U,V must be numbers, got: 'a,b'` |
| fewer than 3 `--point`| exit 2: `a profile needs at least 3 points, got N` |
| zero `--point`        | the same "at least 3" error (the flag is not `required=True`, so the arity check is one rule in one place) |

Arity is checked in the dispatch handler, before any geometry is built, and again after §5's cleanup
(welding can drop the count below 3).

*Rejected:* a single `--profile "u,v u,v …"` string (compact, but quoting-sensitive and invisible in
`--help`); a **point list on stdin via `-`** (pipe-friendly, but uedcli deliberately has exactly two
stdin conventions — a newline-separated *name list* and a *T3D snippet* — and the tool's `CLAUDE.md`
requires keeping them distinct; a third, a bare coordinate list, would blur what `-` means per verb).
If long generated profiles ever become a real workflow, adding stdin later is a compatible extension;
starting there is not.

### 2.2 Orientation: `--axis x|y|z`, default `z` (**D3**)

`--axis` names the world axis the **profile plane is normal to** — equivalently, the direction the
sweep grows. The 2D `(u,v)` coordinates map onto the two remaining world axes by **right-handed
cyclic order**, so `u × v = +axis` in every case:

| `--axis`        | `u` | `v` | extrude sweeps along | revolve axis is |
|-----------------|-----|-----|----------------------|---|
| `z` *(default)* | X   | Y   | +Z                   | Y (the line `u = 0`) |
| `x`             | Y   | Z   | +X                   | Z |
| `y`             | Z   | X   | +Y                   | X |

Right-handed cycling is what makes one winding rule work for all three orientations: a
counter-clockwise profile in `(u,v)` always has its 2D normal pointing along `+axis`. The last column
is the revolve axis of §4, spelled out here so the reader need not derive it.

This is also the naming precedent for the parked `brush build cylinder/cone --axis x|y|z` item in
[`to-spec.md`](../board/to-spec.md) — that item should adopt this flag name and this table rather than
inventing a second spelling. Both exist to remove the same problem: without them the author must
reason about which of pitch/yaw/roll lays a +Z shape onto Y and reach for `--rotate`.

*Rejected:* `--plane xy|xz|yz` (reuses `brush build sheet`'s vocabulary, but for a *swept solid* the
natural parameter is the sweep direction, and it would leave the cylinder/cone item needing a
different word for the identical concept); XY-only in v1 (reproduces exactly the `--rotate`
axis-guessing ergonomics this removes).

### 2.3 Anchoring: `--at` is where profile `(0,0)` lands (**D4**)

The emitted brush's **local vertices are the authored profile coordinates, verbatim** — no
re-centering — and the sweep grows from the profile plane in the `+axis` direction, `0 .. depth` (for
revolve: `0 .. angle`). The actor's `Location` is `--at`, so:

> **`--at` is the world point that profile coordinate `(0,0)` lands on.**

```
--point 0,0 --point 128,0 --point 128,64 --point 0,64
--axis z --depth 32 --at 512,0,64
⇒ occupies X 512..640, Y 0..64, Z 64..96
```

(For `--axis z` the profile's `u`→X and `v`→Y, each offset by the matching component of
`--at = (512, 0, 64)`; the sweep then runs along Z from `--at`'s Z of 64 to `64 + depth`.)

For **revolve** the same rule has a particularly useful reading: the revolve axis passes through
profile `(0,0)` (§4), so `--at` is the world position of the **bend centre**.

**This is the THIRD `--at` exception, and one of the other two is currently undocumented.** The
`--at` help (`cli.py`) names only the staircase (front-bottom corner) — but `builders.spiral_staircase`
already anchors at "the base of the column axis" (centred in XY, *bottom* in Z, not the geometric
centre on every axis; `builders.py:362-363`), so the help is stale today. §12 carries the task of
rewriting that help to name all three: staircase (front-bottom corner), spiral (base of the column
axis), extrude/revolve (profile `(0,0)`). *(A fourth, unrelated sense exists on
`brush intersect`/`deintersect`, where `--at` places the merged brush's pivot.)*

**Consequence you must document: `--rotate` no longer spins the brush in place.** An actor's
`Rotation` is applied about its local origin. For every existing shape the local vertices are centred
on the origin, so `--rotate` turns the brush about its own centre. Under D4 the local origin is
profile `(0,0)` — for an extrude typically a corner, for a revolve the bend centre, and for a profile
authored at `u ∈ [512, 640]` a point 512 uu *outside* the brush. `--rotate 0,16384,0` on that brush
swings it across the map instead of turning it. This is correct behaviour for the anchor rule, not a
bug, but it is surprising, so it must appear in both verbs' `--help` and in `usage.md` (§12). The same
lever-arm effect makes `--rotate`'s existing off-grid-vertex stderr warning fire more often.

*Rejected:* **geometric center, ±depth/2** — uniform with cube/cylinder/cone/sheet and needing no new
exception, but it throws away the authored 2D coordinate system, which is the entire point of drawing
a profile: a ring of arch voussoirs laid out at known offsets would all collapse onto the same
centered brush. *Rejected:* **anchor on the profile's FIRST point** (Andrzej's own initial proposal) —
same lands-where-you-drew-it property and no need to know where `(0,0)` sits, but re-ordering the ring
silently moves the brush in the world, and revolve has no meaningful "first point" (it anchors on a
pivot axis), so the two verbs would need different rules. `(0,0)` is edit-stable and shared.
*Rejected:* **an `--origin center|min|max|keep|X,Y,Z` mode flag**, the vocabulary
`brush intersect`/`deintersect` already uses. It would make the anchor selectable rather than fixed,
but the profile frame *is* the anchor under D4, so a mode flag would re-introduce the ambiguity D4
removes and add a fourth meaning to a word that already has three. Filed as a follow-up if authors
ask for it.

### 2.4 Everything else is the standard generator surface

Both verbs take the full `_common_build_opts` set: `--at`, `--base-name`, `--csg`, `--solidity`,
`--folder`, `--label`, `--texture`, `--mover-class`, `--prop`, `--rotate`. They are ordinary
generators — stateless, stdout-only, composing with `actor add -`, `brush replace`, `brush intersect`,
`stash`, and the folder/label carriers — with no bespoke plumbing. The one *behavioural* difference
from the other shapes is `--rotate`'s pivot, above.

---

## 3. `brush build extrude`

Sweep the profile in a straight line along `+axis`.

| Flag      | Type  | Required   | Meaning |
|-----------|-------|------------|---|
| `--point` | `U,V` | yes (≥3)   | repeatable profile vertex; argument order = ring order (§2.1) |
| `--depth` | float | yes        | sweep length along `+axis`, in world units (uu); must be > 0 |

Plus §2.4's common options.

**Geometry.** With a profile of `n` (post-cleanup, §5) vertices:

- **near cap** at `w = 0`, facing `-axis`;
- **far cap** at `w = depth`, facing `+axis`;
- **`n` side quads**, one per profile edge, each spanning `w ∈ [0, depth]`.

Face count is `n + 2` when the profile is convex and `n ≤ 16`; a concave or over-16-vertex profile
tiles its caps into several faces each (§6), so the count is `n + (2 × pieces)`.

**Face `ItemName`s** (UnrealEd's semantic face label, used for selection-by-item): caps are `Cap`;
the side quad of profile edge `k` is **`Side<k>`** (`Side0`, `Side1`, …). Per-edge naming rather than
a single `Side` is what keeps `brush poly find --item` usable — see §4.4, where it matters most.

**Worked example — an L-shaped ledge** (concave profile, one brush):

```
brush build extrude --axis y --depth 16 --at 0,0,0 \
  --point 0,0 --point 96,0 --point 96,32 --point 32,32 --point 32,96 --point 0,96 \
  --folder castle.hall --texture Ancient.Floors.Stone1 | actor add -
```

**Worked example — an arch voussoir** (a trapezoid profile extruded through the wall thickness; this
is why taper/bevel variants are *out* of scope, §8):

```
brush build extrude --axis y --depth 64 --at 0,0,256 \
  --point 0,0 --point 48,0 --point 40,64 --point 8,64 | actor add -
```

---

## 4. `brush build revolve`

Sweep the profile around an in-plane axis, in `--segments` flat facets.

| Flag         | Type | Required        | Meaning |
|--------------|------|-----------------|---|
| `--angle`    | int  | yes             | total sweep in UU, `0 < angle ≤ 65536`; `65536` is a closed full turn |
| `--segments` | int  | no (see §4.2)   | number of flat facets the sweep is divided into |

Plus §2.4's common options. Note `--angle` is an **integer count of UU**, not an FRotator field — see
§7 for why that distinction is load-bearing.

### 4.1 The revolve axis, and why there is no `--pivot` (**D10**)

**The revolve axis is the profile plane's own `v` axis — the line `u = 0`, passing through profile
coordinate `(0,0)`. There is no `--pivot` flag.** Distance from the axis is expressed in the profile
coordinates themselves: a profile drawn at `u ∈ [64, 192]` revolves at radii 64 to 192. §2.2's table
gives the resulting world axis per `--axis`. UnrealEd's "move the green pivot away from the
cross-section" ([`kb/geometry-builders.md`](../unrealed/leveldesign/kb/geometry-builders.md) §4) —
what turns a sweep into a *curved corridor* rather than a solid of revolution about its own edge — is
therefore spelled by drawing the profile away from `u = 0`.

This is strictly better than a separate pivot parameter, not merely equivalent to one:

- **A pivot flag would be redundant.** With the axis fixed parallel to `v`, shifting the profile's
  `u` coordinates and moving the axis are the same operation.
- **It sharpens the anchor.** Because profile `(0,0)` lies **on** the revolve axis, §2.3's rule makes
  **`--at` the world position of the bend centre** — the point you actually want to place.
- **It tightens the family.** Extrude and revolve take exactly the same profile, `--axis` and `--at`,
  differing only in `--depth` vs `--angle`/`--segments`.
- **It simplifies validation** (§5.6).

The cost: a point list authored for an extrude (which typically wants `(0,0)` at a corner) needs its
`u` values re-written to be reused for a revolve.

*Rejected:* a **free in-plane axis** (`--pivot U,V` + a tilt angle), which would allow conical sweeps
— a tapering curved duct, a splayed arch ring — without pre-rotating the profile. It costs two flags,
a coordinate that is redundant whenever the axis is untilted, and a general point-line side test in
validation; and the same shapes are reachable by rotating the authored points. Filed as a follow-up
if a real use case appears.

### 4.2 Sweep direction, angle, and segments

**The profile must lie strictly on the positive-`u` side** (§5.6). Given that, the sweep grows toward
`+axis`, exactly like extrude — so both verbs share one mental model ("the shape grows in the
`--axis` direction"). Concretely, in the sweep frame a profile point `(u, v)` maps at sweep angle `θ`
to `u·cos θ · û + v · v̂ + u·sin θ · ŵ`.

*(This is why negative `u` is rejected rather than merely discouraged: for `u < 0` the identical
rotation grows the solid toward **−axis**, silently inverting the one invariant the shared `--axis`
model rests on, and flipping the sign of every cap's outward direction. Mirroring the profile's `u`
values is the supported way to build the other bulge. The earlier draft offered "the opposite
`--axis`" as an escape hatch — that is not a thing: `--axis` takes `x|y|z` only, and choosing another
value re-orients the whole profile plane rather than reversing the sweep.)*

**`--segments` default:** `max(1, floor(angle / 4096 + 0.5))` — i.e. **one facet per 22.5°**, which is
UnrealEd's own default density ("16 pieces = 360°", `kb/geometry-builders.md` §4 — a **📖**-level fact,
so this default rests on inferred semantics, not a verified measurement). A 90° bend (`--angle 16384`)
therefore defaults to 4 segments, matching the kb's `Use=4` recipe. The rounding is spelled with an
explicit `floor(x + 0.5)` rather than `round()` because Python's `round()` is banker's rounding and
would make the tie cases surprising.

### 4.3 Output is ONE brush (**D5**)

A revolve emits a single brush actor whose swept inner wall is concave, with its caps tiled into
convex faces per §6 — **not** one brush per segment. Andrzej: this matches what UnrealEd itself
produces: **every 2D-shape-editor operation — extrude, revolve, sheet — yields the single red builder
brush, faceted, which you then Add/Subtract once**; it is not one brush per facet or per segment.
*(Attested by Andrzej from direct UnrealEd use, 2026-07-25; recorded in the durable kb at
[`kb/geometry-builders.md`](../unrealed/leveldesign/kb/geometry-builders.md) §4, tagged ✅ with that
provenance. An earlier draft listed this in §11 as needing a live spike — it does not.)*

*Rejected:* **one convex brush per segment** (the `spiral` precedent) — it would be correct in all
three render/build tiers including the offline `--native` draft, and would hand CSG convex solids to
carve with, but it diverges from UED's output, emits N actors per sweep, and puts internal seams
through the solid.

### 4.4 Geometry and face naming

With `n` profile vertices and `s` segments: `n × s` swept side quads, plus two caps (tiled per §6) at
the start and end of the sweep. Every swept quad is **planar** — a straight edge swept by a rotation
about a coplanar axis always yields a planar quad, for any `u₁,u₂,v₁,v₂` — so no non-planarity finding
arises from the sweep itself.

When `--angle 65536`, the sweep closes on itself: the two caps coincide and are **omitted entirely**,
and the last segment's far ring is the first segment's near ring (no duplicated vertex column).

**`ItemName`s: caps are `Cap`; the swept face of profile edge `k` is `Side<k>` in every segment.**
A single `Side` for all `n × s` faces would make the brush unselectable in practice: on a 4-segment
curved corridor all 16 wall/floor/ceiling faces would share one item, and inner and outer walls are
both `slant` to `brush poly find --facing`, so "retexture just the inner wall" would have no selector
at all. Keying the item to the *profile edge* (stable across segments) gives exactly the handle the
author thinks in — `--item Side0` is "the face swept by my first profile edge", the whole strip of it.
This mirrors `spiral_staircase`, which distinguishes `Inner`/`Outer`/`Side`/`Step`/`Base` for the same
reason. Cheap now; unfixable later without breaking §10's committed goldens.

### 4.5 Off-grid geometry: a revolve is a BSP-hole risk when solid

Every revolve vertex except at `θ = 0` lands on `radius · cos/sin(θ)` — irrational. `emit.clean`
deliberately **preserves** genuine fractions, and `kb/csg-bsp.md` §5.5 records the consequence as
uedcli's own standing caveat: "grid discipline is guidance, not an enforced operation — uedcli does
NOT snap coordinates for you." That section's Tier-A prevention list is unambiguous: an off-grid
**solid** brush throws its partition planes off-grid, landing faces inside the ±0.25 uu
`SplitWithPlane` band and the ~1e-4 `RemoveColinears` band → slivers, T-junctions, discarded `FPoly`s,
holes. Its prescribed mitigation is to **push off-grid / curved / detail geometry to semisolid**,
which receives cuts but emits no world-splitting planes.

This bites the flagship curved-corridor case hardest: a large `--csg subtract` *solid* that carves the
world BSP. So:

- **`revolve --help` and `usage.md` state it** (§12), next to the `--native` caveat.
- **The curved-corridor recipe recommends `--solidity semisolid`** where the corridor is detail rather
  than structure.
- **A stderr advisory fires** when an emitted brush has off-grid vertices *and* is solid (`--csg
  add|subtract` with the default `--solidity solid`) — not on semisolid/nonsolid, where the situation
  is already handled, so the advisory stays signal. This reuses the precedent of `--rotate`'s existing
  off-grid warning. It applies to extrude too (an author can type off-grid points), at no extra cost.

`brush build cylinder`/`cone` have the same latent property and no such warning; §12 files that as a
board item rather than widening this change.

### 4.6 The poly-budget advisory

A 16-segment revolve of an 8-point profile emits 128 side faces plus caps — a lot of BSP for one
brush. When the emitted actor's **total face count exceeds 64**, print to **stderr** (never stdout —
the pipe stays clean):

```
brush build revolve: 130 faces (8 profile edges × 16 segments + 2 caps) — a heavy brush for the BSP;
consider fewer --segments, or --solidity semisolid so it does not partition the world.
```

Exit status is unaffected: this is an advisory about a legitimate build, not a half-answer.

### 4.7 v1 limitations

- **The profile must be strictly off-axis and positive-`u`** (§5.6): every `u > 0`. A profile
  straddling the axis sweeps into a self-intersecting solid; a profile *touching* the axis degenerates
  the swept faces along it into zero-width quads (they would need collapsing to triangles). Both
  **exit 2** naming the offending vertex. Sphere-of-revolution shapes (which need the touching case)
  are a follow-up item.
- **A full turn produces a genus-1 solid (a torus), which is unverified territory.** §6's
  single-non-convex-brush argument rests on the `staircase` precedent — but a staircase is a
  simply-connected stepped hull, whereas a closed revolve of an off-axis profile has a *hole through
  it*. Nothing in `kb/csg-bsp.md`, `quirks.md` or the spikes evidences UE1 `bspBrushCSG` behaviour on a
  genus-1 brush. `--angle 65536` is therefore **kept but listed in §11 for live verification**; if it
  builds badly, the fallback is two 180° revolves (two brushes), which costs an actor and nothing
  else. This is called out rather than silently asserted under a precedent that does not reach it.

**Worked example — a 90° curved corridor** (the kb recipe, as one verb):

```
brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 \
  --at 0,0,0 --folder castle.corridor | actor add -
```

The profile is the corridor's cross-section in `(u,v) = (Y,Z)`: a passage 128 uu wide and 128 uu
tall, whose inner wall sits 64 uu from the bend centre and outer wall 192 uu. The revolve axis is the
vertical line through `--at`, so `--at 0,0,0` puts the bend centre at the world origin; the sweep
bulges into +X. `--solidity semisolid` per §4.5.

---

## 5. Profile cleanup and validation

Applied identically by both verbs, before any face is built. This mirrors what the engine does to
every `FPoly` at `FPoly::Fix` / `FPoly::RemoveColinears` (see
[`kb/csg-bsp.md`](../unrealed/leveldesign/kb/csg-bsp.md) §5.2), so uedcli rejects offline what the
editor would silently mangle or crash on.

1. **Weld** consecutive (and wrap-around) near-duplicate points, reusing `builders.WELD` (1e-3) — the
   same tolerance the existing builders already use via `_dedup_ring`.
2. **Drop collinear** points: a vertex whose two adjacent edges are parallel contributes a redundant
   coplanar split of one flat side, and the engine's `RemoveColinears` deletes it at build time
   regardless — so drop it up front, and the emitted face count matches what is built.
3. **Require ≥3 distinct points** after 1–2 — else exit 2 naming the count.
4. **Reject a non-simple profile.** Exit 2, naming the offending edges or vertex, if either holds:
   - any two **non-adjacent** edges intersect *at all* — crossing, touching at an endpoint (a pinch),
     or collinear-overlapping;
   - any vertex value repeats **anywhere** in the ring (step 1 only welds *consecutive* duplicates, so
     a ring like `A B C A D E` survives it while being a figure-eight).

   A non-simple profile has no consistent inside; ear-clipping it (§6) yields overlapping or inverted
   "convex" pieces with no error, and the emitted brush is a self-intersecting solid — a guaranteed
   BSP defect and a plausible editor crash.
5. **Normalize winding**: compute the profile's signed area in `(u,v)`. If it is exactly zero, exit 2
   (a degenerate profile with no area). If negative (clockwise), reverse the point list. Downstream
   face construction can then assume counter-clockwise, and the author never has to think about
   winding — either order is accepted.
6. **Range and degeneracy rejections**, each naming the offending value:
   - `--depth <= 0`;
   - `--angle` outside `(0, 65536]` — checked on the **raw integer**, before any unit conversion (§7);
   - `--segments < 1`;
   - **`angle / segments >= 32768`** (a facet of 180° or more). A single 180° facet maps every point
     `(u,v)` to `(−u,v)` in the profile plane with `w = 0`: the "solid" is flat, zero-volume, with
     coincident caps. This mirrors `spiral_staircase`'s existing `0 < degrees_per_step < 180` guard;
   - **`segments < 3` when `angle == 65536`** — a closed turn in 1 or 2 facets degenerates (the far
     ring welds onto the near ring, collapsing every side quad);
   - **revolve: any profile vertex with `u <= 0`** (§4.2, §4.7).

### 5.7 Winding and per-face outward directions — DIFFERENT PER VERB

Face emission goes through `builders._face`, which **flips the ring** whenever its Newell normal
disagrees with the supplied outward direction. So the outward hint is not advisory: a hint that is
merely "not the right sign on the true normal" produces a **backwards-wound face** — which is exactly
`doctor.check_watertight`'s "a face is wound backwards → inverted solid → CSG crash / HOM", and which
UnrealEd's importer cannot recover from (it ignores the emitted `Normal` and derives the face from the
winding).

**Extrude** (the sweep is a translation, so nothing rotates):

| Face          | Outward direction |
|---------------|---|
| near cap      | `−w` |
| far cap       | `+w` |
| side quad `k` | the in-plane edge normal: for a CCW profile edge `(du, dv)`, that is `(dv, −du)` in `(u,v)`, mapped to world |

**Revolve** (every face is rotated about the revolve axis, so the extrude hints are wrong):

| Face                      | Outward direction |
|---------------------------|---|
| near cap (at `θ = 0`)     | `−w` — **unchanged from extrude** (see below) |
| far cap (at `θ = angle`)  | `+w` **rotated about the revolve axis by `angle`** — for a 90° sweep it is `−û`, exactly perpendicular to `+w` |
| side quad of edge `k` in segment `m` | the quad's OWN normal, computed from its emitted vertex ring and oriented outward — **not** the formula this row originally gave (see the correction below) |

**CORRECTION (2026-07-26, from the follow-up branch's build review).** This row originally read
"`(dv, −du)` mapped to `(u,v)`-world, then **rotated about the revolve axis by that segment's
mid-angle** `θ_m + Δ/2`", and that is what shipped. It is **not** the quad's true normal: de-rotated,
the true normal is proportional to `(dv, −du·cos(Δ/2))` for a facet of angle `Δ`, so the two agree
only when `du == 0` or `dv == 0` — i.e. only for an axis-parallel profile edge. Every profile in the
test suite was a rectangle, so the error went unnoticed until a cold review. The angular error is
`90° − 2·atan(√cos(Δ/2))`: 0.56° at the default 22.5° facet, 2.27° at 45°, 9.88° at 90°.

It never mis-WINDS a face — `_dot(nw, shortcut) = dv² + du²·cos(Δ/2) > 0` for every `Δ < 180°`,
which the CLI enforces — so `doctor` and a signed-volume check are both structurally blind to it.
It lands in the TEXTURE BASIS instead: `_face` seeds `_tex_basis` from the hint, and per
`unrealed/t3d.md` the editor PRESERVES `TextureU`/`TextureV` while recomputing `Normal`, so the
error survives into the built map as a texture projected from off the face's plane.
`builders.revolve` now computes each side quad's own Newell normal and uses the mid-angle direction
only to ORIENT it (its sign is all that was ever needed). The cap rows above are unchanged and
remain correct.

**Why the near cap does not rotate.** Under §4.2's sweep map, the `θ = 0` cap lies in the `(û, v̂)`
plane and the solid grows toward `+ŵ` (every `u > 0`), so its outward is `−ŵ` — identical to
extrude's. Only the *far* cap has rotated away from the profile plane. *(An earlier draft of this
spec gave the near cap as "the profile-plane tangent at `θ=0`, not `−w`", spelled `−v̂ × t̂(0)`. That
is wrong twice over: the tangent at `θ=0` **is** `+ŵ`, and the cross product evaluates to `−û` for a
right-handed frame. Both cold reviewers of the build plan caught it independently — see
`decisions.md` 2026-07-25 02:30 UTC.)*

Getting the rotated hints wrong is not cosmetic. A hint 90° off the true normal gives
`_dot(newell, outward) == 0`, so `_face` neither flips nor keeps deterministically, and `_tex_basis`
derives `TextureU/V` from a normal that is not the face's, putting the texture axes out of the face
plane. And side quads whose true outward has rotated past 90° from the unrotated hint get their
correctly-wound rings **reversed** — roughly half the side faces of a full-turn revolve. The worst
affected are edges parallel to the revolve axis (`du = 0`), i.e. the inner and outer corridor walls.
§10 pins this with `doctor`-clean assertions at 90°, 180° and a full turn — noting that a **full turn
omits both caps**, so the cap hints are only exercised by the partial-sweep cases.

---

## 6. Concave profiles and the 16-vertex cap: tiled caps (**D6**)

Two independent constraints force the same mechanism:

- **The engine's `FPoly` is convex** — `doctor` reports a concave face as an error (the per-face test
  is `_is_convex`, `doctor.py:177`, run inside **`check_degenerate`** and emitted under
  `category="convex"`; there is no `check_convex` function): "CSG assumes convex faces — a concave face
  splits/builds wrong → hole or crash".
- **An `FPoly` holds at most 16 vertices** (`FPoly::VERTEX_THRESHOLD`; `kb/csg-bsp.md` §5.2, decoded in
  `spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`). A 24-sided profile's cap exceeds the
  engine's fixed array bound even though it is perfectly convex. *(The evidence is for the in-memory
  polygon's bound; the repo has no measurement of what `MAP IMPORTADD` does with a >16-vertex authored
  poly, so the spec does not claim a "serialization limit" — the bound is reason enough to split.)*

**Decision: tile the caps into convex sub-faces and emit ONE brush.** The side faces are unaffected
(always quads). This is precisely the `staircase` precedent — a non-convex **brush** built from convex
**faces** — which `doctor` accepts, UnrealEd's `level materialize` builds correctly, and the real
engine (`level preview --game`, the default tier) renders correctly.

**Algorithm.** Ear-clip the CCW profile into triangles, then merge adjacent triangles across shared
diagonals wherever the merged polygon stays convex (Hertel–Mehlhorn), stopping any piece at 16
vertices. Merging matters: it keeps the cap face count near the minimum convex decomposition instead
of emitting `n−2` triangles, and every extra face is BSP nodes and rendering cost.

**Required invariant:** a **convex profile of ≤16 vertices must decompose to exactly ONE piece**, so a
plain box or hexagonal prism emits exactly two cap faces and nothing changes for the simple case.
This gets an explicit regression test (§10).

**No T-junctions.** Tiling adds only *diagonals* of the original polygon — no new vertices on the
boundary — so every cap boundary edge still matches its side quad's edge exactly, and
`doctor`'s `check_watertight` sees a clean solid. (The `staircase` needed T-junction tolerance; this
does not.)

### 6.1 Why UnrealEd's "merge faces" is not an alternative — and what it does buy us

UnrealEd has a face-merging capability, so it is worth stating precisely why tiling is still the
answer. **Two distinct things carry the name:**

1. **"Merge Polygons" — the explicit GUI command** on selected surfaces. Import does **not**
   auto-merge: a 7-poly split-face cube round-trips through `BRUSH IMPORT`/`MAP IMPORTADD` as 7 polys
   (`unrealed/quirks.md` "No coplanar auto-merge"). It is a manual authoring convenience and never
   runs against our T3D.
2. **`bspMergeCoplanars` — a build pass** (Editor.dll `0x36200`), part of every `MAP REBUILD` /
   `BSP REBUILD` (`bspBuildFPolys → bspMergeCoplanars → bspBuild`, called unconditionally — the
   LAME/GOOD/OPTIMAL difference is splitter sampling, not whether merge runs; `kb/csg-bsp.md`). It
   fuses adjacent coplanar **BSP surfaces** — build output, not authored geometry.

**The mechanism** 🔬 (instruction-decoded from `Editor.dll 0x34b10` —
[`spikes/2026-07-15-native-materialize/sections/82-bspbrushcsg-port-decode.md`](../spikes/2026-07-15-native-materialize/sections/82-bspbrushcsg-port-decode.md)
§10.3, ported as `uedcli-native/src/bspcsg.rs::try_to_merge`): `TryToMerge(P1, P2)` first rejects
outright if **`NV1 + NV2 > 16`** — a gate on the two inputs' vertex **sum**, applied *before* any
splicing. It then looks for a shared point (the first hit in `(i,j)` scan order) **whose forward or
backward neighbour also matches**, using `FPointsAreSame`'s 0.002 **box** (Chebyshev) tolerance;
without that neighbour match it returns 0. On success it splices all of P1 with P2 minus its two
shared vertices, runs `RemoveColinears`, and rejects if the result falls below 3 or exceeds 16
vertices. `MergeCoplanarPolys` (`0x33cb0`) applies it pairwise to a fixpoint within each coplanar
group.

**It cannot replace cap tiling**, for three separate reasons:

- **Opposite direction.** Merge *fuses* coplanar neighbours; we need the inverse — decomposing one
  concave cap into convex pieces. No editor operation makes a concave authored face legal.
- **Wrong layer and time.** It acts on BSP surfaces after CSG (or manually on selected surfaces).
  Our T3D is consumed by CSG *before* any of that, and CSG is where convexity actually matters:
  `SplitWithPlane` yields exactly two pieces from a plane cut, which is only correct for a convex
  polygon — a concave one can require more, which is the real mechanism behind the "keep every face
  convex" rule (`kb/csg-bsp.md` §5.5).
- **Merge itself does not enforce convexity.** The decode shows only the `≤16` / `≥3` gates, no
  convexity test — so the build pass can fuse two convex surfaces into a **concave** one. That is
  tolerable for a compiled surface and tells us nothing about what is legal to *author*. (Whether
  `Engine.dll`'s `RemoveColinears` carries an additional convexity reject is **not settled** by our
  evidence — our port `fpoly.rs::remove_colinears` has none, but a port is not proof of the binary.
  Either answer leaves this design unchanged; see §11.)

**What it does buy us.** Cap tiles are coplanar by construction and share **exact, full edges** —
tiling adds only *diagonals* of the profile, introducing no new boundary vertices — which satisfies
`TryToMerge`'s shared-edge condition. So on `MAP REBUILD`, the built map should carry **fewer cap
surfaces than the tiling emitted**, wherever each pairwise merge's two pieces have vertex counts
**summing to ≤16**. For a cap tiled into quads and pentagons that is essentially always, so most tiled
caps should come back as one surface — but note the gate is on the *sum of the inputs*, not on the
fused ring: two 9-vertex tiles fuse to a 16-vertex ring, legal as an `FPoly`, yet `TryToMerge` rejects
them at `18 > 16`. A cap tiled into three or more pieces may therefore fuse only partially. This is an
**inference from the decode, not yet observed** — §11 carries the item to verify it live.

**The one caveat, stated plainly.** The offline `level preview --native` draft tier classifies
solidity with `uedcli-native/src/csg.rs:62 point_in_convex` — a point is inside a brush iff it is
*behind every face plane*, which is only valid for a convex solid. For a concave brush (an L-profile,
or a revolve's inner wall) the notch is behind all the planes too, so it is classified solid and
**drawn filled in**. Native *materialize* is not affected: it defaults to `core="bspcsg"`
(`native/materialize.py:822`), the incremental `bspBrushCSG` port, which never calls `point_in_convex`
— though `bspcsg.rs`'s own comments flag a non-convex **first Add** as an unhandled case (its
convex world-seed shortcut), so a concave brush should not be a level's leading Add. UnrealEd's
`level materialize` and the default `--game` preview are correct. This must be repeated in `usage.md`
and in the verb `--help`, next to the concave-profile support, so nobody debugs a preview artefact as
a geometry bug. **`builders.py:305-309`'s `staircase` docstring states the broader, now-stale claim
that native *materialize* also mis-classifies** — §12 carries fixing it, so the caveat does not reach
users in two contradictory forms.

---

## 7. Angle units: UU everywhere, and a retrofit (**D7**)

`decisions.md` 2026-07-19 19:28 UTC established that rotation CLI input is **unreal rotation units,
not degrees** — "one unit system end to end", extended even to the preview camera-pose grammar. That
decision reached the *rotation* flags but not the **builder-geometry** angles, so uedcli today mixes
units: `brush build cylinder --angle-offset` and `brush build cone --angle-offset` take **degrees**,
and `brush build spiral --degrees-per-step` takes **degrees**, while `--rotate` takes UU.

**Decision: generalize UU to builder angles, and fix the two existing flags in the same change.**

| Flag                                    | Before                         | After |
|-----------------------------------------|--------------------------------|---|
| `brush build revolve --angle`           | *(new)*                        | UU |
| `brush build spiral --degrees-per-step` | degrees (`30`), default `30.0` | **renamed** `--angle-per-step`, UU, default `8192` (45°) |
| `brush build cylinder --angle-offset`   | degrees (`22.5`)               | **deleted** → `--align-to-side` (bool, §7.1) |
| `brush build cone --angle-offset`       | degrees (`22.5`)               | **deleted** → `--align-to-side` (bool, §7.1) |

The justification is **unit consistency with `--rotate` and the rest of the substrate**, and that
alone. *(An earlier draft also argued UU "divides better". That is false in general: `65536 = 2¹⁶`, so
only power-of-two counts divide it exactly — `65536/16 = 4096` — while every threefold division is
exact in degrees instead: `360/3 = 120`, `/6 = 60`, `/12 = 30`, versus `65536/3 = 21845.33…`. The
practical consequence, worth one line in `usage.md`: a 60° or 120° bend is not exactly representable,
so `--angle 10923` is 60.002°.)*

**Mechanism — and the trap to avoid.** `rotation.uu_field()` and `rotation.uu_to_deg()` both wrap
mod 65536 (`rotation.py:89`, `:93-99`), because they exist to parse an **FRotator field**, which is
inherently modular. A sweep **magnitude** is not a field: `0` and a full turn are different values, and
`uu_to_deg(65536)` is `0.0`. Routing `--angle` through them would silently collapse the closed full
turn (§4.4's special case) to zero. So:

- `--angle` and `--angle-per-step` are parsed as plain `int`, range-checked on the **raw** value
  (§5.6), and converted with `degrees = uu * 360.0 / 65536.0` — **no modulo, and not via
  `uu_field`/`uu_to_deg`**, which stay reserved for `--rotate` and friends.
- `builders.py` remains internally in degrees (its trig is in degrees). This is the same *shape* of
  arrangement `preview_shots.py` uses for the camera-pose grammar — though note that file uses its own
  private `_uu_to_deg` helper, not `rotation.uu_to_deg`, so it is an analogy rather than a call site
  to copy.

**The spiral's range check moves too.** `builders.spiral_staircase` currently validates in degrees and
names the flag in its error (`builders.py:373-375`: `"spiral staircase needs 0 < degrees_per_step <
180, got …"`). Left alone, `--angle-per-step 40000` would report a value the user never typed, in
units they never used, naming a flag that no longer exists — breaking both "errors name the offending
value" and the no-back-compat-cruft rule. So the **user-facing** range check moves to the CLI/dispatch
boundary as `0 < angle_per_step < 32768` UU, with a message naming `--angle-per-step` and the UU
value; the builder keeps its own check as an internal-API guard, reworded to name the *parameter*.

**The retrofit narrows the CLI surface ONLY — `builders.py`'s signatures are untouched.**
`cylinder`/`cone` keep `angle_offset: float` (degrees) and `spiral_staircase` keeps
`degrees_per_step: float`: those are accurate names for a degrees-based internal API, and
`tests/builder_parity_cases.py` calls them **by name** (`:87`, `:95`, `:100-101`) to produce golden
fixtures captured against the real editor. One of those calls is `cone(160, 96, sides=6,
angle_offset=25)` — 25° is *not* a half-segment for a hexagon, so it cannot be expressed as
`--align-to-side` at all. Renaming or removing the builder parameters would force a needless
editor re-bless of the parity goldens. *(Established while planning; see
[`plans/2026-07-25-brush-profile-generators-plan.md`](../plans/2026-07-25-brush-profile-generators-plan.md)
§0.)*

**No back-compat shims** (`CLAUDE.md`, `direction.md` "No back-compat cruft"): `--degrees-per-step` is
**deleted**, not aliased; the spiral default changes from `30.0` degrees to `8192` UU (45°) rather
than to `5461`, which is neither round nor exactly 30° (30° is `5461.33…` UU, so `5461` UU = 29.9945°).
The default *change* is a behaviour change to an existing verb, accepted by Andrzej (§11).

### 7.1 `--angle-offset` becomes the boolean `--align-to-side` (**D9**)

**What the flag was for** (nowhere documented until now): `builders.cylinder` puts vertex 0 at angle
0, on `+u`. For an 8-gon the *vertices* land on the axes and the *faces* straddle them, so an
octagonal pillar pushed against an axis-aligned wall meets it on a **corner**, leaving two thin wedge
gaps. Offsetting the cross-section by **half a segment** turns a face, not a vertex, toward the axis
so it sits flush.

**Decision: replace the free angle with a boolean `--align-to-side`,** which applies exactly that
half-segment offset (`180/sides` degrees — `22.5°` for an 8-gon). Reasons:

- **Every documented use is this one case.** `usage.md`, `leveldesign/general/brush-shapes.md`, and
  the `recipes/shapes/octagonal-column.md` recipe all describe `--angle-offset` solely as "sit a flat
  face on an axis". Nothing asks for an arbitrary angle.
- **An arbitrary offset duplicates `--rotate`.** Turning an n-gon to meet a wall at some *other*
  angle is whole-actor placement — `--rotate` is the right tool and already does it. The bool and
  `--rotate` then partition the space with no overlap.
- **It matches the engine.** `CylinderBuilder`'s own parameter is the **`AlignToSide`** checkbox
  (`kb/geometry-builders.md` §1) — same name, same semantics, so the mapping to UnrealEd stays 1:1.
- **It removes the units question for this flag entirely** — a bool has no units to get wrong, and it
  sidesteps the fact that a half-segment offset is not exactly representable in UU for most `--sides`
  (a 3-gon's 60° is `10922.67` UU).
- **It sharpens reverse-mapping.** For the `brush identify` work
  ([`specs/2026-07-24-corpus-brush-idioms.md`](2026-07-24-corpus-brush-idioms.md) §7 gaps 2+3), a real
  brush now classifies as *aligned or not* (a bool to recover), with any other cross-section rotation
  falling out as a `--rotate`.

*Rejected:* keeping the free angle in UU (`--angle-offset 4096`) — no documented need, and it
overlaps `--rotate`. *Rejected:* deleting the flag outright and telling authors to use `--rotate`
— it reintroduces exactly the pitch/yaw/roll guesswork the parked `--axis` item exists to remove
(for an X-built prism the equivalent is *roll*, not yaw), and it consumes the actor's single
`Rotation` field for an intent that is really about the shape, not its placement.

---

## 8. Out of scope (**D8**), and why

- **Taper / bevel / loft** — UED's *Extrude to Point* and *Extrude to Bevel*, where the far cap is a
  scaled copy of the near one. Deliberately excluded: a **trapezoid profile** already gives wedges,
  voussoirs and tapered blocks (the taper lives *in the profile plane*), and `brush clip` covers a
  single chamfer plane. The genuine residual is taper **along the sweep axis** — a frustum/loft, which
  neither extrude nor clip nor `brush build cone` (apex-only, no `CapHeight` truncation) can produce.
  That is a one-flag follow-up (`--taper S` scaling the far cap), not spec-sized. The p3
  `inbox.md` item asking for `cube --taper`/a wedge builder must be **re-scoped to that remnant** once
  extrude lands, not closed outright.
- **Profiles with holes** (an annulus in one brush) — in UE1 a hole is a subtracted brush, not a
  cap topology. Not a gap.
- **Sweep along an arbitrary path** — Tarquin's `Extruder` (a `PathPoints[]` sweep for pipes and
  curved tubes, `kb/geometry-builders.md` §2). A third verb, a much larger design; extrude + revolve
  are its two straight-line and circular special cases.
- **Revolve touching or crossing the pivot axis, and negative-`u` profiles** — §4.7's v1 limitations.
- **The pre-existing `cylinder`/`cone --sides` upper bound.** Those builders accept any `sides >= 3`
  with no cap (`builders.py:204`, `:227`), so `brush build cylinder --sides 24` emits a 24-vertex cap
  face today — the exact defect §6's tiling exists to prevent, but in existing code. §12 files it as a
  board item rather than widening this change.

---

## 9. Implementation shape

Where the code lands (`architecture.md`'s layer map is unchanged — these are ordinary generators):

- **`uedcli/profile.py` (new, small)** — the shared 2D layer, deliberately separate from `builders.py`
  so it is testable without any brush: `--point` token parsing, cleanup + validation (§5), signed area
  / winding normalization, the non-simple-profile test, and the convex decomposition (§6, the one
  non-trivial algorithm here). No world coordinates, no `Polygon`, no T3D.
- **`uedcli/builders.py`** — `extrude(points, depth, axis, …) -> Brush` and
  `revolve(points, angle_deg, segments, axis, …) -> Brush`, both returning a single `Brush` through
  the existing `_face` winding machinery and `make_brush_actor` wrapper. The `(u,v) → world`
  mapping of §2.2 and the
  per-verb outward directions of §5.7 live here as small helpers. Existing builder **signatures are
  unchanged** (§7): only `spiral_staircase`'s guard message is reworded.
- **`uedcli/cli.py`** — two new `bshape` subparsers, each `_common_build_opts(…)`; plus the §7 unit
  retrofit on `cylinder`/`cone`/`spiral`, and the `--at` help rewrite (§2.3).
- **`uedcli/dispatch.py`** — two new branches in `_build_brushes` (which returns a list; both verbs
  return a single-element one), the raw-value range checks of §5.6, the UU→degrees conversion of §7,
  and the two stderr advisories (§4.5, §4.6).

Nothing about naming, trunk writes, folders/labels, `--prop` validation, or the off-grid `--rotate`
warning changes: the existing `brush build` dispatch path already handles all of it for any shape.

**Build order:** extrude first (it exercises the whole shared spine — profile parsing, cleanup,
winding, cap tiling, the axis mapping — with a trivial sweep), then revolve on the settled spine
(adding the segment loop, the rotated outward directions, and the closed-turn case), then the §7
retrofit as its own commit so a units change never hides inside a feature.

---

## 10. Tests

Offline suite (`bin/test`), alongside the existing `test_generators.py`:

- **Shape correctness** — a square profile extruded along each of `x`/`y`/`z` produces the same solid
  as the equivalent `brush build cube`, compared over **vertex sets and outward normals only** (face
  order, anchoring and `ItemName`s all differ by design: `cube` tags every face `OUTSIDE`,
  `builders.py:196`). This is the strongest available oracle for the axis mapping and winding.
- **Winding, per verb (§5.7)** — `doctor` reports zero `watertight` findings (its backwards-wound-face
  branch) on: an extrude, and revolves at `--angle 16384`, `32768` and `65536`. The full-turn case is
  the one that catches un-rotated side-face hints.
- **The convex invariant (§6)** — a convex ≤16-vertex profile yields exactly 2 cap faces; a
  17-vertex convex profile and a concave L profile both yield >2, all convex, and `doctor`
  reports zero `convex`-category findings on the emitted actor.
- **The full turn is not degenerate (§7)** — `--angle 65536` emits a closed solid with no caps and a
  non-zero volume, proving the conversion did not wrap it to 0.
- **Anchoring (§2.3)** — the emitted vertices place profile `(0,0)` at `--at` on all three axes.
- **Winding-agnostic input** — the same profile given clockwise and counter-clockwise emits
  identical T3D.
- **Rejections** — each exits 2 with the offending value in the message and **no traceback**:
  malformed `--point` (one field, three fields, non-numeric), fewer than 3 points, zero points, a
  self-intersecting profile, a **pinched** profile (repeated vertex, non-adjacent edges touching at an
  endpoint), a zero-area profile, `--depth 0`, `--angle 0`, `--angle 65537`, `--segments 0`,
  `angle/segments >= 32768`, `--angle 65536 --segments 2`, and a revolve profile with any `u <= 0`
  (straddling, touching, or wholly negative).
- **Advisories (§4.5, §4.6)** — a solid off-grid revolve and a >64-face revolve each print to stderr
  while **stdout stays a clean T3D snippet**; a semisolid off-grid revolve prints no off-grid
  advisory.
- **Golden T3D** — one extrude and one revolve snippet committed as goldens, so face order,
  `ItemName`s (`Cap`/`Side<k>`) and the emitted coordinates cannot drift silently.
- **Unit retrofit (§7)** — `--angle-per-step 8192` on a spiral produces the geometry the old
  `--degrees-per-step 45` did; an out-of-range `--angle-per-step` errors naming *that* flag and the UU
  value; `--degrees-per-step` no longer exists as a flag.
- **`--align-to-side` (§7.1)** — on an 8-gon cylinder it produces exactly the geometry the old
  `--angle-offset 22.5` did; on a 6-gon it offsets by 30°, not a hardcoded 22.5°; without it the
  cross-section is unchanged; `--angle-offset` no longer exists as a flag.

---

## 11. Resolved defaults, and what to verify live

The three spec-author's calls below were put to Andrzej and **accepted as specced (2026-07-25)**:

1. **`--segments` default** (§4.2): `max(1, floor(angle/4096 + 0.5))` — one facet per 22.5°, so a 90°
   bend defaults to 4 segments, matching UED's own "16 pieces = 360°". *(Note that kb fact carries a
   **📖** marker — inferred from the binary string table, not measured — so the default rests on
   inferred semantics.)*
2. **The spiral default change** (§7): `--degrees-per-step 30.0` becomes `--angle-per-step 8192`
   (45°) — not `5461`, which is neither round nor exactly 30°. This changes existing spiral output.
3. **A poly-budget advisory** (§4.6): stderr, above 64 total faces.

**To verify live, once built** (each is currently an inference or an unevidenced claim; none blocks
the build):

- **Cap merge-back** (§6.1): materialize an L-profile extrude and count cap **surfaces** in the built
  map. Prediction: `bspMergeCoplanars` fuses tiles wherever each pairwise merge's inputs have vertex
  counts summing to ≤16 — so a 2-piece cap fuses, and a 3+-piece cap may fuse only partially. A
  by-product is whether `Engine.dll`'s `RemoveColinears` carries a convexity reject our port omits.
- **The full-turn torus** (§4.7): materialize a `--angle 65536` revolve and check the built map for
  holes. UE1's behaviour on a genus-1 brush is unevidenced; the fallback is two 180° revolves.

Per `CLAUDE.md` ("pin the finding, or it rots"), each answer lands as a **committed regression**
alongside the prose, not as a note.

---

## 12. Docs to update when this lands

Per `CLAUDE.md` (user-facing docs first, then the dev docs, then fold the spec's content into the
durable ones and delete the spec):

- **`docs/usage.md`** — the two verbs and every flag; the `(u,v)` axis table; the `--at` anchoring
  exception **and** the `--rotate`-pivot consequence (§2.3); the concave/`--native` caveat (§6); the
  off-grid-solid caveat (§4.5); the §7 unit change across `cylinder`/`cone`/`spiral`; the "thirds are
  not exact in UU" note (§7). Also its **"Pivots"** bullet (the second place the staircase-only `--at`
  exception is written down) and its **"Item labels"** bullet (which enumerates each shape's `Item`
  values — add `Cap`/`Side<k>`).
- **`cli.py`'s `--at` help** — rewrite to name all three exceptions: staircase (front-bottom corner),
  **spiral (base of the column axis — currently missing, a pre-existing staleness)**, extrude/revolve
  (profile `(0,0)`).
- **`docs/leveldesign/general/recipes/shapes/`** — recipes for the shapes this unlocks: L-ledge, arch
  voussoir, curved corridor (with the `--solidity semisolid` guidance of §4.5), moulded cornice; plus
  `octagonal-column.md`, which documents `--angle-offset` and must move to `--align-to-side`.
- **`docs/leveldesign/general/brush-shapes.md`** — the `--angle-offset` prose (two places) → the bool.
- **`docs/leveldesign/general/README.md`** line 18 — the six-shape list in the doc-index table.
- **`dev/docs/unrealed/leveldesign/kb/geometry-builders.md`** — the **intro** (which hardcodes the six
  shapes), §1's builder table (`AlignToSide` now maps 1:1 to a uedcli flag), §4 (curved geometry:
  Revolve now HAS a uedcli verb), and §7's verb-summary table.
- **`dev/docs/unrealed/leveldesign/kb/csg-bsp.md`** — §1's uedcli-verb line and §6's verb summary,
  both hardcoding the six shapes.
- **`builders.py:305-309` + the matching `architecture.md` paragraph** — the `staircase` docstring's
  stale claim that native *materialize* mis-classifies concave brushes (§6: it defaults to the
  `bspcsg` core, which does not). Fix in this change so the caveat is not stated two contradictory
  ways.
- **`dev/docs/architecture.md`** — the generator inventory and the `profile.py` module.
- **`dev/docs/decisions.md`** — the D1–D10 entries plus the review-refinements addendum; reconcile
  **`direction.md`**'s "Generator pattern" section, which lists the generator shapes.
- **`dev/docs/board/`** — close this item; re-scope the p3 taper item in `inbox.md` (§8); add
  follow-ups for the axis-touching revolve case, `--taper`, and the `cylinder`/`cone --sides > 16`
  cap defect (§8).
