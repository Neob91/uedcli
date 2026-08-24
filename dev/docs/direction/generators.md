# Generators — stateless T3D producers

## What we want

### What a generator is

A **generator** is a verb that computes a T3D snippet and writes it to **stdout**. It writes to no
tree — not the trunk, not a stash, not a prefab — and the caller decides the disposition:
`| actor add -` to land it in the level, `> shape.t3d` to keep it, `| brush intersect -` to feed
another generator.

The family is **`brush build <shape>`** (`cube`, `cylinder`, `cone`, `sheet`, `staircase`, `spiral`,
plus the swept-profile `extrude` and `revolve`), **`actor build <Package.Class>`** (fully qualified;
a bare name is rejected), and **`brush intersect` / `brush deintersect`**, whose shape comes from a
piped brush set rather than from parameters.

**Name allocation and the write into the trunk live exclusively at `actor add`** — the only consumer
holding both the target level and the incoming T3D at once. A generator emits a name *stem*
(`--base-name`, defaulting to the shape or class name); `actor add` appends the unique `_<rand>`
suffix. The flag is `--base-name`, not `--name`, because the value is never the final Name.

**"Stateless" means no level and no session — not "no project".** A generator validates that the
classes and textures it names exist on the composed search path, so it needs a resolvable project and
package path and exits 2 without one ([`conventions.md`](conventions.md), no fallbacks). It does not
need a level: it reads no tree, so **`--tree` is absent from every generator** — there is no box to
point at, and the race it would guard is downstream at `actor add`.

**Geometry is validated where geometry enters the trunk, not in the builder.** A generator checks
class and texture existence only; `validate_brush` runs at `actor add` and on the trunk-mutating
verbs, so the whole family behaves the same. Builders still refuse a degenerate face at build time,
because that is a bug in the builder's own arithmetic, not a property of the trunk.

### A generator creates the actor's authored identity

The generator — not `actor add` — sets everything about *what the actor is*: `--at`, `--base-name`,
`--csg`, `--solidity`, `--texture`, `--rotate`, `--prop`, `--mover-class`, and the organization
flags `--folder`/`--label` that [`organization.md`](organization.md) owns. `brush build sheet`
additionally takes `--flag <name>` to OR a poly flag onto its face at build time.

**`actor add` is a pure carrier-consumer**: no `--folder`/`--label`, no positioning flag. Its
`--order` stays, because a trunk-sequence position is an add-time concern, not authored spatial
identity.

**A dedicated flag has to earn its place.** `--csg`, `--solidity`, `--texture`, `--rotate` and
`--mover-class` each carry semantics beyond a raw property, so they stay. The engine `Group` is a
plain Name property with no abstraction on top, so it is set with `--prop Group=<name>`.

### One invocation, one brush — unless the shape is genuinely a set

`brush build <shape>` emits **one brush actor**, including for shapes whose silhouette is not convex.
The engine's polygon must be convex and holds at most 16 vertices, so a non-convex shape is realized
as a **non-convex BRUSH made of convex FACES**: the staircase tiles its side into strips, and
`extrude`/`revolve` tile each cap into convex pieces, adding only diagonals of the author's own
outline.

The **spiral staircase** is the one shape that is really a set — a central column plus one wedge
tread per step — because rotated wedges and a column overlap, and a per-brush convex list keeps every
piece valid on both the editor and the native paths.

**Accepted caveat:** the offline draft renderer `level preview --native` classifies solidity as
"behind every face plane", valid only for a convex solid, so it draws a concave notch **filled in**.
UnrealEd and the default `level preview --game` render it correctly. Stated in `--help` and the user
docs.

### `--at` anchors a different point per shape

| Shape | `--at` anchors |
|-----------------------------|---
| cube, cylinder, cone, sheet | the geometric centre on **every** axis, Z included |
| staircase | the front-bottom corner (min X/Y/Z) |
| spiral | the base of the column axis |
| extrude, revolve | the world point profile coordinate `(0,0)` lands on — for a revolve, the bend centre |
| intersect, deintersect | the `--origin` anchor; omitted keeps the carved position |

`--rotate` stores an absolute `Rotation` and never bakes it into the vertices, so it turns the brush
about that **same** local origin. A shape whose origin is not its centre therefore swings through an
arc instead of turning in place — correct, and stated in the docs.

### Swept 2D profiles: `extrude` and `revolve`

UnrealEd's 2D shape editor, as two generators sharing the profile grammar, orientation rule, anchor
rule, winding and cap generation, differing only in the sweep.

- **The profile is a repeatable `--point U,V`** — argument order = ring order, at least three
  points, the ring closed implicitly, either winding accepted.
- **`--axis x|y|z` (default `z`) names the axis the profile plane is NORMAL to**, equivalently the
  direction the sweep grows. `(u,v)` map onto the other two world axes in right-handed cyclic order,
  so one winding rule serves all three. Any future `cylinder`/`cone --axis` adopts this naming.
