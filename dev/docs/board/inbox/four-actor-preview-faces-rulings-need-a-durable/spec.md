# Spec: textured faces for `actor preview` (`--faces wire|flat|textured`)

**Status:** spec review complete — both rounds run, **gate at its ceiling** (`CLAUDE.md` "Review
gates"). No structural finding in either round. Everything found is fixed below, logged, or escalated;
**nothing is escalated and nothing blocks** — §14 records the two former escalations, both resolved.
The only gate is the build-order dependency in §12.
**DEPENDS ON** the on-deck texture-decoder work — see §12. Build order is fixed: that item first
(with the §12 accessor folded into its scope), then all of this.
**Requested by:** the owner, 2026-07-26, session `uedcli:preview-textured`.
**Ephemeral:** scratch, per `CLAUDE.md`. On build, fold the outcome into
[`architecture.md`](../../../architecture.md) "Preview internals", [`docs/usage.md`](../../../../../docs/usage.md)
and [`docs/leveldesign/general/textures-and-surfaces.md`](../../../../../docs/leveldesign/general/textures-and-surfaces.md),
record the agent-side choices in the `rationale/` tree under a **new preview topic** (that tree
currently holds `cli.md`, `emit.md`, `reported-coordinates.md`, `surface.md`, `MIGRATION.md`, `README.md` — the file is created by this
build, so it is deliberately not cited as a path yet), and delete this file.

---

## 0. What this is, and what it is not

`actor preview` renders an **orthographic schematic** of a set of actors — model-side, host-only, no
editor and no container. Today it draws **wireframe only**. This spec adds two solid-face modes, one
of which samples each face's **real texture** through the face's own authored UV frame.

**Not** a Rust port (§10); **not** a replacement for `level preview --native` (that stays the
perspective, whole-level, post-CSG tier); **not** lighting. The native extension stays optional —
nothing here may make `actor preview` fail on a machine without `cargo`.

**One property IS given up, deliberately (decision 2.13).** `actor preview` today needs no game
install for a brush-only render. `--faces flat` and `--faces textured` **do** — they load the class
hierarchy to tell a mover from a real subtraction (§4.7), and `textured` additionally needs the
textures the scene references. **`--faces wire`, the default, is unchanged and still needs nothing.**

**Why it is worth building.** Every texture-frame defect in
[`spikes/levelbuild-friction/agent-reports.md`](../../../spikes/levelbuild-friction/agent-reports.md) —
mirrored lettering, the half-shifted sheet, the wrapped door trim, the cut-out texture on a solid
face — was **invisible in `actor preview`** and cost a full materialize + render cycle to see. Those
faults are properties of the *authored* UV frame, which this tier reads directly.

## 1. The governing constraint

`preview.py` is **stdlib-only** (no PIL/numpy) and **resolver-free** — `dispatch.py` resolves and
decodes, `preview.py` receives decoded pixels and draws ([`architecture.md`](../../../architecture.md)
"Preview internals"). The seam already carries texture pixels: point sprites resolve in
`dispatch._preview_render_data()` and reach `preview._blit` as `(w, h, rgb, mask)`. Textured faces
extend that same channel (§6).

## 2. Decisions (the owner's, 2026-07-26)

1. **`--faces {wire,flat,textured}`, default `wire`.** *Rejected: a boolean `--textured`* — no room
   for `flat` without a second flag later, and "No back-compat cruft" makes reshaping a hard break.
2. **A textured face is shaded as `level preview --native` shades it** (§4.1). *Rejected:
   unlit/full-bright.* Every divergence is enumerated in §4.9 — nothing diverges by accident.
3. **Cut-outs are honoured, but ONLY on a genuinely masked face** (§4.3a). *Rejected: masking every
   index-0 texel unconditionally* — the spike measured **464 of 2,669** corpus textures using index 0
   while unmasked, including flat swatches at 100 % that would have rendered as nothing at all;
   *rejected: rendering masked opaque like `--native`.*
4. **All layouts accept `--faces`, no size guard, no cost ceiling** — **re-put and re-affirmed a
   third time, 2026-07-26, on an accurate cost picture.** The two earlier affirmations each rested on
   a wrong statement of mine: first pane arithmetic that was 4× off, then a claim that mip selection
   bounded per-pixel work. It does not — under nearest-neighbour sampling there is exactly one texel
   fetch per covered pixel at every mip level, so mip choice controls **aliasing only** and there is
   no cost-control mechanism at all. Ruling stands on that basis. *Rejected: a stderr cost estimate
   past a pixel-count threshold; rejected: refusing `textured` under `breakdown`.*
5. **`textured` draws NO wireframe; `flat` KEEPS its wireframe** (§4.6). Accepted consequence: under
   `textured` two abutting brushes sharing a texture are indistinguishable and the CSG cue is absent.
6. **Any texture the render NEEDS and cannot get is a clean exit 2 naming the cause** (§8) — and
   "needs" is literal (owner ruling, 2026-07-26): the scene's texture refs are collected first, and a
   scene referencing none renders fine with no texture source at all. *Rejected: refusing whenever no
   resolver exists regardless of what the scene contains* — I had derived that rather than asking, and
   it would have blocked previewing a freshly generated brush. *Rejected: checkerboarding; rejected:
   silently falling back to `flat`.*
7. **`--brush-colors` with `--faces textured` is a clean exit 2** — re-affirmed after its original
   rationale ("it would do nothing") was **refuted**: `preview._scene_geometry` derives `vivid`, the
   `--highlight` colour, from it. It stands on the corrected ground that the flag's documented job is
   the wireframe, and repurposing it under one mode would give one flag two jobs.
8. **`level preview` is NOT changed** — it keeps `--native`/`--game` (which *backend*).
9. **The Rust port and a non-optional native extension are DEFERRED** (§10).
10. **A subtract brush's faces render ONLY from inside the subtracted volume** (§4.7) — *"the
    subtract's polys looked at from OUTSIDE do not render in UnrealEd or in game, and they should not
    render here"* (owner). Under an always-outside ortho camera: **cull a subtract's camera-facing
    polys, draw its far ones.**
11. **Build order: the texture-decoder item FIRST, with this spec's mip accessor folded into its
    scope; then all of this** (§12). *Rejected: shipping `wire`/`flat` first and `textured` later;
    rejected: waiting for that item without folding the accessor in; rejected: building now against
    today's decoder and reworking.*
12. **`--focus` context dimming is strengthened and VERIFIED BY RENDER, not by arithmetic** (§4.8).
13. **`flat` and `textured` LOAD THE CLASS HIERARCHY to identify movers** (§4.7) — so the §4.7 cull
    applies to real subtractions and never to a mover, which is never carved into the world.
    **Accepted cost, stated plainly: those two modes lose the "works with no game install" property.**
    `--faces wire`, the default, keeps it entirely. *Rejected: culling on the raw `CsgOper` marker*
    (simple and index-free, but a door or breakable carrying that marker renders inside-out);
    *rejected: using the hierarchy only when it happens to be reachable* (the same command would draw
    two different pictures depending on the environment — the silent inconsistency `conventions.md`
    rejects); *rejected: dropping the cull* (a subtracted room would render as a solid box hiding
    everything inside it, which is what makes the filled view useful).

## 3. CLI surface

One option, on `actor preview`, `stash preview` and `prefab preview` — they share
**`cli._preview_opts`** (`cli.py:686, 1476, 1513`).

```
--faces {wire,flat,textured}
```

**`help=`:**

> how brush faces are drawn (default `wire`). `wire` = outlines only, the schematic. `flat` = each
> face filled solid in its brush's CSG hue, wireframe kept — a diagram of what occludes what.
> `textured` = each face filled by sampling its OWN texture through its authored UV frame
> (`Origin`/`TextureU`/`TextureV`/`Pan`), with NO wireframe, so alignment, panning, mirroring and
> tiling are visible offline — no editor, no container, no lighting. Under BOTH `flat` and
> `textured` a subtract brush shows only its far (interior) faces, so geometry inside a subtracted
> room stays visible. **`flat` and `textured` both load the game's class hierarchy** (to tell a mover
> from a real subtraction), so unlike `wire` they need the game content available, and both reject a
> **mirrored** brush (a negative scale axis flips which way its faces point, which would invert that
> subtract rule). `textured` additionally rejects `--brush-colors` and any scaled or sheared brush,
> and needs every texture the scene actually references to be readable.

