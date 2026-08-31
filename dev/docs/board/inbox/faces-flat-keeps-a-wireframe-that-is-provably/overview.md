+++
priority = "p1"
kind = "owner-question"
summary = "RULED + DONE: --faces flat's invisible wireframe — edges take the other member of the pair"
+++

# RULED and IMPLEMENTED: `--faces flat` drew a wireframe that was provably invisible

> Migrated to `four-actor-preview-faces-rulings-need-a-durable`'s
> `questions/flat-edge-colour-uses-partner-member.md`. Kept here because this slug is cited from
> `architecture.md`.

**RULED by the owner: take the proposed fix — under `flat` only, each surviving face's edges draw in
the OTHER member of its brush's colour pair. Implemented in S2 of `actor diagram --faces` (board item
`four-actor-preview-faces-rulings-need-a-durable`), with the final choice confirmed from real renders
rather than reasoning, the treatment decision 2.12 set for the `--focus` dim constant.**

Kept (not deleted) because it is the only record of why `flat`'s colour roles are assigned the way they
are, and of the second observable a cold review round then found underneath the same root cause.

## The defect

Two rulings in that spec are individually fine and jointly empty:

- **§4.5** — a `flat` fill is *"the `(front, back)` pair the wireframe already uses, chosen by
  `_is_front`"*, unshaded.
- **§4.6 / decision 2.5** — `flat` **KEEPS** its wireframe, and *"an edge draws iff its face survived
  the cull and that face is front-facing for its own brush's cull sense."*

Combine them and **every drawn edge is painted in exactly its own face's fill colour**, so no edge is
ever visible on its own brush:

| brush        | faces the edge rule keeps | that face's fill | edge colour drawn | visible? |
|--------------|---------------------------|------------------|-------------------|---|
| non-subtract | its `_is_front` faces     | `front_rgb`      | `front_rgb`       | no |
| subtract     | its FAR (non-front) faces | `back_rgb`       | `back_rgb`        | no |

The only edge that can show is a REAR brush's edge over a NEARER brush's fill (there is no depth test
on the edge pass), which §4.6 already treats as an incidental.

## Measured

`actor diagram Room Pillar Crate --faces flat --annotate none --layout single --view iso --size 700`
on a subtracted 1024×1024×384 room with an added pillar and crate inside it. The whole 700×700 image
contains **exactly three colours**: `(224,224,224)` background, `(205,180,110)` subtract-back,
`(0,0,200)` add-front. Zero edge pixels. The render is two flat silhouettes — a gold hexagon and a
blue L — with no interior creases on the room and **no boundary at all between the abutting Pillar and
Crate**.

That is the very failure decision 2.5 was written to prevent: it names *"under `textured` two abutting
brushes sharing a texture are indistinguishable and the CSG cue is absent"* as `textured`'s accepted
cost, and keeps `flat`'s wireframe so `flat` does not have it. As specified, `flat` has it too.

## The fix, as ruled and implemented

Under `flat` only, each surviving face's edges draw in the **other** member of its brush's colour pair —
a non-subtract's `_is_front` edges in `back_rgb`, a subtract's far edges in `front_rgb`. One line in
`_scene_geometry`, no new constant and no new palette entry; the CSG hue (the cue §4.5 protects) is
preserved because both members carry the same hue. `wire` is untouched, so S2's committed golden holds.

**Chosen from four real renders of the same scene and view**, not from reasoning:

| variant | what | verdict |
|---------|------|---------|
| a       | as originally specified                     | unusable — 3 colours, two flat silhouettes, no crease and no brush boundary |
| **b**   | **the other member of the pair (RULED)**    | **taken.** The room reads as a three-walled interior; the two abutting adds separate; every edge keeps its brush's hue |
| c       | a fixed dark outline for filled faces       | highest contrast, but the edge hue stops carrying the CSG cue, and on the legacy `color_by_csg=False` path (black fill) a black outline is invisible — it needs a second rule |
| d       | edge untouched, fill `_fade`d instead       | reads well, but moves the FILL off §4.5's exact palette value, which is the one thing §4.5 protects (the legend is matched against it) |

Only b is committed. c and d were throwaway local experiments and no code from them remains.

## A SECOND observable of the same root cause, found by cold review and fixed with it

`--highlight` was invisible under `flat` on every non-subtract brush, for the same reason one layer
down: `vivid` is the pair's front member, and a surviving non-subtract face fills with that same member,
so the highlight outline painted in exactly the fill beneath it. Measured on a 256³ add cube at
`--view iso --size 200`: one highlighted face changed **138 of 40,000 px** and the render had **2 distinct
colours**; highlighting all six changed the same 138 px. Every one of them was the `weight=2` stroke
thickening the silhouette against `BG` — inside the brush there was nothing. Worse under
`--brush-colors legend`, where `vivid` IS the tint IS the fill.