- **`extrude --depth`** sweeps `0..depth` along `+axis`. **`revolve --angle`** sweeps in flat facets,
  `--segments` many.
- **The revolve axis is fixed at `u = 0`.** There is **no `--pivot`**: distance from the axis is
  expressed in the profile coordinates themselves, so a profile drawn at `u ∈ [64,192]` revolves at
  radii 64 to 192. Every `u` must be positive — the sweep direction is fixed, so a negative-`u`
  profile would bulge toward `−axis` and invert the shared "grows toward `+axis`" model. Mirror the
  profile instead.

**Out of scope, deliberately:** taper along the sweep, profiles with holes (in UE1 a hole is a
subtracted brush), sweeping along an arbitrary path, and a revolve profile that touches or crosses
the axis.

**A revolve is off-grid by construction** — uedcli never snaps coordinates for the author. An
off-grid *solid* brush throws its BSP partition planes off-grid too, the primary cause of slivers and
holes, so uedcli emits a stderr advisory when a brush is both off-grid and solid, and the guidance is
`--solidity semisolid` for swept detail.

### Every builder angle is in unreal rotation units

One unit system end to end: the substrate speaks FRotator units (65536 = a full turn), so
**`--rotate`, `revolve --angle` and `spiral --angle-per-step` all take UU**, never degrees. Thirds
are not exactly representable — a 60° bend is `--angle 10923` (60.002°) — stated in the docs.

**A sweep MAGNITUDE is not an FRotator field.** Field parsing wraps mod 65536, which would turn a
closed full turn into a zero sweep; a magnitude is range-checked on the raw integer and converted
without any modulo.

**`cylinder`/`cone` take the boolean `--align-to-side`, not a free angle** — turning a FACE rather
than a vertex toward the axes, so an n-gon pillar sits flush against an axis-aligned wall. That is
UnrealEd's own `AlignToSide` checkbox. Any other cross-section orientation is `--rotate`. **This
narrows the CLI surface only:** the internal builder functions keep degrees-valued parameters,
because several editor-blessed parity goldens are captured through direct calls carrying offsets that
could not be expressed as `--align-to-side` at all.

### Movers are generator output too

**`--mover-class <Package.Class>`** turns any generator's result into a **base Mover** — base pose
only, no `CsgOper` — and `--csg`/`--solidity` are **rejected** with it rather than accepted as inert,
because a mover carries no CSG operation and its collision is the dynamic hash. The emitted name stem
is the mover class's bare name, so a subclass stays visible.

**Keyframes are never authored by a generator.** They live only in the trunk-editing `mover key`
family, so index bookkeeping has one owner and editing one key needs no rebuild.

### `brush intersect` / `brush deintersect` — the set merge

UnrealEd's `BRUSH FROM INTERSECTION` is `builder-brush ∩ world-solid`, needing a live red builder
brush and a surrounding carved room, neither of which exists in uedcli. The verbs are reframed onto an
**in-tree SET of brush actors against a uniform assumed background**, computed **natively — no
editor**:

- **`intersect`** — background **empty**. Additives make solid, subtractives carve it; the resulting
  solid's boundary is emitted as one welded brush.
- **`deintersect`** — background **solid**. The set's subtractives define voids and the **void is
  emitted as a solid** — the plug that exactly fills a carved doorway, which is the door-mover flow.

**They take a T3D brush set, not a name list.** The positional is `-` for a snippet on stdin (or a
saved FILE) — the `build → add -` convention. Every tier feeds them through its own `show` verb, so
there are **no `stash`/`prefab` intersect wrappers**. **Stdin order IS CSG order** and is never
re-sorted. A non-brush actor or a Mover in the set is **refused, exit 2, naming it** — not skipped.

Two verb-specific defaults and one added pair: **`--at` defaults to keeping the carved position**;
**`--solidity` defaults to the faithful per-face rule** (a face keeps the solidity of the additive it
came from; a face from a subtractive is forced solid, because the engine forbids a semisolid subtract
wall); **`--origin center|min|max|keep|X,Y,Z` re-centres the result so it is relocatable**, and
**`--pivot`** writes `PrePivot`, the hinge a swinging mover rotates about.

**A disjoint result stays ONE actor** plus a component-count note on stderr. Someone who wants
independently mover-izable pieces runs the verb once per subset.

## Rejected

**The pattern**

- **Shape verbs that add straight to the model** — the brush is already placed, with no way to
  inspect, redirect or compose it.
- **Putting the shape flags on `actor add`** — the generator must emit a T3D ready for *any*
  disposition, including one that never reaches `actor add`.
- **`--folder`/`--label` on BOTH the generators and `actor add`** — two setters plus a precedence
  rule.
- **Converting only `brush build` and leaving `actor build` behind** — a half-converted family.
- **A positioning flag on `actor add`** — breaks the pure-consumer model.
- **`--group` as a dedicated `brush build` flag** — a plain Name property, redundant with
  `--prop Group=`.