**Three existing `help=` strings are corrected in the same change** (`CLAUDE.md`: help must say what
a flag actually does):

- `--brush-colors` (`cli.py:155`) — says "how to colour **the wireframe**"; it also drives `flat`
  fills and is a hard error under `textured`.
- `--focus` (`cli.py:190`) — says other brushes "recede to a faint (dimmed) **wireframe**"; under
  `flat`/`textured` they recede as dimmed *fills*.
- `--show` (`cli.py:199-205`) — its tail says *"Brush actors (incl. movers) are excluded — their
  preview stays **schema-free (no class lookup)**"*. Under `flat`/`textured` the brush preview now
  DOES do a class lookup (decision 2.13), so that clause must be scoped to `wire`. Its overlays
  themselves are unaffected; the ordering guarantee is also now explicit (§4.10).

## 4. The shape of a face — exact

### 4.1 Per-face shade (`textured` only)

| Quantity   | Definition
|------------|---
| `N`        | Newell normal over the face's **world** vertices — NOT the stored `Normal`, per `t3d.md` "Winding defines the face, not `Normal`"
| `L`        | key light `(-0.408, -0.577, 0.707)`, **un-normalized** (`|L|` = 0.99962)
| `shade`    | `0.55 + 0.45 * abs(dot(N, L)) / length(N)`
| skipped    | a face with **fewer than 3 vertices** (matching `render.rs:141-143`), or `length(N) <= 1e-12`