Fixed by the same ruling, extended one step: a filled render has **three** roles (fill, ordinary edge,
highlight outline) and **one two-member pair**, so a highlighted face **inverts** — fill takes the
partner member, outline takes its own. That separates it from its own fill AND from every neighbour's
partner-coloured edge, with no third colour invented and the hue still intact. Now >1,000 px change.

## Also standing from S2, RESOLVED by the review round

**`--layout breakdown` under `flat` used to refuse a `--focus` it ignores.** The refusal is now scoped
off `breakdown`, where `--focus` is documented as validated-but-ignored (that layout sets its own focus
per pane), so a flag that cannot reach the output no longer turns a working render into an error. It
still refuses under `single`/`quad`, where it does reach the output. S3 removes the refusal entirely.

## The mirror refusal that used to sit beside this — ALSO RULED, and gone

Owner ruling, verbatim: **"Mirrored brushes SHOULD WORK CORRECTLY."** So `flat`'s exit-2 on a mirrored
brush is DELETED — not narrowed, not reworded — along with its test and every doc and `help=` claim that
it existed, including the "un-mirror the brush" advice (which proposed a destructive edit to the user's
level as the remedy for a viewer limitation).

**Why it is one line.** A reflection reverses every ring's handedness, so a transformed face's Newell
normal comes out as the NEGATIVE of its true outward normal and `_is_front` answers the opposite of the
truth for every face of that brush — measured on a subtract cube under `MainScale.X=-1`: the wall that
lands at x=+256 carries a computed normal of −X. The cull, the three colour roles above, the `flat` edge
rule and `occluders` are ALL expressed in terms of that one boolean, so correcting the boolean
(`_is_front_corrected`) fixes all four at once. An EVEN number of negative axes is a 180° rotation,
determinant +1, and is deliberately untouched.

Before/after on a mirrored subtracted room with an added pillar and crate inside: **before** it filled as
a solid gold box hiding both adds entirely (the cull kept its NEAR faces); **after** it is
indistinguishable in quality from the unmirrored render — three-walled interior, both adds opaque and
correctly occluded. Verified by eye, and the on-face digits are NOT mirror-imaged (`_face_decal_basis`
fixes `Uw`'s sign from the screen projection, which survives a reflection; now pinned).

**The coverage gap the refusal was hiding is now closed.** `uedcli/tests/fixtures/level_small.t3d` — this
repo's own real 13-brush editor export, and the source of the `wire` goldens — carries three mirrored
brushes (`Brush2` `MainScale.X=-1` subtract; `Brush8`/`Brush10` `Scale.Y=-1` adds), so it refused
outright and NOTHING in the suite rendered a filled view over real editor content. It now has a committed
`flat` golden (`preview_flat_golden_iso.png`), which does catch the uncorrected mirror.

**`wire` is deliberately left uncorrected** — the ruling was about the filled modes, `wire` culls nothing
so the inversion costs it only the front/back shade, and correcting it would change the bytes of the
byte-identity golden. Parked separately as
`board/inbox/wire-renders-a-mirrored-brush-with-its-front`.

## Third and final ruling on the edge pass — DROP the front-facing condition

Owner ruling: **draw edges on any FILLED face.** `draw_edge` becomes "is this face filled", not "is it
filled and front-facing for its brush's cull sense". Rationale: it makes the edge ruling's goal — an
outline is always visible — hold unconditionally with no new machinery. A "is this brush closed?"
predicate to scope it to single-sided brushes was rejected as real new machinery for one case.

**What it fixed.** A back-facing SINGLE-SIDED face had a fill and no cover: two abutting `nonsolid` sheets
wound away from the camera rendered as one undifferentiated 17,672-px block with **zero** edge pixels and
no boundary between the two brushes — the same symptom the first edge ruling was made to eliminate,
surviving in the one case a facing test cannot reach. Now 657 px of outline.

**What it costs, measured** — the ruling's accepted "redundant edge draws" is very nearly right, with one
residue worth recording: on a closed brush the extra edges are invisible BY COLOUR (a cube is
byte-identical, hidden far-corner edges and all), but on faceted/stepped geometry or where two brushes
abut, a silhouette gains ≤1 px in its own hue — 5 px on a cylinder, 15 px on a staircase, 55 px (0.084 %)
in the `level_small.t3d` flat golden, which was re-blessed for it deliberately. Full numbers and the
fill-vs-Bresenham coverage mismatch behind them:
`board/inbox/filled-edges-on-every-face-extend-a-faceted`.

**This supersedes spec §4.6's front-facing condition**, which will still read otherwise until the spec is
deleted at S5.