- **`--tree`/`--target` on a generator** — inert: a generator reads no box.
- **Validating class/texture existence only at the write boundaries** — the generators are checked
  too, accepting that this makes them project-dependent.
- **Geometry validation inside the two profile builders as a deliberate exception** — two verbs
  validating while four do not is the family inconsistency the conventions exist to prevent, and the
  premise behind it was false.
- **Applying geometry validation family-wide instead** — defensible, but a behaviour change to four
  existing verbs has no business riding inside a new-feature build.
- **`--name` for the name stem** — the stored Name is always `<value>_<rand>`, so "name" implied a
  literal final Name it never was. `--name-prefix` is also wrong (the random part is a suffix), and a
  hidden `--name` alias was not kept.

**Shape and decomposition**

- **One brush actor per step** for the staircase — one actor per shape; the doctor noise that
  decomposition avoided is fixed at the validator instead.
- **A single non-convex stepped side FACE**, untiled — a non-convex polygon is a genuine CSG defect.
- **Suppressing the watertight check on builder-tagged brushes** — a provenance marker instead of a
  principled fix that also helps hand-authored geometry.
- **A single non-convex brush carrying the whole spiral** — rotated wedges and the column overlap.
- **Curved (arc) inner and outer tread edges** — straight chords keep each footprint a trivially
  valid convex trapezoid.
- **Splitting a concave profile into several convex brushes** — correct in every tier, but N actors
  per sweep and internal seams through the solid.
- **Rejecting concave profiles outright** — arches and L-profiles are most of why the gap was raised.
- **The first tread at floor level** — you climb one riser onto step 0.

**Profiles**

- **Speccing `extrude` first and `revolve` later** — the shared grammar would have been settled twice
  and drifted.
- **A single `--profile "u,v u,v …"` string** — quoting-sensitive and invisible in `--help`.
- **A point list on stdin via `-`** — a third stdin convention.
- **`--plane xy|xz|yz`** — for a swept solid the natural parameter is the sweep direction.
- **XY-only in v1** — reproduces the axis-guessing that `--axis` exists to kill.
- **Anchoring `--at` at the geometric centre** — discards the authored 2D coordinate system, which is
  the whole point of a profile.
- **Anchoring on the profile's FIRST point** — re-ordering the ring would silently move the brush,
  and a revolve has no meaningful first point.
- **A scalar `revolve --pivot U`** — redundant once the axis is the `v` axis.
- **A free in-plane axis** — two flags, a redundant coordinate, and a general point-line side test,
  for shapes reachable by rotating the authored points.
- **Taper/bevel/loft in scope** — a trapezoid profile already yields wedges and voussoirs.

**Units**

- **Keeping degrees** on the authoring flags — the substrate speaks FRotator units end to end, so
  degrees forced a mental unit switch.
- **"UU divides better than degrees"** as a rationale — false, and dropped: only power-of-two counts
  divide exactly in UU, while every threefold division is exact in degrees. The decision stands on
  unit consistency alone.
- **Keeping `--angle-offset` as a free angle** — no documented use beyond the half-segment case, and
  it overlaps `--rotate`.
- **Deleting it and using `--rotate`** — reintroduces pitch/yaw/roll guesswork and spends the actor's
  single `Rotation` field on a shape concern.
- **Renaming the internal builder parameters to match the CLI** — would force an editor re-bless of
  parity goldens for zero user-visible gain.

**Movers and the set merge**

- **Baking keyframes on the generator** — duplicated index bookkeeping and a full rebuild to edit one
  key.
- **Accepting `--solidity` on a mover as inert** — a silent no-op.
- **A shape-derived or hardcoded mover name stem** — the first is opaque, the second loses the
  subclass.
- **The literal editor `builder ∩ world` model** — needs a room and a stateful builder brush.
- **Listing brush names on the CLI** — unwieldy and produces nothing reusable.
- **An `--out-stash <id>` flag** — the pipe handles every disposition uniformly.
- **Keeping `stash intersect`/`prefab intersect` wrappers** — redundant once every tier can pipe its
  own `show`.
- **Strip-ALL-flags as the default** (loses authored additive solidity) and **preserve-ALL** (keeps
  impossible semisolid subtract walls).
- **Keeping the faithful `Location=0` world-vertex form as the default** — movable only by a
  hand-computed offset, and a mover would pivot at the world origin.
- **A `--prepivot` alias beside `--pivot`** — offline there is one field.
- **`--split` into connected components** — dropped entirely; run the verb per subset.
- **Warn-and-skip a non-brush or Mover in the piped set** — a merge quietly missing a brush hands
  back a T3D the caller reads as complete.

## Refs

[`organization.md`](organization.md) · [`conventions.md`](conventions.md) ·
`../architecture.md` "Builders (`builders.py`)" · `../unrealed/leveldesign/kb/geometry-builders.md` ·
`../unrealed/leveldesign/kb/csg-bsp.md` · `../unrealed/quirks.md` ·
`../spikes/2026-06-25-mover-keyframe-basepos-semantics.md`