Compute in Python `float` (f64); convert with **truncation**, `min(int(c * shade), 255)`, matching
`render.rs`'s `(c * shade).min(255.0) as u8`. `render.rs` is f32, so byte-identity with `--native` is
**not** claimed (§4.9 #3).

### 4.2 Per-vertex UV

From **`texframe.world_uv_frame(actor, poly)`** (§6): `base_w = Location + R·(Origin − PrePivot)`,
`tu_w = R·TextureU`, `tv_w = R·TextureV`, and per vertex `P`:

```
u = dot(P − base_w, tu_w) + pan[0]        v = dot(P − base_w, tv_w) + pan[1]
```

per `t3d.md` "The UV convention" (✅, pinned by
`test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`). **Texel scale lives in the
MAGNITUDE of `TextureU`/`TextureV`** — a unit axis is 1 texel per world unit.

**Zero/missing axis fallback:** `_tex_basis_default` is fed `poly.normal` when present, Newell
otherwise — the *existing* `_world_uv_frame` behaviour, preserved verbatim so the two renderers
cannot drift. A deliberate exception to §4.1's Newell rule, scoped to the fallback basis only; it
never affects `shade`.

**Interpolation is AFFINE and exactly so** under ortho — `render.rs`'s per-pixel perspective divide
is not needed.

**Scaled OR SHEARED brushes are REJECTED under `textured` ONLY** — clean exit 2 naming the
actor and which of `MainScale` / `PostScale` / `SheerRate` is non-identity. `preview._scene_geometry`
builds vertices with `rotation.actor_linear` (`PostScale·R·MainScale`, and `transform.fscale_matrix`
folds sheer in) while the UV frame uses `rotation.actor_matrix` (**rotation only**) — so such a brush
would render transformed geometry against an untransformed texture frame.
`preview_native._reject_scaled` rejects the same fields.

**`flat` rejects ONLY the mirrored case, not scale in general.** The argument above is entirely about
the *UV frame*, and `flat` reads no UV frame — its fill is the projected polygon, which `actor_linear`
already builds correctly and which `wire` renders correctly today. **But a negative-determinant
(mirroring) transform inverts `_is_front`, which §4.7's subtract cull depends on**, so `flat` refuses
that one case and renders every other scaled or sheared brush normally — §4.7 has the predicate. An earlier draft rejected under both modes, costing the whole level's
`--faces flat` for one scaled brush, for a reason that does not apply to it.

*Rejected: transforming UV axes by the inverse-transpose* — UE1's actual treatment is unverified and
guessing it would put a wrong answer in the one tool meant to be authoritative about UV. Supporting
them is a follow-up (§10). **`wire` and `flat` render them exactly as today** — a behavioural
difference from `--native`, which rejects in every mode (§4.9 #7).

### 4.3 Per-pixel texel fetch (`textured`)

```
tx = floor(u / 2**level) % mip_w        # u is in MIP-0 texel units — the /2**level is REQUIRED
ty = floor(v / 2**level) % mip_h        # Python % on ints == Rust rem_euclid for positive divisors
texel = rgb[(ty * mip_w + tx) * 3 : ... + 3]
```

The `/ 2**level` is load-bearing: `u` is in mip-0 units, so taking it modulo a level-`L` width tiles
the texture `2^L` times instead of scaling it down.

Nearest-neighbour, no bilinear. **A non-finite `u`/`v` is a clean exit 2 naming the actor and poly —
not a silent fallback.** `floor(nan)` raises `ValueError` and `floor(±inf)` raises **`OverflowError`**,
so the frame is checked with `math.isfinite` before any pixel is drawn. Rendering such a face as
`DEFAULT_GREY` would make a *corrupt authored frame* pixel-identical to the legitimate "no `Texture`
set" case two rows below — a half-answer that looks like a full one, which `conventions.md` puts under
**Rejected** ("No fallbacks, anywhere"). Avoiding the traceback is only half that rule; the other half
is refusing.

| Case                                     | Result
|------------------------------------------|---
| face is masked (§4.3a) and `mask[…] == 0` | **pixel not written, and depth NOT written** — a face behind shows through
| face is NOT masked                       | index 0 is an ordinary colour and draws normally
| poly has no `Texture`                    | `DEFAULT_GREY = (128,128,128) × shade` — matches `render.rs`'s `tex_index < 0` path. Normal, not an error
| the texture cannot be read               | **exit 2 before rendering** (§8) — no checkerboard, no partial image

#### 4.3a Is this face masked?

```
flags  = (poly.flags or 0) | poly_flags_int(actor.props)   # the engine ORs the ACTOR's PolyFlags in
masked = bool(flags & 0x2) or decoded[ref].b_masked        # b_masked rides the decoder's typed result
```

**The actor-level `PolyFlags` OR is required**, not optional: `preview_native.build_scene` does
exactly this (`flags = (poly.flags or 0) | _poly_flags_int(dict(actor.props))`,
`preview_native.py:382`) and `preview.classify_brush` already reads actor-level flags for
semisolid/nonsolid. Omitting it would leave a brush authored `PolyFlags=2` masking in the engine and
in `--native` but opaque here — re-hiding "cut-out texture on a solid face", one of the four defects
§0 exists to expose.

**Two mechanical points, both round-1 findings.** (a) The existing spelling is
`preview_native._poly_flags_int(dict(actor.props))`, whose real call site guards `if actor else 0` for
the `actor is None` join case. It moves to `texframe` with the UV helpers rather than being imported
from `preview_native` — `preview.py` importing that module would pull in `TextureResolver` and break
§1's resolver-free invariant. (b) There is **no separate `texture_has_bMasked(ref)` predicate**: the
decoder's typed result already carries the flag, so the gate reads it off the result it already has. A
second entry point would be a second way to ask one question — against the "one texture-API change,
not two" argument that justified folding this in — and a bool-returning predicate would violate
`conventions.md` "a predicate answers or it RAISES; 'don't know' is never returned as `False`".

`PF_Masked = 0x2` (`query.PF_NAMES`); `bMasked` is a UE1 bool written **presence-only**, so present ⇒
masked (spike
[`2026-07-26-texture-masked-property/findings.md`](../../../spikes/2026-07-26-texture-masked-property/findings.md);
`quirks.md` "Surfaces / polys"). Delivered by §12's accessor.

### 4.4 Mip selection (`textured`)

```
# PER FACE, from the affine solve §6 already computes for this face:
texels_per_px = max(hypot(du_dx, du_dy), hypot(dv_dx, dv_dy))   # screen-space UV gradients
level         = clamp(floor(log2(max(texels_per_px, 1.0))), 0, len(mips) - 1)
```

**The quantity is PER FACE, and it is already in hand.** Two earlier drafts tried to derive it from a
view-global projection gain — first the larger singular value of the iso map, then the smaller. Both
are wrong, because what a mip pick needs is the least screen gain *within the face's own plane*, which
a view-global number cannot see. Worked example at the **default** `--iso-angle 30`, where the
view-global values coincide at 1.2247 and the question looks moot: a wall with normal +X has in-plane
basis mapping `Y→(−cos r, sin r)`, `Z→(0, 1)`, whose singular values are 1.2247 and **0.7071** — so
the view-global figure understates texels/px by 1.73×, about 0.8 of a mip level too sharp, on the most
common face orientation. For a near-edge-on face the error is unbounded.

§6's affine solve already produces `∂u/∂x, ∂u/∂y, ∂v/∂x, ∂v/∂y` for this face in order to interpolate
UV, so the correct quantity costs nothing extra and needs no projection special-casing — `top`,
`front`, `side` and `iso` all fall out of the same gradients. (`preview._draw_sphere:1843`'s
`max(√2·cos r, √(2 sin²r + 1))` is a *silhouette radius*, a different question that merely shares a
formula shape — do not "unify" them.)

**Mip choice is NOT a cost control.** Under nearest-neighbour sampling (§4.3) there is exactly one
texel fetch per covered pixel at every level, so it changes *which* bytes are read, never how many.
It is purely an image-quality control. `decode_texture` already decodes all mips and `mip0_to_rgb` is
generic over any `Mip`.

### 4.5 `flat` mode

Fill is the `(front, back)` pair the wireframe already uses, chosen by `_is_front`:

- `--brush-colors csg` (default) → `_CSG_PALETTE[classify_brush(actor)]`
- `--brush-colors legend` → `(tint, _fade(tint))` from `assign_tints`, matching `_scene_geometry`
- the **legacy `color_by_csg=False` path** (`render_brushes_pgm`'s default, used by unit tests) →
  the same `(FRONT, BACK)` black/grey pair that path already uses for edges. *(Mechanically,
  `_scene_geometry` evaluates `_CSG_PALETTE[...]` unconditionally at `preview.py:1464-1467` and then
  discards it on this branch — the colours are as stated, the palette lookup is not skipped.)*

**No key-light shade** — multiplying the hue would break the "this exact blue means additive" cue the
legend is matched against. Accepted consequence: a subtract brush can only ever show its **back**
colour, since decision 2.10 culls every camera-facing subtract poly.

### 4.6 Wireframe presence

`wire` → the whole render. `flat` → **yes**, over the fills. `textured` → **no**; the only
*deliberate* line art is `--highlight` (§5). A default `textured` render is not literally line-free —
`--annotate` defaults to on and still paints decals, keylines and the legend (§5).

**Line art follows the cull.** A face suppressed by §4.7's subtract cull or by the `PF_Invisible`
drop draws no wireframe edge, no `--highlight` outline and **no on-face index decal** — the cull
removes the face entirely, not merely its fill. A culled face is also **excluded from `occluders`** —
and the reason is the opposite of what an earlier draft claimed. `occluders` today takes only
`_is_front` faces, and `wire` culls nothing, so *keeping* culled faces would preserve `wire`'s decal
grading exactly; **excluding** them is what changes it. It is excluded anyway because a face that
draws nothing must not dim a decal on a face that does — the visual rule wins, and the cost is that
`flat`'s decal opacity legitimately differs from `wire`'s. `occluders` is what
`_occluder_count`/`_decal_opacity` grade each remaining decal against, so dropping culled faces from
it raises the opacity of decals those faces used to dim. **That difference is intended, and §9 pins
it** with its own row — it is the sole observable of this rule.

**Under `flat`, the edge pass draws the edges of the faces that SURVIVED the cull and are visible —
not "`_is_front` only".** `_scene_geometry` today emits an edge for every face regardless of facing and
`render_brushes_pgm` draws them with no depth test, so over opaque fills a cube's three hidden faces
would show straight through. But "`_is_front` only" is wrong in the other direction: for a subtract
brush §4.7 culls exactly the `_is_front` set, so the two rules would intersect to **nothing** and a
subtracted room would render as an outline-free blob — contradicting decision 2.5 and the `help=`.
**The rule, stated once and unambiguously: an edge draws iff its face SURVIVED the cull and that face
is front-facing *for its own brush's cull sense*.** Concretely: for a non-subtract brush that is its
`_is_front` faces; for a subtract brush it is its NON-`_is_front` (far) faces, which are exactly the
ones §4.7 kept. It is a **per-face facing test, not a per-pixel depth test** — an earlier draft said
"the nearest surface along that edge", which reads as true hidden-line removal against the depth
buffer. That is a different and much larger renderer (`_line` has no depth parameter, and §4.7's
strictly-`<` test would reject an edge pixel against its own face's fill), and it is NOT what this
spec asks for. A rear brush's front-facing edges therefore still draw over a nearer brush's fill;
that is accepted, and it matches how `wire` reads today. `wire` is untouched.

### 4.7 Visibility: CSG-aware culling, then a depth buffer

| Condition (tested in order)                       | Which faces render
|---------------------------------------------------|---
| `flags & PF_Invisible (0x1)`, actor-OR'd per §4.3a | **none** — dropped entirely, fill and line art alike
| `movers.is_mover(actor, index)`                   | **all** faces — a mover is never carved into the world, whatever `CsgOper` it carries
| the actor's `CsgOper == CSG_Subtract`             | **only faces NOT facing the camera** — the far/interior surfaces
| otherwise                                         | **all** faces; the depth buffer resolves visibility

Vertices are stored CCW-from-outside (`t3d.md`), so a subtract's near face is `_is_front` — exactly
the set to cull. Non-subtract brushes are **not** back-face culled: a `nonsolid` sheet is one face and
must be visible from both sides.

**Mover-ness comes from `movers.is_mover(actor, index)` — the repo's single shared, schema-AWARE
predicate — not from `classify_brush` and not from the raw `CsgOper` marker.** Both index-free
candidates are wrong, in opposite directions, and an earlier draft of this spec got it backwards:

| Brush                                        | `classify_brush` | raw `CsgOper` | correct
|----------------------------------------------|------------------|---------------|---
| a real subtracted room                        | `subtract`       | `CSG_Subtract`| cull — both agree
| `SomethingMover` with `CsgOper=CSG_Subtract`  | `mover`          | `CSG_Subtract`| **do not cull** — raw marker gets it wrong
| `CEDoor` / `BreakableGlass` / `TNM.*mover`    | `subtract`       | `CSG_Subtract`| **do not cull** — BOTH get it wrong

`classify_brush`'s mover arm is a documented **name guess**, and `movers.is_mover`'s own docstring
records that the `endswith("Mover")` test was already tried and rejected precisely because `CEDoor`,
`CaroneElevator`, `BreakableGlass` and `BreakableWall` are real movers whose names do not end in
`Mover`. Under `wire` a misclassification costs a shade; here it deletes every camera-facing face.

**This is why decision 2.13 accepts loading the class hierarchy for these two modes.**
**And once the index is loaded, `flat`'s FILL COLOUR uses it too.** `classify_brush`'s name guess must
not survive beside `movers.is_mover` in one render: for a `CEDoor` with `CsgOper=CSG_Subtract` the
guess returns `subtract` — gold fill, and `is_solid=False` for `occluders` — while `is_mover` exempts
it from the cull, so the picture shows a gold "carved volume" drawn as a closed solid with mis-graded
decals. `direction/conventions.md` forbids exactly this ("one shared predicate … no name-suffix
guess"; Rejected: "two predicates to keep true"). The cost that justified the guess — threading an
index into these verbs — is what decision 2.13 has now paid. **Under `flat`/`textured`,
`classify_brush`'s mover arm is replaced by `movers.is_mover`.** Under `wire` it is untouched, since
`wire` loads no index.

*(That this matches the editor and the game is the owner's ruling of 2026-07-26, quoted in decision
2.10 — attributed, not asserted as independently verified engine fact.)*

**A MIRRORED brush inverts the cull, and must be rejected under `flat` too.** `_scene_geometry` builds
world vertices with `rotation.actor_linear`, so a negative-determinant scale (`brush scale --by -1,1,1`
— `cli.py`'s own help says "a negative axis mirrors") reverses ring orientation, flips the Newell
normal and inverts `_is_front` for every face. The §4.7 cull then keeps a subtract's NEAR faces and
drops its far ones: the room renders inside-out, silently. §4.2 rejects scaled/sheared brushes under
`textured` only, so **that rejection extends to `flat` for the negative-determinant case specifically**
— not for scale in general (a positive-determinant scale leaves facing intact and `flat` still renders
it, per §4.2).

**The predicate must guard the identity sentinel.** `rotation.actor_linear` returns **`None`** when
rotation and both scales are identity (`rotation.py:297-298`) — the common case — so
`det(actor_linear(actor)) < 0` would raise `TypeError` on nearly every brush. It is:
`M = actor_linear(actor); mirrored = M is not None and det(M) < 0`.

**Depth**, after culling: `depth(P) = dot(P, _view_depth(iso_angle, view))`, **smaller = nearer**,
affine under ortho. Write iff `depth < zbuf[i]`. **Coplanar tie-break:** strictly `<`, so the first
face drawn wins and iteration is scene order (stable, as `assign_tints` already relies on) — no
epsilon bias, since a flush add/subtract pair is common pre-CSG and a bias would only move the
arbitrariness.

### 4.8 `--focus`

Every brush stays filled; non-focused brushes are dimmed. Two passes, **separate** depth buffers:

| Pass | Contents                | Depth buffer  | Colour
|------|-------------------------|---------------|---
| A    | all NON-focused brushes | `zbuf_ctx`    | resolved **opaquely** into a scratch buffer initialised to `BG`, then composited over the canvas **once**
| B    | the focused brush       | `zbuf_focus`  | opaque, full shade — drawn after A, never occluded by context

**Resolve-then-composite-once is required, not stylistic:** per-face alpha blending against a
nearest-wins depth buffer blends a pixel once per passing face, making the result depend on iteration
order.

**The dim strength is NOT fixed by this spec — it is chosen by render.** The originally-specified
`_fade(rgb, 0.75)` then alpha 0.25 was refuted (it leaves `0.0625·texel + 210` against `BG` 224, i.e.
invisible). The obvious replacement — one `_DIM_ALPHA = 0.15` composite, as the wireframe uses — was
independently flagged by every reviewer in that round as probably *also* too faint: it gives
`0.15·c + 190.4`, so a mid-grey texel lands ~210 against `BG` 224. `_DIM_ALPHA` was tuned for thin
**lines**, where a faint stroke still reads as a stroke; a large flat area at that strength is
near-uniform. **Owner ruling (2026-07-26): make it stronger, then verify with a real before/after
render rather than arithmetic.** The build produces that render, picks the constant from it, and
records the chosen value plus the image in the `rationale/` preview topic. Starting point ≈ 0.35.

### 4.9 Declared divergences from `level preview --native`

| # | Divergence
|---|---
| 1 | **Masking** — `--native` renders masked faces opaque (making it a free cut-out detector); this tier honours the cut-out on genuinely masked faces
| 2 | **Mip selection** — `render.rs` is **mip-0 only**; this tier picks a mip per face (§4.4)
| 3 | **Precision** — `render.rs` is f32, this is f64; byte-identity is not claimed
| 4 | *(NOT a divergence — listed because §4.3a's actor-OR'd flag test is shared.)* **`PF_Invisible`** — both tiers drop those polys on the actor-OR'd flags; the only difference is internal, that `wire` keeps drawing them
| 5 | **Projection** — ortho vs perspective, hence affine UV
| 6 | **Unresolvable/undecodable refs** — `--native` checkerboards and warns; this tier **exits 2** (§8). `conventions.md` rejects warn-and-continue, so this tier conforms and `--native` does not; that is logged against `--native`, not softened here
| 7 | **Scaled/sheared brushes** — a **behavioural** difference: `--native` rejects in every mode; this tier rejects them under `textured`, rejects only the **mirrored** (negative-determinant) subset under `flat`, and renders all of them under `wire`
| 8 | **Pre-CSG vs post-CSG** — the largest divergence, and the reason decision 2.10's cull exists at all: `--native` renders **built BSP node polys**, this tier renders **raw brush polys** with a hand-rolled subtract cull
| 9 | **Concave faces** — `render.rs` fills by triangle fan (`render.rs:196-206`), which bleeds outside a concave face; this tier uses even-odd scanline (§6) and is correct there. `architecture.md` measures 0.1–0.6 % of real faces as concave, so the difference is real. Not softened here — **logged against `--native` on `board/inbox.md`** (filed 2026-07-26)
| 10 | **Background** — `render.rs`'s `BACKGROUND` is `[56,56,60]`; this tier's `BG` is 224
| 11 | **Non-planar faces** — this tier interpolates UV and depth from ONE plane per face (§6, anchored at `verts[0]` with the Newell normal); `render.rs` fan-triangulates, so each triangle carries its own plane. On a face that is not planar the two disagree in both UV and depth. Reachable via `--from-t3d` over arbitrary editor T3D

### 4.10 Draw order within a pane

1. background (`BG = 224`)
2. **face fills + depth (new)** — under `--focus`, pass A then pass B
3. point-actor underlays (`_draw_point_underlay`) — selection brackets, **sprites**, and the `--show`
   collision/light/sound overlays
4. brush wireframe edges — **`wire` and `flat` only**
5. `--highlight` outlines
6. point markers → legacy leader labels → painted on-face decals → the overlap keyline → the legend
   (the existing order at `preview.py:1663-1749`, unchanged)

Fills sit at step 2, **ahead of the point layer**: they are brush geometry, and placing them later
would paint over every sprite and every `--show` overlay.

## 5. Interaction with every existing option

| Option              | Behaviour under `flat` / `textured`
|---------------------|---
| `--layout`          | all three accept it. See §7 for what `breakdown` costs
| `--view`            | unchanged, **including the mip pick**. §4.4 derives it from the face's own screen-space UV gradients, which already account for the projection — there is no per-view `gain` term (an earlier draft had one; §4.4 measured it wrong and removed it)
| `--iso-angle`       | feeds `_view_depth` **and the mip pick** — not via a separate `gain` term, but because `_project`'s iso branch uses it and §4.4 derives the level from the resulting screen-space gradients. §9 tests this at a non-default 80°
| `--brush-colors`    | `flat`: as today. **`textured`: passing it explicitly is a clean exit 2** (decision 2.7)
| `--annotate`        | unchanged and **left exactly as-is** (owner-decided). Two accepted consequences: (a) a tinted decal can be unreadable on a busy texture; (b) `_decal_opacity` still paints an *occluded* face's index at a 0.12 floor, so over an opaque fill that number sits on the wall in front of it — a wrong-face label. Read indices off `flat`, or pass `--annotate none`
| `--highlight`       | under `textured` its vivid outline is the only deliberate line art. Hue comes from `vivid`, `csg`-derived since `--brush-colors` is rejected here. A face removed by the §4.7 cull gets no outline
| `--focus`           | §4.8
| `--show`            | unaffected — the overlays draw at step 3, above the fills (§4.10)
| `--frame`/`--frame-tightness` | set `scale`, which feeds the mip pick
| `--size`            | uncapped (decision 2.4)
| `--from-t3d`        | works **when every texture the snippet references is readable**. A generated snippet carries `texture=None` per poly *only when `brush build --texture` was not passed* — that flag stamps a ref onto every face — a no-texture snippet needs no **texture** source (decision 2.6) — but under `flat`/`textured` it still needs the **class hierarchy** (decision 2.13, §8), so those two modes are not offline-capable on `--from-t3d` either. **`--faces wire` remains fully offline-capable on this path** — the property §0 promises is preserved
| `--prefab-dir`      | **does NOT imply "no project", and no project does NOT imply no resolver.** It overrides only the prefab *library root* (`dispatch._prefab_root`); `_preview_render_data` independently calls `_resolve_project(args)`, and `config.composed_search_files` accepts `project=None`, falling back to the base dirs — which that function already relies on. Conversely a valid project can still yield no resolver (§8's three causes). **The trigger is `resolver is None` AND the scene referencing at least one texture**, never "no project"
| `--out`             | unchanged (always PNG)

**Point actors are unaffected** by `--faces`.

**How `--brush-colors` explicitness is detected.** Its argparse `default` is `"csg"`, so a defaulted
value is indistinguishable from an explicit `--brush-colors csg`, and decision 2.7 rejects only the
*explicit* case. The parser sets `default=None`. **Its three consumers are `dispatch.py:754`, `:855`,
`:862`** — and each is `getattr(args, "brush_colors", "csg")`, whose default does **not** fire for an
existing-but-`None` attribute, so **each needs an explicit `or "csg"`**. Only a non-`None` value
alongside `--faces textured` triggers exit 2.

## 6. Code shape

| Change                                                                     | Where
|----------------------------------------------------------------------------|---
| `world_uv_frame`, `tex_basis_default`, `newell` move to a shared stdlib-only module | new `uedcli/texframe.py`
| `preview._face_normal` **and `preview_native._newell`** are both deleted (byte-identical, and `_newell` is the one `world_uv_frame` calls); `preview.py`, **`query.py:13`**, **`polyalign.py:32`** and `preview_native.py` import `newell` from `texframe`. (`builders.py:82` is a third copy returning `Vec3` — deliberately left alone) | `preview.py`, `preview_native.py`, `query.py`, `polyalign.py`
| **every `world_uv_frame` importer re-points**: `polyalign.py:33` (used at :257/:330/:417), `tests/test_polyalign.py:445`, `tests/test_preview_native.py:167/181/195`. A re-export alias in `preview_native` is forbidden by "No back-compat cruft", so all move in the same change | `polyalign.py`, both test modules
| `poly_flags_int` moves to `texframe` too (§4.3a) — `preview.py` must not import `preview_native` | `texframe.py`, `preview_native.py`
| build the `ClassIndex` and resolve **mover-ness per actor** (decision 2.13), passing the result across the seam as data — `preview.py` stays schema-free and never calls `movers.is_mover` itself | `uedcli/dispatch.py`
| the `--faces` MODE itself needs a channel: a `faces=` parameter on `render_brush_pgm`, `render_brushes_pgm`, `render_quad_pgm` and `dispatch._render_breakdown_grid`'s `_pane`. It cannot be inferred from the seam — `faces=None` would be both `wire` and `flat` | `preview.py`, `dispatch.py`
| `tests/test_actor_preview.py`'s `_prev` helper hardcodes `brush_colors="csg"`, which under §5's `default=None` scheme is an EXPLICIT value and would trip §2.7's exit 2. Its `SimpleNamespace` also lacks `faces`, so **dispatch must read the mode as `getattr(args, "faces", "wire")`** | `tests/test_actor_preview.py`
| **a third committed harness calls the same seam**: `dev/docs/spikes/2026-07-24-corpus-brush-idioms/render_brushes.py:186` invokes `dispatch._render_actors_to_out` with a hand-built namespace (`_args_for`, `:92-96`) that has no `faces` attribute. `rules/spikes.md` makes it durable evidence, so it is in scope | that harness
| the mip-pyramid accessor + the `bMasked` predicate, on the decoder's typed-result contract | **folded into the texture-decoder item — §12**
| resolve each distinct face ref; map any typed error to exit 2; the four exit-2 validations | `uedcli/dispatch.py`
| `--faces` parsing; `--brush-colors default=None`; three corrected `help=` strings | `uedcli/cli.py`
| the fill rasterizer, depth buffers, focus two-pass, mip pick, texel loop | `uedcli/preview.py`

**Buffers use the `array` module, not Python lists.** `--size` is uncapped (decision 2.4), and a
`list[float]` depth buffer at `--size 4096` is ~0.5 GB against ~67 MB for `array("f")`. Depth buffers
are `array("f")`; the scratch RGB buffer is a `bytearray` like the canvas. A `MemoryError` is still
reachable at absurd sizes — it is caught and reported as a clean exit 2 naming the size, never a
traceback (§8).

**The interpolation plane is the face's own plane**, anchored at `verts[0]` with the **Newell** normal
(the same `N` as §4.1). Stated because faces are not guaranteed planar — `--from-t3d` reads arbitrary
editor T3D — so the anchor and normal choice are observable. A face whose *projected* area is zero
(edge-on) gives a singular gradient solve; it is detected up front and skipped, the same disposition
as §4.1's degenerate skip.

**The rasterizer is EVEN-ODD SCANLINE with affine UV, not a triangle fan.** `architecture.md` records
that **0.1–0.6 % of faces in real exported maps are concave** (spike `concave-faces/`, live
2026-07-23) — which is why `preview.py` already carries `_poly_is_convex_2d`. A fan triangulation
fills *outside* a concave face. Scanline with even-odd parity handles both cases in one path, and
under ortho `u`, `v` and depth are affine in screen space, so they interpolate exactly from the face's
plane without triangulation. Coverage rule: sample at the **pixel centre** (`x + 0.5`, `y + 0.5`),
matching `render.rs:241-244`.

**The `render_data` seam.** Today `dict[actor_name → PointRender]`; it becomes:

```
PreviewData(points: dict[str, PointRender], faces: FaceData | None)
FaceData:      movers:  frozenset[str]      # actor names movers.is_mover said yes to — §4.7's cull
               textures: TextureData | None  # None under `flat`; populated under `textured`

TextureData:   by_ref: dict[str, list[tuple[int,int,bytes,bytes]]]   # casefolded ref → mip pyramid
               masked: dict[tuple[str,int], bool]                    # (actor, poly_idx) → §4.3a
```

**The split is deliberate and load-bearing.** `flat` needs `movers` (§4.7's cull) and needs **no**
textures at all. A single `FaceTextures | None` would tempt an implementer to pass `None` for `flat` —
the natural reading of a type named for textures when there are none — which silently drops the mover
set, and §4.7's cull would then treat a `CsgOper=CSG_Subtract` mover as a subtraction and render the
door inside-out. That is precisely the failure decision 2.13 was ruled to prevent. So: `faces` is
`None` only under `wire`; under `flat` it carries `movers` with `textures=None`; under `textured` it
carries both.

`by_ref` is keyed on `ref.casefold()` (FName semantics, matching `preview_native._TextureTable`), and
every ref in the set is guaranteed present — an unreadable one exits 2 before rendering, so there is
no fallback slot and no missing-key path.

**All call sites, complete** (round 2 found the earlier list short and "mechanical" overstated):

- `preview._scene_geometry:1446` — `render_data.get(name)` then `if pr is None: continue`. Must stay
  a `.get`, on `.points`; `[name]` would raise `KeyError` for a legitimately-absent point actor
- `preview.render_brushes_pgm:1622` and `preview.render_quad_pgm:1868` — both do
  `render_data = render_data or {}`, which under the new type yields a bare `dict` with no `.points`
  ⇒ `AttributeError` to the user. Both must default to an empty `PreviewData`
- `preview.render_quad_pgm:1870` — `a.name in rd`
- `preview.render_brush_pgm:1563` — a fourth public entry point
- `dispatch._world_aabb:618` — both `in` and `[...]`; `_point_pane_region` and `_resolve_zoom` reach
  it through that
- `uedcli/tests/test_preview.py` constructs plain dicts and migrates with them

**`_preview_render_data` must be restructured.** It early-returns `{}` when the set has no point
actors (`dispatch.py:1038-1039`) — the common case for a brush-only textured preview — so neither
face resolution nor decision 2.6's exit 2 is reachable as written. Its docstring's "a pure-brush
preview works with no game install" stays true for `wire`/`flat` and is now false for `textured`.

## 7. Cost, and the accepted risk

| Layout        | Panes                                             | Pixels at `--size 1024`
|---------------|---------------------------------------------------|---
| `single`      | 1 at `size`                                       | ~1.05 M
| `quad`        | 4 at `size // 2` (`render_quad_pgm`)              | ~1.05 M total — **~1× a single pane**
| `breakdown`   | **N+1 at full `size`** (`_render_breakdown_grid`) | ~(N+1) × 1.05 M

**`--layout breakdown` is the worst case.** Only the per-**brush** panes are `--focus`ed — pane 0 and
every point-actor pane pass `focus=None` (`dispatch.py:775-783`) — so the two-pass count is the brush
count, not N+1.

**On timings, stated honestly.** The one measurement taken is `actor preview` quad @1024 **wireframe**
at 4.6 s (~1.05 M px) — measured 2026-07-26 on LUM `basement` (28 actors) via
`time (uedcli actor find | uedcli actor preview - --out …)`, on the 4-core box this repo is developed
on. That is *not* a fill rate — its cost is dominated by label placement and decal
planning — so it cannot be extrapolated to fills, and this spec makes **no** slower/faster claim
against `--native`. What is certain is qualitative: fills are O(area) where wireframe is O(perimeter),
and a pure-Python per-pixel loop is far slower than the Rust one. **The build takes a real fill
measurement before any doc states a number.**

**The owner re-affirmed "no guard, no ceiling"** (*rejected: exit 2 for `textured` under `breakdown`;
rejected: a stderr cost estimate*). Accepted consequence: a large breakdown textured render can run
for minutes with no progress output. **There is no cost control at all** — §4.4's mip selection is an
image-quality control only; an earlier draft wrongly called it one, and this ruling was re-put on the
corrected picture.

## 8. Failure and degradation

**Every failure refuses; none degrades.** Most run in `dispatch` before any pixel is drawn. **Two
cannot**, and are called out rather than papered over: the **non-finite UV frame** (§4.3) is detected
per face inside `preview.py`, and a **`MemoryError`** necessarily surfaces during rasterization. Both
still refuse — `preview.py` raises a dedicated `PreviewAbort` carrying the actor/poly, and `dispatch`
maps it to exit 2 — but neither is a pre-flight check, and a reader must not infer that a `--faces`
render is fully validated before it starts.

| Situation                                        | Behaviour
|---------------------------------------------------|---
| bad `--faces` value                                | argparse choice error, exit 2
| `--faces textured` + explicit `--brush-colors`     | exit 2 naming both flags and the conflict
| `--faces textured` + a scaled/sheared brush        | exit 2 listing **every** such actor with its offending field (`conventions.md`: a batch is all-or-nothing). `wire` is unaffected; `flat` refuses only the mirrored subset — next row
| `--faces flat` + a **mirrored** brush              | exit 2 listing every such actor. A mirror inverts `_is_front`, which §4.7's cull depends on, so the render would be inside-out and silent (§4.7). Non-mirroring scale or sheer renders normally under `flat`
| `--faces textured`, the scene REFERENCES a texture, and no resolver | exit 2 naming **which** of `_texture_resolver`'s three causes applies — no user games config, a `ConfigError`, or an empty composed file list (`dispatch.py:936-945`); all three are reachable *with* a valid project, so a generic "no project" message would violate "naming the offending value"
| a **bare (unqualified)** `Texture=` ref            | exit 2 naming the ref **and saying to qualify it as `Package.Name`**. `_decode_ref` rejects an unqualified ref before any lookup, so this is the most common miss on real content; `preview_native._TextureTable` already emits exactly this hint
| a ref that does not resolve, or does not decode    | exit 2 listing **every** such ref in one run (not just the first) with the decoder's typed-error case for each — §12's contract makes "which cause applies" answerable
| a **non-finite UV frame** on any face (`nan`/`inf`) | exit 2 naming the actor and poly. Detected in `preview.py`, raised as `PreviewAbort`, mapped by `dispatch`. **Not** rendered as `DEFAULT_GREY`: that would be pixel-identical to the legitimate no-`Texture` row below, i.e. a half-answer that looks like a full one
| a poly with no `Texture` at all                    | `DEFAULT_GREY × shade`, silently — normal, not an error
| `--faces flat` or `textured` and mover-ness cannot be resolved | exit 2 naming **which** of `movers.is_mover`'s four causes applies (`movers.py:52-73`): the index cannot resolve `Engine.Mover`; **an actor's own class does not resolve** (package off the search path — reachable on ordinary `--from-t3d` content); its ancestor chain truncates before `Core.Object`; a bare class name's candidates disagree. The last three are per-actor and name that actor. `ClassRefError` is a `ValueError` subclass, so the preview path must catch it rather than let it surface. `wire` is unaffected
| `--faces textured`, scene references NO texture, no resolver | **renders normally** (decision 2.6) — nothing needed, so nothing refused. (The class index is still required, per the row above)
| a `MemoryError` from an absurd `--size`            | caught, exit 2 naming the size — never a traceback

**Every row is scoped to the mode named in it.** `--faces wire`, the default, gains no new failure: it
needs no texture, no resolver and no project, exactly as today.

`conventions.md` puts warn-and-continue under **Rejected**, and a textured render whose faces are
secretly checkerboards is exactly that: the picture looks like an answer.

## 9. Tests

| Test                                                                                | Guards
|--------------------------------------------------------------------------------------|---
| `--faces wire` output **byte-identical** to today for a fixed scene                   | the change is additive — the primary regression guard
| `u = (V − Origin)·TextureU + Pan` on a rotated, pre-pivoted brush                     | the UV convention
| **mip level L samples the same world point as level 0** (the `/2**level` rescale)      | a test of level *selection* alone passes the buggy version
| **mip pick under `--view iso`**: assert the level-selection function directly against a computed expectation at a NON-default `--iso-angle` (e.g. 80°, where σ_min/σ_max differ by 6.98×) | §4.4. Asserting only "iso differs from ortho" proves nothing — the two panes already differ in `_framing` scale, and at the default 30° the two candidate gains coincide, so such a test passes with `gain` hard-coded to 1.0
| a **masked** face's index-0 texels leave `BG` and skip depth; an **unmasked** face's index-0 texels draw normally | decision 2.3, both directions
| a brush with **actor-level `PolyFlags=2`** masks even though its polys carry no flag    | §4.3a's OR — the round-2 defect that would re-hide a motivating bug
| **a synthesized fixture package carrying `bMasked`** exercises the texture-side arm     | neither committed fixture has one and the game corpus is gitignored, so without this the half the spike calls load-bearing ships untested
| a **positive-determinant** scaled brush and a sheared brush each exit 2 under `textured`, and still render under **`wire` AND `flat`** | §4.2's scope
| a **MIRRORED** brush (`brush scale --by -1,1,1`) exits 2 under **both** `flat` and `textured`, still renders under `wire`; and an unscaled brush does not crash the predicate (`actor_linear` returns `None`) | §4.7's mirror rule and its identity guard
| **subtract**: camera-facing faces culled, far faces drawn, an add brush inside a subtract visible, and no wireframe/highlight on a culled face | decision 2.10 + §4.6
| a `nonsolid` sheet renders from both sides                                             | the cull is subtract-only
| a **concave** face fills only inside its boundary                                      | §6's scanline choice; a fan would bleed outside
| two overlapping brushes: nearer wins; coplanar tie goes to scene order                 | §4.7
| a culled face draws no wireframe edge, no `--highlight` outline and **no on-face index decal**; and `flat`'s decal opacity differs from `wire`'s exactly where a culled face left `occluders` | §4.6 — the pin that section promises
| point **sprites** and each `--show` overlay survive an opaque fill                      | §4.10
| `--focus`: focused brush visible when fully enclosed; context composited **once** (order-independent) | §4.8's two-buffer mechanism
| `PF_Invisible` (actor-OR'd) faces do not fill and do not write depth                    | §4.9 #4
| `flat` fill RGB for `csg`, `legend`, and the legacy `color_by_csg=False` path, unshaded | §4.5, all three
| bare `--faces textured` succeeds; `--faces textured --brush-colors csg` exits 2          | the `default=None` + `or "csg"` mechanism
| each of the resolver's three `None` causes, a bare ref, and an undecodable ref produce distinct exit-2 messages naming the case | §8
| `stash preview` / `prefab preview` accept `--faces`; `--prefab-dir` inside a project **succeeds** | §3, §5 — the inverted round-2 claim
| `--layout quad` and `--layout breakdown` render under `flat` and `textured`               | untested layouts in both rounds
| non-finite UV (`nan` **and** `inf`) produces a clean result, never a traceback            | §4.3
| **`textured` emits no wireframe pixels; `flat` does** | decision 2.5 — its most visible observable, previously untested
| **a poly with no `Texture` renders `DEFAULT_GREY × shade`** | §4.3 — the most common `textured` render in practice (a generated brush)
| **§4.1's shade formula and truncation** on a known normal | a golden PNG cannot separate a shade error from a UV error
| **§4.2's zero/missing-axis `_tex_basis_default` fallback** | §4.2 justifies preserving it verbatim as the anti-drift guarantee, so it needs its own pin
| a `CEDoor`-style mover carrying `CsgOper=CSG_Subtract` is **NOT** culled, while a real subtract brush **is** | §4.7 + decision 2.13 — the case both index-free rules get wrong
| `--faces flat` and `textured` exit 2 when the class hierarchy cannot be loaded; `wire` still renders | decision 2.13's accepted cost, in both directions
| **a scene referencing NO texture renders with no resolver**; one referencing a texture exits 2 | decision 2.6's literal "needs"
| **`flat` drops back-facing edges**; `wire` still draws them | §4.6's hidden-line rule
| a golden PNG of a textured cube                                                           | end-to-end pixel stability
| `uedcli/texframe.py` imports nothing outside stdlib + uedcli                               | §0's no-cargo constraint

**Dropped as unimplementable or vacuous:** the cross-renderer "same texel index" test — `render.rs` is
reachable only as `render_frame` → RGB bytes, never texel indices; the projections differ; and it is
`importorskip`-gated, so it would silently skip on the no-cargo machine §0 protects. Cross-renderer
agreement is instead guarded by `texframe` being the **single shared source** of the UV frame. Also
dropped: "`%` vs `rem_euclid`" (true by definition for positive divisors) and "runs with the native
extension absent" (`preview.py` never imports it — the `texframe` import test is the real guard).

## 10. Deferred

- The Rust port / a non-optional native extension.
- **Scaled and sheared brushes** under `flat`/`textured` — rejected in v1 (§4.2); supporting them
  needs UE1's actual scaled-brush texture-frame behaviour verified first.
- Bilinear filtering, real lighting, mesh rendering for point actors, the `Translucent` polyflag.
- A `texture list --cutout` filter over the catalog's dominant-colour signal.

## 11. The masking spike — DONE

[`spikes/2026-07-26-texture-masked-property/findings.md`](../../../spikes/2026-07-26-texture-masked-property/findings.md):
the stored property is **`bMasked`**, a UE1 bool written **presence-only** (present ⇒ masked), decoded
by the existing `utexture._read_props`. Two measurements size what decision 2.3 avoided:

- **464 of 2,669** corpus textures use index 0 while unmasked — **17.4 %**. Flat colour swatches
  (`LUM_CoreTex.White`, `.Red`, `.Yellow`, `.SILVER`, `.NAVY` and eight more — **13** in total) are
  **100 %** index 0 and would have rendered as nothing at all.
- **Reserved magenta at palette[0] is not a masking signal** — three unmasked textures park it and
  never use it, while `ArthurCallaway` (2.2 % index-0 usage) has real black there.

Pinned by two `test_engine_facts` regressions against committed fixtures.

## 12. Build order (owner ruling, 2026-07-26)

**The texture-decoder item builds FIRST, with this spec's texture accessor folded into its scope; then
all of this.**

`to-build.md`'s **"Native texture decode for any UE1 package"** (`p1`, on deck, spec + plan
self-contained) rewrites the same component this spec depends on: it **deletes
`TextureResolver.resolve_masked`**, **replaces `resolve`'s `None`-on-miss contract with a typed error
object naming the case**, and adds **`CompMips`**, a second compressed mip array. It also fixes a live
bug — **30 textures in `LUM/Textures/LUM_CoreTex.utx` are unreadable today** — and gates the asset
catalog, so it lands first regardless.

**Folded into its scope** (one texture-API change, not two):

1. **A mip-pyramid accessor** — every mip of a ref as `(w, h, rgb, mask)`, on its typed-result
   contract, replacing this spec's earlier `resolve_mips(...) -> … | None`.
2. **`bMasked` on the typed result**, NOT a `texture_has_bMasked(ref)` predicate — §4.3a explains why
   (a second entry point for one question, and a bool predicate cannot distinguish "unqualified ref"
   from "unreadable"). *(That plan already carries this correction; recorded here because §12 is the
   section its builder reads.)*

*Rejected: shipping `wire`/`flat` first and `textured` after; rejected: waiting for that item without
folding the accessor in (two API changes); rejected: building now against today's decoder.*

**Both consequences are already carried into that item** (done 2026-07-26, not outstanding): its plan
holds slice `S2b` with the accessor and the verbatim "`actor preview --faces textured` REFUSES — do
not assume every preview caller degrades" contract note, and its `to-build.md` entry is flagged scope-
widened so the plan re-enters plan review before building. That plan's own round-1 review is recorded
at its foot. **Both of that plan's escalations are now RESOLVED** (its `repo_texture_root()`
propagation, and its decode oracle — the latter by spike `2026-07-26-ucc-texture-fixture`), so the
dependency is not parked. **This spec still builds SECOND**: it consumes S2b's mip-pyramid accessor
and the `bMasked` flag on S2's typed result, neither of which exists until that item lands.
*(Superseded text follows for the record — it named findings that were closed by the time it was
written, which is why the gate is now stated as a slice dependency instead. Per `CLAUDE.md` the
superseded wording is not preserved — git holds it.)*

For orientation only, the formerly-cited findings: two of them
(S2b's missing tests, and the `bMasked` flag's home) are the half this spec consumes.


---

## 13. Review history

Both spec-review rounds have run (2026-07-26) at the headcount `CLAUDE.md` "Review gates" sets — the
count is deliberately not restated here, per that section's own rule. **No structural finding** in
either round. Findings are resolved into the sections above; git holds the reports at `77769d2` and
`559405e`. Owner rulings taken during resolution are recorded at the decisions they govern.


## 14. Former escalations (both RESOLVED) and items carried to the build

Round 2 is the gate's ceiling (`CLAUDE.md` "Review gates"), so what is still standing is escalated
rather than carried into a third round.

### E1 — RESOLVED 2026-07-26 by owner ruling: load the class hierarchy (decision 2.13)

The owner ruled that `flat`/`textured` load the class hierarchy and use `movers.is_mover`, accepting
that those two modes lose the "works with no game install" property while `wire` keeps it. §4.7 and
§8 implement it; the alternatives and their costs are recorded at decision 2.13. The analysis that
led there is kept below because it is what makes the ruling's cost legible.

#### (the analysis)

Decision 2.10 culls a subtract's camera-facing faces. **Both candidate rules are wrong, in opposite
directions, and I got this backwards last revision.**

`preview.classify_brush` tests `cls.endswith("Mover")` **first**, then `CsgOper`. So
`classify_brush == "subtract"` is a strict **subset** of `CsgOper == CSG_Subtract`:

| Brush                                            | `classify_brush` | raw `CsgOper` | cull?
|--------------------------------------------------|------------------|---------------|---
| a real subtract                                   | `subtract`       | `CSG_Subtract`| yes, both rules agree
| `SomethingMover` with `CsgOper=CSG_Subtract`      | `mover`          | `CSG_Subtract`| **classify: no · raw: YES** — a door rendered inside-out
| `CEDoor` / `BreakableGlass` / `TNM.*mover`        | `subtract`       | `CSG_Subtract`| **both cull it** — also inside-out

So switching to raw `CsgOper` (my last revision) culls *more*, not less, and **the `CEDoor` case both
rules get wrong**. The §9 test I wrote to guard it was unsatisfiable under either rule.

There is no schema-free fix: `movers.is_mover` needs a `ClassIndex`, which `actor`/`stash`/`prefab
preview` deliberately do not thread (that is an existing open item `classify_brush`'s own docstring
points at). `preview_native` only gets this right because it *does* have an index.

**Options, all with real costs:** cull on raw `CsgOper` and accept subtract-movers rendering
inside-out; keep `classify_brush` and accept a `*Mover`-named subtract escaping the cull; thread a
class index into these three verbs (scope increase, and it breaks their "no game install needed"
property); or drop the cull for anything that looks like a mover by any signal and accept the same
name guess one layer down.

### E2 — RESOLVED 2026-07-26: `--native`'s triangle-fan concave bleed is now filed

§4.9 #9 had claimed a board entry that did not exist. The entry is now on `board/inbox.md` as a `p2`
`[debug]`, carrying the reviewer's scope caveat (`render.rs` rasterizes post-CSG BSP node polys, which
are convex, so the authored-face measurement reaches it only on the mover path).

### Also standing, lower severity — fix during the build

- ~~**A mirrored brush inverts §4.7's cull**~~ — **RESOLVED**: `flat` and `textured` both refuse the
  negative-determinant case (§4.2, §4.7, §8), with the `actor_linear`-returns-`None` guard, and §9
  tests both directions.
- ~~**§6 defines no channel for the `--faces` MODE itself**~~ — **DONE**, §6's table now carries the
  `faces=` row. Kept struck rather than deleted so a reader of an older review can see it closed.
  *(original text)* — the `render_data`
  seam carries textures, but `faces=None` is both `wire` and `flat`, so the renderer cannot tell which
  mode it is in. A `faces=` parameter is needed on `render_brush_pgm`, `render_brushes_pgm`,
  `render_quad_pgm` and `_render_breakdown_grid`'s `_pane`.
- **The owner's decisions in §2 have no durable `direction/` home**, and this file is deleted on build.
  `CLAUDE.md` requires the decision to land durably first. Several are policy, not implementation:
  2.4 (no cost ceiling), 2.6 ("needs" is literal), 2.10 (subtract visibility), **2.13 (the class
  hierarchy load)** and 2.12 (§4.8's choose-by-render). **DONE 2026-07-26** — all five are parked as
  one `[OWNER — confirm]` item on `board/inbox.md` carrying the proposed `direction/` text verbatim,
  so none is lost when this file is deleted.
- **`--from-t3d` + point-actor sprite refs** under decision 2.6: does an unresolvable *sprite* count as
  "a texture the render needs"? The existing path degrades it to a marker plus a stderr note. And are
  refs on culled faces collected before or after the cull? Both change the exit code.
