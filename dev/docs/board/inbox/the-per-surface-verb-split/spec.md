# Spec — per-surface texture verbs: `pan`, `rotate`, `scale`, and `align wall|floor|run|one-tile`

**Date:** 2026-07-26 · **Status:** §2–§4 REWRITTEN from the settled ruling set (thirteen owner rulings,
several superseding earlier ones) after earlier re-gates found the patched document describing more
than one design; then **corrected in place after the spec gate's round 1** (the closed-run walk
direction, §2.4.1 step 7; the cap predicate, step 4, now removed outright; `run`'s across-run axis
convention, §2.4.2; `one-tile`'s skewed basis, §2.6, owner ruling; and a false premise in §2.3/§7
about what deleting the co-orientation guard costs); then **again after round 2**, which replaced
§2.2's out-of-plane tolerance with the plan's absolute-or-relative rule, replaced §2.4.2's across-run
sign convention (the fixed axis-priority chain was discontinuous on a gently graded track bed), moved
`--fit-perimeter`'s guards into the step that makes them reachable (§4.4), gave §4.3 a per-step
column, and promoted the `run` V-flip to an owner narrowing (§7). The previously-open algorithm
questions — branching, terminal faces, connectivity validation, the derived root and walk direction,
the across-run axis — are decided in §2.4.1–§2.4.2. **The spec gate is at its ceiling
(`CLAUDE.md` "Review gates"): what stands after this pass is fixed, parked on `board/inbox/`, or
escalated — there is no further round.**
· **Evidence:** [`dev/docs/spikes/2026-07-26-poly-rotate-curved-track/`](../../../spikes/2026-07-26-poly-rotate-curved-track/README.md)
(the curved run) and [`dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/`](../../../spikes/2026-07-26-unrealed-texalign-semantics/README.md)
(the measured editor semantics).

> Ephemeral, per `CLAUDE.md` "Documentation". Once built, the durable half goes to
> `direction/conventions.md` (the owner's rulings — **which needs their explicit yes and a
> `Confirmed:` trailer**, see §7) and the `rationale/` tree (the engineering choices): the verb split
> and the re-anchor are already in `rationale/surface.md`, and the align frame math lands in a
> **new sibling topic for `polyalign`**, created when step 4 does — it does not exist yet, so nothing
> may cite it as a path until then. Do not cite this file from a durable doc.

## 1. Problem

UnrealEd surface editing has four canonical operations — **pan, rotate, scale, align**. uedcli ships
pan (as two flags on `brush poly set`) and a narrow align (`brush poly align --wall/--floor/--ring`).
Rotate and scale do not exist. The 2026-07-19 usability probe flagged the two missing ones; the
2026-07-26 curved-track spike then showed the gap is worse than "two verbs missing":

- On a **revolved** brush's flat top face, all facets share one world-axis-aligned frame, so the
  texture runs dead straight across the bend and ignores it entirely (spike finding 1).
- The shipped `--ring`, the only mode that carries a texture along a curve, **rejects coplanar sets** —
  exactly the case a curved floor/track bed presents (finding 3).
- `brush poly set`'s `--pan-*` flags exist only because pan had nowhere else to live; the verb now
  mixes attribute assignment (texture, flags) with frame transformation.

Result: a curved track bed — a routine level-design shape — cannot be textured correctly by any
combination of shipped verbs.

## 2. The verb set

| Today (shipped) | Proposed | Why |
|---------------------------------------|-----------------------------------------|---
| `brush poly set --texture --add-flag --remove-flag --pan-to --pan-by` | `brush poly set --texture --add-flag --remove-flag` | `set` assigns STORED per-face fields. Pan/rotate/scale transform the FRAME. Two different jobs. |
| — | `brush poly pan (--to \| --by) U,V` (§2.1) | integer texel offset, promoted out of `set` |
| — | `brush poly rotate --by UU` (§2.2) | a face on its own terms; no continuity guarantee |
| `brush poly align --wall \| --floor [--fresh-frame]` | `brush poly align wall \| floor` (§2.3) | mode becomes a SUBCOMMAND; the frame is derived from WORLD SPACE, not from a seed face; `--fresh-frame` deleted |
| `brush poly align --ring [--fresh-frame] [--fit-perimeter]` | `brush poly align run [--turn UU] [--fit-perimeter]` (§2.4) | generalised from "cylinder sides" to any connected run; coplanar sets allowed |
| — | `brush poly scale (--to \| --by) U,V` (§2.5) | the fourth canonical surface op; the only general density control |
| — | `brush poly align one-tile` (§2.6) | fit exactly one tile to each face — signs, monitors, light panels |

Per `CLAUDE.md` "No back-compat cruft": `--pan-to`/`--pan-by` on `set`, the `--wall`/`--floor`/`--ring`
**flag** spellings, and `--fresh-frame` are **deleted outright** in the same change that adds the
replacement. No aliases, no shims, no "old way" branch in code, tests or docs.

### 2.0 Modes are SUBCOMMANDS, not a mutually-exclusive flag group

`brush poly align <mode> <targets…|->`, with `<mode>` one of `wall`, `floor`, `run`, `one-tile`.
Owner ruling 2026-07-26. The reason is that **the flags are disjoint per mode**:

| mode | valid flags | shape of the operation |
|------------|--------------------------|---
| `wall` | — | stamp a world-projected frame on each face; projection axis derived from X/Y (§2.3) |
| `floor` | — | the same, projecting along Z (§2.3) |
| `run` | `--turn`, `--fit-perimeter` | walk a connected run, carry phase across seams (§2.4) |
| `one-tile` | — | per-face fit; no continuity, no orientation guard (§2.6) |

As a flag group that cannot be expressed: `-h` shows one blob in which most options are invalid for
most modes, and every bad combination has to be caught at runtime — one hand-written check and one
regression test per combination. `polyalign.align()` already carries exactly one such check
(`"--fit-perimeter applies only to --ring"`, the first statement of `polyalign.align()`, pinned by
`test_fit_perimeter_requires_ring`), and the new `--turn` would need a second one that nobody has
written. As subcommands both vanish: argparse rejects `--fit-perimeter` on `wall` before any uedcli
code runs, so the shipped check and its test are **deleted** (§4.1), and `--turn` never needs one.
`brush poly align run -h` then lists exactly the two flags that apply, which is what `CLAUDE.md`
requires of `-h`.

It also matches the precedent already in the CLI: **`brush build <shape>`** is the same problem — one
operation, several parameterised variants with disjoint flags (`--sides` for cylinder,
`--angle`/`--segments` for revolve, `--point` for extrude) — and it is already solved this way. The
cost is depth (`brush poly align run` is four levels); consistency with `build` outweighs it.

### 2.1 `brush poly pan (--to | --by) U,V`

Straight promotion of the existing flags. Targets are `BRUSH:SELECTOR` positionals or `-`; `-` is the
sole source; empty stdin is a clean no-op (exit 0). Exactly one of `--to`/`--by` is **required** — a
required mutually-exclusive argparse group, with its own message. (Do *not* carry over
`apply_surface_edit`'s `"at least one of --texture/--add-flag/--remove-flag/"` text: that is `set`'s, it names five
flags, and its rule is *at least* one rather than *exactly* one.) Values are **integer texels**,
written to the polygon `Pan` field.

**Target grammar across the per-face verbs.** `align` also accepts a bare brush Name meaning all its
polys (`resolve_align_targets`); `pan`, `rotate` and `scale` take `BRUSH:SELECTOR` only. The asymmetry
is deliberate and runs this way round: **a whole brush is a meaningful unit for `align` and not for
the three transforms.** "Wrap this cylinder", "stamp the world grid on this brush" are whole-brush
operations — that IS what a mode does — so a bare `Tower` is the natural spelling of the set. A
whole-brush *pan/rotate/scale* is a blanket nudge of every face the brush has, including the ones the
author never looked at, and `--by` compounds it silently; requiring `Tower:all` makes "yes, all of
them" a deliberate act rather than a name typed one selector short. The asymmetry must be **stated**
in the docs, since ruling 2 unifies these verbs' **output** and a reader will assume the input matches.
A duplicate/overlapping target set is **deduped before applying**, because `--by` is relative and
would otherwise double-apply (`surface.apply_surface_edit` already does this deliberately — carry it
forward).

`--to 0,0` clears the pan, which emits **no `Pan` line** (`unrealed/t3d.md` "A poly sub-field has NO
class default": an absent `Pan` ≡ zero; see the 2026-07-26 `emit` fix).

**It never touches `Origin`.** The precise safety claim — an earlier draft overstated this:

- `run` writes its continuity offset into the float `Origin`, so **a uniform `pan` applied to the
  whole run preserves continuity**;
- **panning a SUBSET of a run breaks it**, because those faces' U shifts relative to their
  neighbours. This is easy to do by accident, since the idiom is `poly find … | poly pan -` and
  `find` filters. Document it;
- **pan-then-align loses the nudge**: every `align` mode now writes `Pan = (0,0)` (§2.3, §2.4, §2.6),
  so a later align discards a dialled-in pan outright. Ordering is pan-**after**-align, and the docs
  must say so.

### 2.2 `brush poly rotate --by UU`

Rotates a face's `TextureU`/`TextureV` within the face plane, re-anchoring so the face's world
**centroid** keeps its `(U,V)` — the texture spins in place rather than sliding.

Targets are `BRUSH:SELECTOR` positionals or `-`, same grammar as `pan`; empty stdin is a clean no-op;
the target set is **deduped** (relative operation, same reason as `pan`). `--by` is the only form,
with deliberately **no `--to`** — but not for the reason an earlier draft gave. The codebase *does*
define a canonical frame (`builders._tex_basis(n̂)`), so "there is no zero to be absolute against" is
false. The real reason: an absolute texture angle would be measured against that basis, whose in-plane
orientation is an implementation detail no author can see or predict, so `--to 8192` would mean
something different per face normal. Reaching for a *known* orientation is what `align` is for. State
this in the help so nobody adds `--to` on the strength of the wrong argument.

- `--by` is in **unreal rotation units** (16384 = 90°), matching `brush build --rotate`,
  `mover key rotate` and the `level photo` pose grammar.
- **The sign is defined at the AXIS level, because that is the only form a test can assert**:
  a quarter turn is `U' = n̂ × U`, `V' = n̂ × V` (arithmetic, no trig). Concretely — and this is the
  assertion to pin — **on a `+Z` face with `TextureU=+X, TextureV=+Y`, `--by 16384` yields
  `TextureU=+Y, TextureV=−X`.**
  Note the drawn image rotates **with** the frame, not against it: under that same turn the texel
  formerly painted at world `(1,0,0)` is painted at `(0,1,0)`. (Pan is the field that inverts; a basis
  rotation does not.) An earlier draft of this spec asserted the opposite, and the prototype
  `poly_rotate.py` negates its angle — both are wrong and the axis-level rule above is authoritative.
- **Quarter turns are exact where the face normal is an exact unit basis vector.** Scoped
  deliberately: on a slanted face `n̂` is already an inexact float triple (a normalised cross
  product), so "no float dust" is unachievable there however the rotation is coded. Orthogonality of
  the frame is *not* required — each axis is rotated independently and exactly — but a naive **swap**
  of the two stored vectors is wrong whenever `|U| ≠ |V|`, since T3D carries the texel scale in the
  magnitudes. Detect `uu % 16384 == 0`, take the exact `n̂ ×` path, and assert exactness only for the
  axis-aligned case, which is the one that pollutes trunk diffs.
- **It writes `Origin`** — the centroid re-anchor cannot live in the integer `Pan` — and leaves `Pan`
  untouched. This is the counterpart to `pan`'s "never touches `Origin`" invariant.
- **`TextureU`/`TextureV` are assumed to lie in the face plane.** T3D does not require it, and
  `n̂ × U` silently annihilates any normal component, changing `|U|` and hence the texel density. A
  face whose stored axes have a normal component **exits 2 naming every such face** (a pre-pass over
  the whole set, before any write — `conventions.md` "A batch is all-or-nothing … collects *all*
  misses") rather than being silently projected. An exact-zero test would reject ordinary content,
  since `emit.clean`'s `CLEAN_EPS` snapping and a normalised cross product both leave dust, and the
  batch is all-or-nothing so one noisy face would kill the whole invocation.

  **The test is ABSOLUTE-OR-RELATIVE — SETTLED** by the step-1 plan
  (board item `brush-poly-rotate-turns-against-the-visible` §5) and durably recorded in
  `rationale/surface.md` ("`rotate`'s out-of-plane guard"). It supersedes both the `1e-3` and the
  relative-only `1e-2` that earlier drafts of this spec asserted:

  > **reject when `|axis·n̂| > max(TOL_ABS, TOL_REL·|axis|)`**, with
  > **`TOL_ABS = 3e-3`** and **`TOL_REL = 1e-2`**.

  A **relative-only** gate is broken on frames uedcli itself writes, which is why the plan measured
  it out. The two effects the gate sits between scale differently: the serializer noise is
  **absolute** (independent of the axis magnitude) while the harm is **relative**, so shrinking an
  axis raises its relative noise without raising the harm. `brush poly scale --by` (§2.5) shrinks
  axes on demand: after `--by 8,8` a unit axis is `0.125` long and the same absolute noise is
  `1.13e-2` relative — over a `1e-2` relative gate. `scale --by 8,8` followed by `rotate` would exit
  2 on a frame written one trunk round trip earlier.

  - **the noise, stated precisely.** `emit.clean` snaps **each component independently** when it is
    within `CLEAN_EPS = 0.001` of an integer, and `_vec_line` runs the texture axes through it. So
    the worst displacement of a whole axis is **up to `√3·CLEAN_EPS ≈ 1.7e-3` absolute** — all three
    components snapped, e.g. `(0.999, 0.001, 0.001) → (1, 0, 0)`. The worst *relative* figure is
    smaller than that bound implies, because the two are not simultaneously achievable: at the
    corpus minimum magnitude `0.6667` the component carrying the magnitude is nowhere near an
    integer and cannot be snapped, so at most two components move — **`√2·CLEAN_EPS = 1.41e-3`
    absolute there, i.e. at most `≈ 2.1e-3` RELATIVE at `0.6667`**. (The same two-component bound is
    what gives the `1.13e-2` figure above: `1.41e-3 / 0.125`.) `TOL_ABS = 3e-3` therefore clears the
    `1.7e-3` absolute ceiling with margin, and `1e-3` (the spec's first assertion) sits *inside* the
    noise — an earlier draft wrote that noise as `√3·0.001` relative at `0.6667` and got `2.6e-3`,
    mixing the two bounds.
  - **the harm.** `n̂ × U` shortens the axis by `√(1−ε²)` for a relative out-of-plane component `ε`,
    costing `ε²/2` of texel density — `5e-5` at `ε = 1e-2`, invisible — while a genuinely
    out-of-plane authored frame is `ε ≥ 0.05` (~3° of tilt). `TOL_REL = 1e-2` is the geometric
    midpoint of that gap, chosen from the harm side rather than from the observed ceiling.
  - the plan's measurement (max `4.135e-07` over 942 fixture axes) **confirms** the noise floor sits
    far below the threshold; it does not set it.

  **Pin BOTH branches** (§4.2): the relative branch on a unit-magnitude axis, and the absolute
  branch on a face that has been through `scale --by 8,8` — the crossover where a relative-only rule
  fails.
- **No continuity guarantee.** Applied across a run, each face pivots about its own centroid, which
  breaks the seams `run` matched — and equally breaks the shared world grid `wall`/`floor` stamp. This
  is the verb for a one-off face (a sign, a panel, a soffit). Document it, and note the contrast with
  `run --turn`, which is the run-aware operation.

### 2.3 `brush poly align wall | floor` — the editor's projection family, derived from world space

**Owner ruling 2026-07-26: `wall` and `floor` are WORLD-SPACE aligned in orientation AND anchor, and
they adopt the EDITOR's projection family** — `POLY TEXALIGN`'s `FLOOR`/`WALLX`/`WALLY`, measured in
§4b — rather than `builders._tex_basis`. The frame is a pure function of the face's **plane** and the
world axes: it does not depend on which other faces were selected, on which face came first, or on
anything the face carried before.

**Notation, used in this section and in §4b.** `N` is the face's unit outward world normal (computed
from its winding by `polyalign._world_normal`); `P` is any point of the face's plane and `d = N·P`;
`X̂ Ŷ Ẑ` are the world axes; and

> `proj(B) = B − N (N·B)` — the world axis `B` projected into the face's plane, **deliberately NOT
> renormalised**, so `|proj(B)| = √(1 − (N·B)²) ≤ 1`.

Each mode drops one world axis `A` (its **projection axis**), anchors the texture where the face's
plane crosses `A`, and builds the frame from the other two world axes projected into the face and
**negated**:

| mode | projection axis `A` | `TextureU` | `TextureV` | `Origin` | `Pan` | guard |
|-------------------|---------------------|------------|------------|-----------------|-------|---
| `floor` | `Ẑ` | `−proj(X̂)` | `−proj(Ŷ)` | `(0, 0, d/N.Z)` | (0,0) | `\|N.Z\| > 0.05` |
| `wall`, `A = X̂` | `X̂` | `−proj(Ŷ)` | `−proj(Ẑ)` | `(d/N.X, 0, 0)` | (0,0) | `\|N.X\| > 0.05` |
| `wall`, `A = Ŷ` | `Ŷ` | `−proj(X̂)` | `−proj(Ẑ)` | `(0, d/N.Y, 0)` | (0,0) | `\|N.Y\| > 0.05` |

**The axis assignment is NOT cyclic. Copy the table; do not derive it.** A cyclic rule would give
`A = Ŷ` the pair `(U ← Ẑ, V ← X̂)`; the editor's measured answer is `(U ← X̂, V ← Ẑ)`. Both wall rows
put `V` on `−proj(Ẑ)`, which is what makes V run *down* a wall in both. Measured over 396 (mode, face)
predictions; see §4b and `unrealed/texalign.md`.

**`wall` DERIVES its X-vs-Y choice — that is the one thing uedcli adds.** The editor makes the author
pick `WALLX` or `WALLY`; `wall` picks the world axis the face faces more: `A = X̂` when
`|N.X| ≥ |N.Y|`, else `A = Ŷ`. **The tie at `|N.X| == |N.Y|` resolves to the LOWEST axis index (X̂)**,
matching `builders._tex_basis`'s documented tie convention (its docstring, "Ties resolve to
the LOWEST axis index"). This is not a corner case to wave at: a wall yawed 45° is ordinary geometry
and hits the tie exactly, and Python's `max` is first-wins, so writing `max(range(2), key=…)` gives
the rule for free — but it must be **stated and pinned**, not left to `max`'s incidental behaviour.

**Density is `|proj|` — at most 1 — and the texture LOOKS stretched by `1/|proj|`.** These are two
different numbers and an earlier draft of this spec put the reciprocal in the density cell. T3D
carries texels-per-world-unit in the *magnitude* of the stored axis (`unrealed/t3d.md` "The UV
convention"), so:

- **stored:** `|TextureU| = |proj(B_u)| = √(1 − (N·B_u)²)`, where `B_u` is the world axis that row's
  U comes from — **the axis being PROJECTED, not the projection axis `A`**;
- **seen:** the apparent stretch is `1/|proj|`.

Measured (§4b): a 45° ramp `N = (0.7071, 0, 0.7071)` under `floor` gets `|TextureU| = 0.70711`
(= `√(1 − N.X²)`), i.e. it *stores* 0.707 and *looks* 1.41× stretched; a face `N = (0.211, 0.281,
−0.936)` under `WALLX` gets `|TextureV| = 0.35112`, a ~2.8× stretch. This is a planar projection — as
if the texture were painted on a plane perpendicular to `A` and shone onto the face — and it is
*useful*: a ramp's texture stays continuous with the flat floor it meets.

**Consequence: the reset-to-unit ruling binds `run` ALONE.** `wall`/`floor` are unit only on a face
square to their projection axis; `one-tile` (§2.6) derives its density from the face; `run` (§2.4) is
1 texel/uu unless `--fit-perimeter`.

**Using the brush-polygon normal where the editor uses the CSG surface normal is HARMLESS here — and
only here.** uedcli is model-side and has no BSP, so it has only the brush polygon's outward normal;
CSG reverses a subtractive brush's polygons, so on a room's inward-facing surfaces the editor's `N` is
the negation of ours (`unrealed/texalign.md` "The normal it uses is the SURFACE normal"). Both
quantities this family is built from are invariant under `N → −N`:

- `proj(B) = B − N(N·B)` — the two sign flips cancel;
- `d/N.A = (N·P)/(N·A)` — numerator and denominator flip together.

So `wall`/`floor` produce a **byte-identical frame** from either normal. That is **not** true of
`WALLDIR`, whose `TU = normalize(N.Y, −N.X, 0)` flips outright — which is one reason `WALLDIR` is not
adopted (§4b).

**A face failing the `|N.A| > 0.05` guard EXITS 2, naming EVERY failing face** — and this is a
deliberate divergence from the editor, which **silently skips** such a face and leaves it untouched,
pan included. `direction/conventions.md` "No silent half-answers" forbids that shape: a flag that
succeeds while doing nothing is indistinguishable from a broken one, and stderr scrolls away. The
guard is a **pre-pass over the whole set before any write**, collecting *all* offenders and reporting
the complete set — `conventions.md` "A batch is all-or-nothing … collects all misses and reports the
complete set, rather than … dying on the first". Each is named with its selector, its normal, and the
projection axis that failed, e.g. *"brush poly align floor: 2 faces are too close to vertical for a Z
projection — `Ramp:4` (|N.Z| = 0.031), `Ramp:5` (|N.Z| = 0.009); the 0.05 floor exists because a
texture projected down Z would be stretched past 20× and anchored thousands of uu away"*. Nothing is
written when any face fails.

**Why `conventions.md`'s calibrated exception does NOT apply here, since a mixed `poly find` result is
exactly how this set arrives.** That exception lets *a set member the verb structurally cannot act on*
(the canonical case: a point actor handed to a poly verb) be named on stderr and skipped. A
guard-failing face is not that: it is a poly, `align floor` can act on it, and the refusal is about
the *result* being useless rather than the *object* being the wrong kind. Two consequences follow.
First, "this actor has no polys" is a fact about the member alone, so skipping it leaves the rest of
the batch meaningful; "this face is 87° off horizontal" is a fact about the member **and the mode the
author chose**, so skipping it silently produces a set in which some faces moved and some did not,
with no way to tell which from the exit code. Second, the escape is already composable and needs no
flag: `brush poly find --facing +Z` filters the set by orientation upstream, which is what the
`find → mutate -` idiom is for. So: hard exit 2, complete list of offenders, nothing written.

Why the threshold matters rather than being a formality: `d/N.A` diverges as the face turns parallel
to `A`, and the 0.05 floor caps the multiplier at 20×. It is the face's offset *transverse* to `A`
that gets amplified — a wedge 1600 uu off-origin transversely at `|N.A| = 0.049` anchors ~32,600 uu
out, at the edge of UE1's ±32768 world (`unrealed/texalign.md`).

**This guard REPLACES `polyalign._check_orientation`**, the dominant-normal-axis
test that today rejects a face from `wall` iff its dominant axis is Z and from `floor` iff it is not.
The new guard is far more permissive: `floor` now accepts anything up to ~87° off horizontal.

**The coplanarity and co-orientation guards are DELETED** (the two `is not coplanar with` raises in
`polyalign._coplanar_align`). Decided here,
because a world-derived frame removes their whole motivation:

- the co-orientation guard existed because a coplanar face pointing the *opposite* way shared the
  seed's frame and would render the texture **mirrored** (that guard's own comment, `"would share the
  frame but render the texture MIRRORED"`, states exactly that). **The mirroring does not go away — a byte-identical frame is precisely what causes it**: the
  two faces are viewed from opposite sides, so one world→UV map reads reversed on the back one. What
  goes away is the *reason to reject it*. The editor's projection family is **polarity-blind by
  design** — `proj(B)` and `d/N.A` are both invariant under `N → −N` (§4b), so the family cannot
  express "which way this face points", and a world-axis grid has no notion of facing to begin with.
  Under a world grid, mirrored **is** the right answer: both faces read one continuous wallpaper, and
  a sheet of wallpaper seen from behind reads reversed. Rejecting that would be rejecting the family's
  defining behaviour, which ruling 9 adopts deliberately;
- the coplanarity guard existed because one seed frame was being stamped on a set, so a set spanning
  two planes was meaningless. There is no seed now: each face's frame comes from its own plane, and
  the *point* of the projection family is that faces on different planes still share one world grid
  (a whole floor at two heights; a wall run whose faces are not quite parallel). Keeping the guard
  would forbid the capability the ruling was reaching for.

So `wall`/`floor` are **per-face stamps and a set is simply a batch** — there is no set-level
relationship left to validate. What remains per face: the degenerate-face check (`_world_normal`) and
the `|N.A|` guard.

**Idempotence and set-independence, the property the ruling is for.** Identical *axes* are not
identical *frames* — phase lives in `Origin`, and today's `_coplanar_align` anchors on the seed face's
centroid (`base_w = _centroid(_world_verts(seed_actor, seed_poly))`), so two invocations over
different subsets of one plane give different
phases. With the world anchor, aligning face A alone and face B alone produces byte-identical frames,
and re-running over the same set changes nothing. Pin both directions (§4).

**No `--turn` and no `--fit-perimeter`** on these modes — structurally, via §2.0's subcommands.

⚠ **`wall`/`floor` are DESTRUCTIVE on imported content, and `usage.md` must warn at the point of use,
not in a footnote.** Real maps carry deliberate texel scales. Measured 2026-07-26 over a **precisely
stated population** — every `TextureU` line in the seven top-level `uedcli/tests/fixtures/*.t3d`
exports, 253 axes in all — **17 are non-unit**: 14 at exactly `0.6667` (= 2/3, authored, not float
noise), 2 at `0.9967`, 1 at `0.9762`. All 14 of the `0.6667`s come from the two **editor-exported**
maps (`level_small.t3d`, `brush_subtract.t3d`); uedcli's own builder output is unit throughout. (The
`intersect/` sub-tree adds 218 more axes and no non-unit ones, so widening the population to the whole
fixture tree gives *the same 17*, out of 471.)
Aligning imported geometry replaces those with the projection's own density and discards any
authored `Pan`. `brush poly scale` (§2.5) is the general control that puts a density back; `one-tile`
(§2.6) and `--fit-perimeter` (§2.4) reach non-unit densities too, but only for their own specific fits.

### 2.4 `brush poly align run [--turn UU] [--fit-perimeter]`

The generalisation of today's `--ring`. Walks a connected run of faces and lays one continuous texture
along it: U follows the run, V across it, phase accumulating along the run. Density resets to
**1 texel/uu** (owner ruling; this is the mode reset-to-unit binds), unless `--fit-perimeter` rescales
it. `Pan` is `(0,0)`.

**Phase accumulates by the CHORD between consecutive seam midpoints** — the straight-line distance,
not the true arc — and it is what makes the phase actually meet at the seam, since the anchor is a
point. Arc length would inject ~0.18 texels of error per seam on the spike's fixture. The chord
*magnitude* matches today's `--ring` (`usage.md`: "U advances by each facet's true chord
`2·r·sin(π/N)`", pinned by
`test_polyalign.py::test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n`) — but see the anchor
rule below, which does **not** match today's `--ring`.

**The anchor, stated separately from the advance** (an implementer porting `_ring_align` faithfully
would get this wrong, because today's code anchors at `start[0]`, the *low endpoint* of the seam edge
— `_ring_align`'s `base_w = _sub(start[0], …)`):

- the **along-run** phase anchors at the **seam MIDPOINT** — `U(midpoint) = accumulated chord`. The
  midpoint is what makes `half_width` the lever arm in the shear formula; anchoring at an endpoint
  would measure the inner-radius chord on a flat bend (100.4 uu instead of 112.92 on the fixture) and
  double the shear;
- the **across-run** zero keeps today's `--ring` RULE — an **endpoint** of the seam edge, the one with
  the lower projection on the across axis, never its midpoint. Deliberate: a midpoint anchor for both
  axes would move `V = PanV` to *mid-height* on every cylinder the tool has ever textured — half the
  texture above the anchor and half below — and `direction/conventions.md` singles out the T3D trees
  as the one place to think before changing, because a user's *content* lives there. An endpoint
  anchor keeps `V = 0` on a rim, so one texture height spans the run's cross section exactly.
  **Which** rim it lands on follows the across-axis DIRECTION settled in §2.4.2, and that direction
  changes: `run` adopts the spec-wide V-down convention, so on a cylinder the zero moves from today's
  bottom rim to the **top** rim and V grows downward. That is the intended fix, not a regression — a
  UE1 texture's `V = 0` row is its top (§2.6, `unrealed/texalign.md` `WALLDIR`), so today's V-up
  `--ring` renders an asymmetric texture upside-down, and `align wall` and `align run` on the same
  cylinder disagree. The cost is stated plainly: **re-aligning an existing cylinder wrap flips its
  texture vertically.** That is a change to how EXISTING CONTENT renders, so it is an owner narrowing
  and not an agent choice — **§7 narrowing 2**, parked on `board/inbox/`, documented per §4.3 and
  pinned per §4.2.
  **Which seam the zero is read from is settled below** ("Terminal faces and the across-run zero").

Both anchors are satisfiable by one `Origin`: two constraints, two in-plane degrees of freedom.

**The order the faces are passed in has NO bearing on the result.** Not the chain order, and not the
root either — owner ruling, 2026-07-26. Today's `--ring` requires the caller's whole input order to be
the chain order and errors otherwise; `poly find` emits poly-index order, which the author neither
controls nor sees, so any dependence on it is a hidden coupling. `resolve_align_targets`'s docstring
claim that "the ring seam is the first face" is therefore deleted with the behaviour.

#### 2.4.1 The PRE-WALK — eight steps, every one decided here

`run` derives everything from the set before aligning anything. The steps run in **this order**, and
the order is load-bearing: each one is what makes the next one's message specific instead of a
mid-walk surprise.

**1. Single brush, at least two faces.** A multi-brush set exits 2 naming the brushes (§6); a set of
fewer than 2 faces exits 2. Both carried over from `--ring`, with `--ring`'s cylinder wording dropped
(*"all faces must belong to ONE cylinder brush"* → one brush; *"need at least 2 side faces to form a
ring"* → two faces to form a run).

**2. World geometry, then the shared-edge ADJACENCY MAP.**

**First the per-face geometry every later step reads**: each member's world vertices and its **unit
outward world normal `n̂`** (`polyalign._world_normal`, which computes the normal from the winding and
already raises naming the face for a **zero-area** one). `run` needs `n̂` per face — for the across
axis `ĉ = ±(n̂ × t̂)` (§2.4.2) and for the written frame — so the degenerate-face check belongs here,
at the first step that computes a normal at all, and not scattered into the walk. It reports **every**
degenerate member, per `conventions.md` "a batch … collects all misses".

**Then adjacency.** Two faces are adjacent when they share an edge.
**Edge coincidence is a DISTANCE test, not bucket rounding**: two edges coincide when their endpoints
are within `_WELD` (0.5 uu) of each other, matched **unordered** (either endpoint to either). Note
`polyalign._edge_eq` (whose docstring reads *"Two vertical edges coincide iff their bottom endpoints
do"*) is NOT the rule to copy: it compares only the *bottom* endpoints of two axis-parallel edges,
which is valid only under the cylinder-axis assumption `run`
deletes. The spike prototype buckets coordinates (`round(p / 0.5)`), which mis-welds any pair
straddling a bucket boundary — a real risk on a revolve's off-grid vertices after `emit.clean`
snapping, and it would surface as a phantom fork or a phantom disconnection rather than as anything
obviously wrong. Do not port the prototype's version.

**The map stores THE SHARED EDGE, not a boolean.** Adjacency as a `bool` is not enough for anything
downstream: §2.4.2's tangent is `unit(exit_edge_midpoint − entry_edge_midpoint)`, the chord advance is
`|exit_mid − entry_mid|`, and the across-run zero is read off *the root's entry edge* — every one of
those needs the actual edge, so the map is `frozenset{face_a, face_b} → the shared edge` (as a pair of
world points). **A pair of faces sharing MORE THAN ONE edge exits 2**, naming the pair and both
edges: the entry/exit midpoints would be ambiguous and the chord could be measured two different
ways. It is not a theoretical case — two quads folded back onto each other along both of a pair of
opposite edges is a degenerate sliver a builder can emit — and silently picking the first match would
give a defined-looking but arbitrary phase.

**3. An edge shared by MORE THAN TWO faces exits 2**, naming **every** such edge with its faces (all
offenders, per `conventions.md` "a batch … collects all misses"). The set is not a surface strip and
no walk over it is defined.

**4. BRANCH CHECK — ONE error, and it ALWAYS carries the cap hint.** *Decided here; three earlier
attempts at a cap predicate all failed, and the third failure is why there is no predicate at all
now.* A run's phase cannot fork: at a junction it would have to be simultaneously consistent along two
continuations, and nothing picks which arm continues. So:

> Collect every member with **3 or more** neighbours in the set. If that collection is empty, continue
> to step 5. Otherwise the invocation exits 2, naming **every** collected member with its neighbour
> count, and **always** appending the actionable hint that must survive from `--ring`:
> *"face `BRUSH:idx` has N neighbours in the set; a run cannot branch — align each arm as its own set.
> If these are a cylinder's caps, exclude them:
> `brush poly find <brush> --item Side | brush poly align run -`"*.

**There is no cap PREDICATE.** The requirement was only ever that the `--item Side` hint reach the
author — `test_ring_rejects_cap_face` is re-derived against this message (§4.1) and asserts **the
hint**, not a classification — and appending it unconditionally satisfies that at zero cost. Three
attempts to *decide* cap-vs-branch first, and why each is rejected:

- the **first** tested each member's normal against its neighbours' run tangents and was **backwards
  in both directions**: a cylinder cap's normal is the axis while the side tangents are tangential, so
  `n̂·t̂ = 0` and the cap *passed*; while for a legitimate side face `n̂_k · t̂_{k+1} = sin Δθ` = 0.707
  on an 8-gon, so **every real side face** was rejected as a cap;
- the **second** keyed on the shared edge being parallel to the neighbour's **run tangent** — but the
  run tangent only exists *after* the walk this check is supposed to gate. It is not computable where
  it is needed;
- the **third** was pure adjacency: report a member as a cap when its degree is `|set| − 1`, or when
  ≥ 3 of its shared edges are pairwise non-opposite. It **misfires in both directions**. `|set| − 1`
  is a set-size coincidence, not a cap test: a genuine 4-face T-junction satisfies it and is announced
  as a cap; a tetrahedron reports all four faces as caps; and a square prism selected with **both**
  caps satisfies neither disjunct, so its caps go undetected — and a bare
  `brush poly align run <Box>` is exactly that set, which §2.1's target grammar explicitly allows. The
  second disjunct is dead weight besides: any 3 of a quad's 4 edges contain an opposite pair, so it
  reduces to "a non-quad of degree ≥ 3".

The first two were geometric, and the geometry they need is exactly what `run` gave up when it stopped
being cylinder-only; the third bought a distinction it could not draw correctly. Adjacency alone
answers the question that actually matters — *does the phase fork here* — and one honest message with
the hint attached is strictly more useful than two messages, one of which is sometimes a lie.

**What this reads like on the flagship fixture** (`test_ring_rejects_cap_face`: an 8-sided cylinder's
8 sides plus one cap): the cap has degree 8 and each side has degree 3, so *every* member is collected
and all nine are named with their counts, followed by the `--item Side` hint — which is precisely the
next command the author should run. A T-junction in a quad strip reports the one degree-3 face and the
same hint, which there is merely inapplicable rather than wrong.

⚠ **Accepted narrowing, stated so it is not discovered later: a cap that does NOT branch is not
detected.** Select a 4-sided prism's cap plus only 2 of its sides and the cap has degree 2 — a legal
path, walked as an ordinary run member with a 90° corner in it. The old geometric guard would have
caught it. This is the price of a check that works on coplanar runs at all, and the attempts above are
the evidence that the alternative is not available. A non-branching cap produces a defined (if odd)
alignment rather than a wrong-looking silent one, and the `--item Side` idiom the docs teach avoids it.

**5. CONNECTIVITY VALIDATION.** *Decided here.* The adjacency graph must be a **single connected
component that is a simple path or a simple cycle**; anything else exits 2 naming the members of every
component after the first. After step 4 every member has degree ≤ 2, and a connected graph with
maximum degree 2 **is** a simple path or a simple cycle — so the only remaining failure is
disconnection, and the check reduces to one component count. Both cases it catches are silent
otherwise:

- **two disjoint chains** give four degree-1 ends and no branch, so the branch check passes and root
  selection would quietly pick one chain's end and align only that chain (or, worse, walk one chain
  and leave the other's frames untouched with no error);
- **an isolated face** has degree 0, matching neither "two ends" nor "no ends"; it is a component of
  size 1 and is caught by the same count. (A single-face *set* is already rejected at step 1.)

**6. NON-QUAD REJECTION** — every member must have exactly 4 vertices, else exit 2 naming **every**
non-quad member (§6). **It comes after steps 4–5 deliberately:** a cylinder cap is an N-gon, so a
non-quad check placed earlier would report the flagship fixture's cap as "not a quad" and the author
would never see the `--item Side` hint that `test_ring_rejects_cap_face` pins. That ordering argument
survives step 4's simplification unchanged — the hint now rides on *every* branch error, but it still
rides on no non-quad error.

**7. ROOT SELECTION AND WALK DIRECTION, entirely derived.** Both must be stated: a root alone leaves
a closed run's two continuations undecided, and picking the wrong one reverses U on every cylinder the
tool has ever wrapped.

- an **open** run has exactly two degree-1 ends; the root is the one with the **lower poly index**,
  and the direction is forced (an end has one neighbour);
- a **closed** run has no ends, so the root is the **lowest poly index in the set**. Its two
  neighbours both have higher indices — it is the minimum — so the tie is broken between *them*:
  **the walk LEAVES the root through the seam it shares with the LOWER-indexed of its two
  neighbours**, and the root's **entry** seam (where phase zero sits, §2.4.2) is the other one, shared
  with its higher-indexed neighbour. That seam is also the **open** seam the run deliberately leaves.

  Concretely on the shipped case — an 8-sided cylinder whose side polys are consecutive in index
  order, `0 … 7` — the root is `0`, the walk goes `0 → 1 → … → 7`, **U increases with poly index**, and
  the open seam stays `7 | 0`, exactly where `--ring` puts it today (`find_faces` emits poly-index
  order and `_ring_align` walks that order). The opposite choice — leaving toward `7` — would reverse
  U on every existing wrap and move the open seam to `0 | 1`. Nothing in the shipped suite would catch
  that: `_assert_seam_continuous`, the per-facet U-span assertion and the closing-gap measurement are
  all direction-agnostic, which is why §4.2 adds a direction pin.

**8. WALK** from the root in the direction step 7 fixed, which fixes the phase zero, the entry seam
and the frame — all reproducibly, from geometry and poly index alone.

**Consequence, stated because it is a real change:** the author can no longer place the seam of a
closed run, which input order allows today. Accepted deliberately — `--fit-perimeter` makes the
closing seam exact, so on the shipped cylinder workflow the seam's position stops mattering, and a
determinism that cannot be perturbed by an upstream filter is worth more than the control it replaces.
There is deliberately **no `--seam` flag** (owner ruling 2026-07-26).

#### 2.4.2 Tangents, terminal faces, and where phase zero sits

**The per-face run tangent is `unit(exit_edge_midpoint − entry_edge_midpoint)`** — stated because it
is load-bearing and only coincides with an endpoint-derived tangent on a cylinder; take endpoints on a
flat bend and the phase stops meeting. Each face's chord advance is `|exit_mid − entry_mid|`, and the
accumulated chord at a face's entry edge is that face's `U` there.

**Terminal faces of an open run — decided here.** An end face has only ONE seam, so its tangent, its
chord and (for the root) its phase zero are otherwise undefined:

- **the FAR EDGE of a terminal face is the quad edge OPPOSITE its single seam** — index `(i+2) mod 4`
  in the face's vertex ring — and **its midpoint substitutes for the missing seam midpoint** in every
  formula above. This is precisely why the quad assumption is load-bearing and why a non-quad face is
  a hard error (§6, step 6 above): on a general polygon "the far edge" has no definition;
- the **root** takes its far edge as its **entry** edge (so the walk leaves through its seam) and the
  **last** face takes its far edge as its **exit** edge;
- **the root's phase zero sits on its FAR EDGE**: `U(far-edge midpoint) = PanU = 0`, and the chord
  accumulates from there. This **matches today's `--ring`**, which sets `start` to the edge *not*
  shared with the next face and anchors `U` there (`_ring_align`'s `if pos == 0:` branch picks the
  free edge; its `base_w = _sub(start[0], …)` anchors on it) — the only change is endpoint → midpoint, per the anchor rule
  above. On a **closed** run there is no free edge and phase zero sits on the root's entry seam.

**The across-run zero comes from the ROOT's ENTRY edge, once — decided here.** It is the endpoint of
that edge with the lower projection on the across axis (the root's far edge on an open run, its entry
seam on a closed one), and `V` at that point is `PanV = 0`. Every **other** face gets its `V` phase by
**continuity across its entry seam** with its predecessor, not by re-deriving a low endpoint of its
own. The two rules agree on a cylinder and on a symmetric bend — the rim the zero lands on reads the
same V from either face — which is why today's per-face derivation (`_ring_align` recomputes
`base_w` from each face's own `start[0]`) has never shown the difference. They **disagree** whenever the run's cross
section changes along it, and there the propagated version is the one that keeps V continuous, which
is the property `run` exists to provide. Fixing it at the root also makes it order-independent by
construction.

**The across-run axis DIRECTION, stated as a convention — decided here**, because the cylinder axis
that supplied it is gone and `--ring`'s "+Z-ish" tie-break (`_ring_align`'s `Oriented +Z-ish for
determinism` comment and the `if _dot(axis, (0, 0, 1)) < 0 …` line under it) does not survive the
generalisation. The axis itself is forced: the across direction `ĉ` is the unit vector perpendicular
to both `n̂` (face normal) and `t̂` (run tangent), i.e. `ĉ = ±(n̂ × t̂)`. Only the **sign** is a choice,
and `--ring`'s does not work on the case this spec exists for: on a **flat** run `n̂ = ±Ẑ` and `t̂` is
horizontal, so `ĉ` is horizontal, `ĉ·Ẑ = 0`, and "+Z-ish" disambiguates nothing at all — the sign
would fall through to whatever `n̂ × t̂` happened to give, which is the **walk direction**, a thing the
author cannot see or predict. The convention instead is:

> **`ĉ` points along the NEGATIVE side of its OWN largest-magnitude world component.** Concretely:
> take either candidate `c = n̂ × t̂`, let `k` be the index of its largest-magnitude component
> (`|c.X|`, `|c.Y|`, `|c.Z|`), **ties going to the lowest axis index**; then `ĉ = c` if `c[k] < 0`,
> else `ĉ = −c`. The result has `ĉ[k] < 0`.

**There is no epsilon.** `ĉ` is a unit vector, so its largest component is at least `1/√3 ≈ 0.577`
and the sign test on it is never near zero — the rule is a strict comparison with nothing to
calibrate. (An earlier draft ranked the world axes in a fixed `Ẑ`-then-`Ŷ`-then-`X̂` priority and
took the first with a "non-negligible" component. That rule needed a tie epsilon it never gave a
value to, and worse, it is **discontinuous on exactly the geometry this mode exists for**: on a bed
travelling `+X̂` the two candidates are `(0, +0.9999, −0.01)` and `(0, −0.9999, +0.01)`, and the `Ẑ`
test picks the first where the `Ŷ` test picks the second — so a dead-flat bed and one with ~0.6° of
grade come out with V mirrored. A gently ramping curve is ordinary geometry.)

It is still §2.3's projection family read off its own table, only keyed on the vector's own dominant
axis rather than on a fixed axis order: `wall` puts `V = −proj(Ẑ)`, `floor` puts `V = −proj(Ŷ)` and
`U = −proj(X̂)` — every one of them the *negative* side of the axis concerned. It reproduces both
shipped cases exactly: on an upright cylinder `ĉ = ±Ẑ` and the rule gives `−Ẑ` (`wall`'s V); on a
flat bed travelling `+X̂`, `ĉ = ±Ŷ` and the rule gives `−Ŷ` (`floor`'s V).

**Where its own discontinuity is, stated plainly.** The chosen sign flips when the two
largest-magnitude components of `c` are equal in magnitude **and opposite in sign** — i.e. 45° away
from every world axis. (When the tied components have the *same* sign both branches negate to the
same vector, so an equal-magnitude tie is only a discontinuity for the opposite-sign case.) That
sits far from both shipped cases: a cylinder gives `ĉ = ±Ẑ` exactly and a flat bed `ĉ·Ẑ = 0`
exactly, so neither is anywhere near it, where the rejected rule's discontinuity sat **at** the flat
bed. And because the sign is evaluated **once, at the root** (below), a run that sweeps through 45°
mid-way — a flat bed turning a 90° bend does — never re-evaluates it; only two *root* faces
differing by an infinitesimal rotation across that 45° would come out mirrored relative to each
other. It satisfies all four things the mode needs:

- **well-defined on a flat run** — `ĉ` is horizontal, its largest component is `Ŷ` on a bed
  travelling `+X̂` (or `X̂` on one travelling `+Ŷ`), and the sign test on that component decides;
- **V runs DOWN**, matching `wall`, `floor` and `one-tile`, so a top-row-first UE1 texture renders
  upright and `align wall` and `align run` on one cylinder no longer disagree by 180°. (On a
  *vertical* `ĉ` — a cylinder side, a wall run — "the negative side of the dominant axis" IS
  literally downward; on a horizontal `ĉ` — a floor run — "down" means `floor`'s `−proj(Ŷ)` /
  `−proj(X̂)`, which is the same convention read on the axis that applies);
- **independent of the walk direction** — reversing `t̂` flips `n̂ × t̂`. The component *magnitudes*
  are unchanged, so the dominant axis `k` is the same one, and the sign test on `c[k]` flips the
  choice straight back: `ĉ` is unchanged. (`U` runs *along* the walk, so it does follow it; that is why
  step 7 derives the direction rather than leaving it to the geometry. What this bullet buys is that
  the across axis cannot be flipped by it, so a run and its mirror image are not textured
  upside-down relative to each other);
- **invariant under `n̂ → −n̂`**, for the same reason, so a **subtractive** brush's inner wall gets the
  same frame as the identical additive geometry. `run` is therefore polarity-blind exactly as
  `wall`/`floor` are (§2.3, §4b).

**Handedness follows from that and is not separately chosen.** `TextureU` runs along `t̂` and
`TextureV` along `ĉ`, so `U × V = ±n̂` — which sign depends on which way the polygon happens to face.
That is inherent to a polarity-blind family and is NOT a defect to fix: the editor's own family is the
same (`FLOOR` gives `U × V = +N` on a floor and `−N` on a ceiling, and `WALLY`'s axis pair is the
opposite hand from `FLOOR`/`WALLX` by construction — see the "not cyclic" note in §2.3), so "match the
editor's handedness" is not a well-posed target and this spec does not claim it. The visible
consequence, stated once and documented: **on a face read from its back side — a subtractive brush's
inner wall, the routine case for a curved corridor — U appears mirrored, while V still runs down.**
Identical to what `wall`/`floor` do on the same geometry (§2.3's co-orientation bullet), so a run and
the walls around it stay consistent with each other.

The chosen sign is **fixed once at the root and propagated along the walk** by V-continuity across
each seam, never re-derived per face. A per-face world test would flip mid-sweep and mirror V at
that seam on any run whose across axis `ĉ` sweeps through the 45° discontinuity above — and the
motivating fixture does exactly that: on a **flat bed turning a 90° bend**, `n̂ = ±Ẑ` is fixed while
`t̂` rotates, so `ĉ` rotates with it from `∓Ŷ` to `±X̂` and passes through `(−0.707, 0.707, 0)`
half-way, where the two largest components tie with opposite signs. Fixing the sign at the root and
propagating it is what keeps V continuous across that point. Seam continuity alone does not pin any
of this (a cylinder aligned upside-down and backwards is equally continuous), so it needs its own
assertions (§4.2).

#### 2.4.3 `--turn UU`

`--turn UU` applies a uniform **rigid** turn in each face's own **run frame**, not in world space, so
every face receives the same transform relative to the run and the along-run density follows the
along-run direction into whichever stored slot it lands in. The chord advance is accumulated as a
displacement vector in the face plane and expressed in the rotated basis, so it distributes across
both axes. Units are unreal rotation units (16384 = 90°), matching `rotate --by`.

**Non-quarter `--turn` is ALLOWED, and its cost is GEOMETRY-DEPENDENT, not angle-dependent.**

- On a **cylinder-style run** (seam parallel to the turn axis) a turn costs nothing: both axes stay
  exact at every angle. Measured on an open 7-face cylinder sub-run — ΔU = ΔV = 0.000000 at turns 0,
  8192 and 5000.
- On a **flat bend** (seam in the plane of the turn) exactly one axis is continuous at multiples of a
  quarter turn and **neither** at any other angle; the mismatch vector rotates
  (`ΔU = d_u·S·|cos θ|`, `ΔV = d_v·S·|sin θ|`, verified 8.87/8.87 at 8192).

So a warning or rejection keyed on "the turn is not a quarter" would be **wrong for the only case
that ships**. **Ruling: allow any angle, document the redistribution in `usage.md`, and have `run`
report the seam shear to stderr** — where that figure is **MEASURED from the written frames** (the
`seam_check.py` computation), never evaluated from the closed form, which does not apply to cylinder
runs or to compound bends. The report **excludes the closing seam of a closed run**, which is
deliberately left open and measures the full perimeter (1567.47 on the spike's cylinder) — printing it
as "worst-case shear" every time would be noise, not information.

#### 2.4.4 `--fit-perimeter` — BROKEN as shipped, fixed in this change

It is documented as giving "an exact seam meet" and does not: it snaps the total U advance to a whole
number of **texels** (`target = max(1, round(total_chord * density_u))` in `_ring_align`), but a
texture repeats every **T texels**. Measured on the standard 8-sided R=256 cylinder with a 256-wide
texture:

| | total U advance | visible mismatch (mod 256) |
|--------------------------|-----------------|---
| default (leave the seam) | 1567.472357 | 31.47 texels |
| `--fit-perimeter` today | 1567.000187 | **31.00 texels** |
| corrected (whole tiles) | 1535.999876 | **0.0001 texels** |

So it removes 0.47 texels of a 31.47-texel error. **The corrected rule is
`target = max(1, round(total/T))·T`** — a whole number of TILES (owner ruling 2026-07-26) — with the
`max(1, …)` clamp the shipped code already carries for a reason: `round(total/T)` is 0 for any run
shorter than half a tile, giving density 0 and a zero-length `TextureU`, which
`builders._tex_basis`'s docstring says *crashes REBUILD*.

**`T` is the pixel size of the axis the along-run advance LANDS IN**, not always the width: at
`--turn 0` that is the texture's `USize`; at `--turn 16384` the advance sits in V, so it is `VSize`.
Non-square textures are real (the texalign spike's own fixtures are 256×64 and 128×256), so using
`USize` unconditionally is a 4× error on exactly the case the quarter-turn note was added to protect.
At a quarter turn `--fit-perimeter` fits the **along-run** axis regardless of which stored axis
currently holds it — fitting the axis merely *called* U would be silently wrong.

The catalog records both (`texture_catalog.TextureEntry` carries `width`/`height`,
the `TextureEntry` dataclass), so it resolves offline — but it means `align run --fit-perimeter`
**requires a resolved project and a synced catalog**, and exits 2 naming what is missing for: a texture
absent from the catalog, a face with **no** texture at all (every freshly built brush), a run whose
faces carry **different** textures (one density cannot satisfy two), or no catalog at all. Prototyped
and measured by `spikes/2026-07-26-poly-rotate-curved-track/fit_demo.py`.

**The plumbing seam must be specified, because `polyalign` has no project context today** (it is
documented as pure model-side texture-vector math taking only a `Level`). The CLI layer resolves
`(USize, VSize)` for the run's texture and passes it into `polyalign`; `polyalign` does **not** import
`texture_catalog`. That also gives the unit tests their injection point — every existing
`test_polyalign.py` fixture builds a bare `Level` with no project, so without an injectable size the
§4 fit-perimeter pins are not implementable at all. This is the **same dependency `one-tile` and
`scale --to` need**, so the coupling is not new to them: `--fit-perimeter` has needed it since it
shipped and has been quietly wrong without it.

**`--fit-perimeter` requires a CLOSED run and a quarter `--turn`**, exiting 2 naming the offending
value otherwise. **Both guards ship in step 4** (§4.4), with `--turn` and with open runs — the two
things that make either failure reachable:

- on an **open** run — the flag snaps the density so a whole number of tiles closes the loop, and a run
  with no closing seam has no loop to close. Fitting a texture to an *open* run is a legitimate but
  **different** operation (and would want a different flag name); filed to `board/inbox/` rather
  than folded in here;
- at a **non-quarter** `--turn` — the advance then splits across both stored axes
  (`ΔU = d_u·S·|cos θ|`, `ΔV = d_v·S·|sin θ|`), so closing the loop would need *both* components to
  land on tile boundaries, which scaling one density cannot achieve. Silently fitting one is exactly
  the half-answer `direction/conventions.md` forbids.

#### 2.4.5 What `run` accepts that `--ring` does not

**Coplanar sets are valid.** Today's `--ring` rejects them (*"all faces are parallel — not a ring"*,
`_ring_align`'s `all faces are parallel — not a ring` raise); that rejection is deleted. Note this does **not** collapse `run` into
`wall`/`floor`: on the same coplanar set, `floor` yields one shared world grid (texture straight
across) and `run` a turning frame (texture follows the curve). Both are wanted; they are different
operations on the same input, and the curved track bed is the case that needs `run`.

**Closed runs are supported.** Not optional: the wrap-a-cylinder workflow
(`poly find Tower --item Side | poly align run -`) is the only `--ring` use that ships, is documented
in `usage.md` and `architecture.md`, and is covered by eight `test_ring_*` tests.

**There is NO seed, and `--fresh-frame` is DELETED from `brush poly align` entirely.** `--fresh-frame`
existed only to choose between a canonical frame and adopting the seed's density/pan; with adopt-seed
gone from every mode it is a flag with one possible value, so per "No back-compat cruft" it goes.

### 2.5 `brush poly scale (--to U,V | --by FU,FV)`

The fourth canonical surface op, pulled into this change on the owner's 2026-07-26 ruling. After
reset-to-unit it is the **only general way to express a texel density**: `one-tile` fits one tile to a
face, `--fit-perimeter` closes a loop, and `wall`/`floor` take whatever the projection gives — none of
them lets an author say how big a texture should be.

Targets are `BRUSH:SELECTOR` positionals or `-`, same grammar as `pan`/`rotate`; `-` is the sole
source; empty stdin is a clean no-op; the target set is **deduped** (`--by` is relative and would
otherwise compound).

- **`--by FU,FV` multiplies the texture's APPARENT SIZE**, so `--by 2,2` makes the texture look twice
  as large. Note that this *divides* the stored magnitudes (`|TextureU| ← |TextureU| / FU`), because
  T3D density is texels-per-world-unit — a bigger magnitude means a smaller-looking texture. The verb
  is named for what the author sees, not for what is stored, and the help must say so or the sign of
  the effect will surprise everyone once. **Pure math, no catalog needed** — which is why `--by`
  builds in step 1 and `--to` waits for the catalog step.
- **`--to U,V` sets the absolute scale in WORLD UNITS PER TILE** — `--to 128,128` means the texture
  repeats every 128 uu each way, which is how a level designer thinks about it. This needs the
  texture's `W`/`H` from the catalog (`|TextureU| = W / U`), the same dependency `one-tile` and
  `--fit-perimeter` carry; a texture missing from the catalog, an untextured face, or no synced
  catalog each **exit 2 naming what is missing**.
- **Non-uniform is allowed** — U and V scale independently, which is what makes it the general control
  `one-tile`'s stretch is a special case of.
- **Re-anchored on the face centroid**, exactly like `rotate`: the face's world centroid keeps its
  `(U,V)`, so the texture scales *in place* rather than sliding off. It writes `Origin` and
  `TextureU`/`TextureV`, and leaves `Pan` alone.
- **A zero or negative factor exits 2** — a zero-length texture vector crashes REBUILD
  (`builders._tex_basis`).
- **No continuity guarantee**, and more strongly than `rotate`: scaling **breaks a run even when
  applied uniformly to all of it**, because each face re-anchors about its own centroid while the run's
  phase offsets were computed for the old density. Scale before `align run`, not after. Document it
  next to the pan-after-align rule in §2.1.

### 2.6 `brush poly align one-tile`

Fit **exactly one tile of the texture to each face** — the sign / monitor / light-panel case. Owner
ruling 2026-07-26: `one-tile` is **FIT TO THE POLY**, where `wall`/`floor` are world-space. Those are
two different things and the difference is the point: world-space means the frame ignores the
individual face entirely; fit-to-poly means it is derived from that one face.

- **Per-face and independent.** Each face gets its own density and anchor; there is no shared frame
  and no continuity between faces. That is why it is its own mode rather than a flag on `wall`/`floor`,
  which would imply a shared frame it structurally cannot provide.
- **No orientation guard.** Unlike `wall`/`floor` it accepts **any** face orientation — a sign goes on
  a slanted face as happily as a vertical one.
- **Orientation uses the EDITOR'S PROJECTION DIRECTIONS, ORTHOGONALISED** — owner ruling 2026-07-26,
  extending §2.3's family to this mode so all three world-oriented modes share one up-vector
  convention. Project along the world axis `A` of **maximum** `|N.A|` over all three (ties to the
  lowest index, matching `_tex_basis`'s documented convention, its docstring), take the
  `TextureU`/`TextureV` pair from §2.3's table for that `A`, then build an **orthonormal** frame from
  them and set the magnitudes from the fit below.

  **Normalising alone is NOT enough, and this is a measured defect the owner ruled on 2026-07-26.**
  The two projected axes are not perpendicular to each other:
  `proj(B₁)·proj(B₂) = −(N·B₁)(N·B₂)`, which is zero only when the normal is square to one of the two
  axes being projected. On a corner face `N = (0.577, 0.577, 0.577)` the pair comes out **120° apart**
  — a 30° shear on a sign — and the anchor misses too: the fit spans `U ∈ [−85.33, 170.67]` instead of
  `[0, 256]`, because with skewed axes the "minimum corner" of the extent is not a vertex of the face.
  **Where those numbers come from:** `spikes/2026-07-26-poly-rotate-curved-track/uv_preview.py`, its
  `onetile-skew` scene — `frame_one_tile(corner, orthogonalise=False)` on the triangular corner face
  `[(256,0,0), (0,256,0), (0,0,256)]` with a 256×256 texture. The same call with
  `orthogonalise=True` (the `onetile-ortho` scene) returns exactly `[0, 256]` on both axes.
  Re-computed 2026-07-26.

  > **Owner ruling 2026-07-26: ORTHOGONALISE by GRAM-SCHMIDT of U against V.** Keep `V` exactly as
  > the table gives it — that is the predictable up-vector the whole mode exists for — and square `U`
  > to it:
  >
  >     V̂ = normalize(−proj(B_v))
  >     Û = normalize(−proj(B_u) − V̂ ((−proj(B_u)) · V̂))
  >
  > **Rejected: `U = V × N`.** It also produces an orthogonal frame, but it picks its own sign rather
  > than inheriting the table's, so it mirrors the image on half the face directions — the one failure
  > this mode must not have.

  Verified: Gram-Schmidt returns the pair to **90°** on that same corner normal and the fit to an exact
  `[0, 256]²` span. On any face where the pair is already perpendicular (every axis-aligned face — the
  common case) `Û` is unchanged, so this costs nothing where nothing was wrong.

  Why not `_tex_basis(n̂)`: it seeds from the world axis *least* aligned with the normal, which fixes
  no up-vector an author can predict — so a sign could render sideways or upside down, failing the one
  use case the mode exists for. The projection convention gives `TextureV = −proj(Ẑ)` on a wall, i.e.
  `−Ẑ` on a vertical face: V increases *downward*, matching the image-row convention, so a texture
  authored top-row-first renders upright. Normalising is what makes this safe to borrow — the `|proj|`
  shrink `wall`/`floor` inherit is discarded here, because `one-tile` supplies its own density — and
  orthogonalising is what makes the *fit* mean what it says.
  Choosing the **maximum** `|N.A|` (rather than §2.3's per-mode axis) means the guard can never fire:
  a unit normal always has some `|N.A| ≥ 1/√3 ≈ 0.577`, so `one-tile` keeps its "any face orientation"
  promise without an exception.
- **It STRETCHES to fill, non-uniformly.** One tile spans the face's U extent and one tile its V
  extent, so the image fills the face exactly and is distorted when the aspect ratios differ. That is
  the point: a letterboxed sign is wrong, and authors size the brush to the sign or vice versa.
  Aspect-preserving fit is a different operation and belongs to `brush poly scale` (§2.5), where U and
  V density are set explicitly.
- **Anchor: the MINIMUM corner of the face's extent** measured along the chosen U/V axes (the min of
  the vertices' projections). Texture `(0,0)` lands there, so the tile covers the face's bounding box
  exactly. Deterministic, because the axes are a pure function of the normal — and **exact only
  because the frame is orthonormal**: on a rectangular face square to the axes the minimum corner is a
  vertex and the four corners map to `(0,0)`, `(W,0)`, `(W,H)`, `(0,H)`. Under the skewed pair the
  ruling above replaces, that was not true and the fit overshot its own tile. Rejected: centroid
  anchoring, which needs a half-extent offset to mean the same thing and is harder to reason about.
- **`Pan` is `(0,0)`**, like every other mode.
- **On a NON-RECTANGULAR face** (a triangle, a trapezoid, a cap tile) the tile covers the *bounding
  box*, so the face shows a sub-region of the texture. Documented, not discovered.
- **Requires the texture catalog**, for the same reason `--fit-perimeter` does: `|TextureU| = W / E_u`
  needs the texture's pixel size. Exit 2 naming the ref when it is not in the catalog, naming the face
  when it carries no texture or has a zero extent along either axis — and, because a batch is
  all-or-nothing (`conventions.md`), **as one pre-pass reporting the COMPLETE set of offenders**, not
  the first one hit. A `poly find` result over a whole brush routinely contains several untextured
  faces at once, and fixing them one exit-2 at a time is the failure mode that rule exists to prevent.

Open, flagged rather than decided: `one-tile` is arguably a **scale** operation wearing an align hat —
it sets density and anchor, not a shared frame — so it overlaps `brush poly scale` (§2.5). Kept under
`align` because the author's intent is "make this texture fit this face", which is alignment.

**`one-tile` is a uedcli INVENTION, not a port.** UnrealEd 2.2's `ONETILE` is a **no-op** (§4b), so
nothing in the editor constrains this design and it stands or falls on its own merits.

### 2.7 Frame construction for `run`, and what it costs

Orthogonal axes, phase measured on **one reference radius (the centreline)**.

**Where the seams are exact, and where they are not** (spike findings 4–5, and the round-1
correction):

- **A run whose seams are parallel to the turn axis — cylinder sides — is EXACTLY continuous on both
  axes, at every `--turn` angle.** Measured on the shipped `--ring` (all 7 interior seams of a closed
  8-sided cylinder, ΔU = ΔV = 0.000000) and on an open 7-face sub-run at turns 0, 8192 and 5000
  (same). `run` must preserve this.
- **A run whose seams lie IN the plane of the turn — a flat bend, like the track bed's top — shears
  one axis** by `S = 2·sin(Δθ/2)·half_width` world units, appearing on each stored axis scaled by
  **that axis's own density**: `ΔU = d_u·S·|cos θ|`, `ΔV = d_v·S·|sin θ|`. **`half_width` is HALF the
  seam edge's length** — the distance from the phase reference (that seam's midpoint) to either of its
  endpoints, which by construction are the same. It is therefore a **per-seam** quantity, not a
  property of the run: a run whose cross section varies along it (a bed that widens through the bend)
  shears differently at every seam, and the figure to quote — in the stderr report and in a test — is
  the **widest** seam's. The other axis is exact at **multiples of a
  quarter turn** (`--turn 0` included, which is the default and the case §4 tests). This also assumes
  a **uniform** per-facet turn — the seam must bisect it; unequal turns break the even-cosine
  cancellation that makes the exact axis exact.

**What this means for corners, which is the first thing an author will ask.** The discriminator is the
seam's orientation relative to the turn, not how sharp the turn is — so a 90° corner can be perfect or
unusable depending only on which way the seam runs:

| run | seam vs turn | seam mismatch, and where the number comes from |
|-----------------------------------------|-------------------|---
| L-shaped **wall**, 90° corner | ∥ the turn axis | **ΔU = ΔV = 0.000000** — MEASURED, at `--turn` 0 and 8192 |
| flat bend, Δθ = 45° (2-segment revolve) | in the turn plane | ΔU = 48.98 — MEASURED (48.983561, against a closed form of 48.983) |
| flat **L**, Δθ = 90°, 128 uu wide | in the turn plane | ≈ 90.5 texels — **CLOSED FORM ONLY, extrapolated; never measured** (`2·sin(45°)·64`) |

A wall run turning a corner is exact and needs no compromise. A **flat** corner is the pathological
case: ~90.5 texels of shear out of a 256-texel texture, at one seam — a *predicted* figure, since the
flat-L fixture was never built, but predicted by the one closed form the two rows above it confirm to
five decimal places. Unlike a revolve it cannot be
improved by adding segments, because Δθ is fixed by the corner itself. This is what the stderr shear
report is for: on a flat L it prints ~90 and tells the author to mitre the corner or accept a visible
seam, at the moment they need to know.

Any **degree-2 chain** runs, including the minimal two-face case (two faces, one seam, both ends —
each of which is a terminal face per §2.4.2).

The alternative — a sheared, non-orthogonal frame — is exactly continuous on **both** axes but
stretches by `√(1+ψ²)` (86% at the end of a 90° bend) and skews the frame to 34°, and **neither
degradation is reducible by segmentation**, whereas the orthogonal frame's shear halves with every
doubling of `--segments`. Measured both ways; see finding 5.

## 3. Decisions

### 3.1 Owner rulings (all 2026-07-26)

The complete set. Rows 1–6 were made in the first session and are parked verbatim on
`board/inbox/` under *"The per-surface verb split"*; rows 7–13 followed and are parked under
*"SEVEN further per-surface rulings"*. (Ruling 3's *resolution* — that the root is derived rather than
taken from the first input token — is additionally recorded in the board's `[resolved]` pre-walk
entry; that entry is a resolution record, not the parked ruling text.) **Keep this table and those two
inbox items in step** — they are the same text awaiting the same yes (§7).

| # | Ruling | Rejected, and why |
|---|--------|---
| 1 | **Pan moves out of `poly set` into its own verb `brush poly pan`.** | Leaving it on `set` — the `--pan-to`/`--pan-by` compound spelling exists only because it shares a verb; alone it is `pan --to/--by`, matching every other transform in the CLI. |
| 2 | **Per-face mutators print `BRUSH:idx` selectors on stdout**, not touched brush names. Applies to `poly set`, `poly pan`, `poly rotate`, `poly scale` **and `poly align` (all four modes)**. The model functions still **return brush names** for `src.save(touched=…)`. | Keeping brush-name output — a bare name means *all* that brush's polys, so a second per-face verb in the pipe silently widens the set. Changing the model return too — `touched=` is a session-store contract, and widening a *save* set is harmless where widening a *mutation* set is not. |
| 3 | **`run` orders the chain itself, and the order faces are passed in has NO bearing on the result — the ROOT is derived by a pre-walk too** (lower-poly-index end; lowest index on a closed run). | Trusting pipe order for the whole chain, as `--ring` does — `find`'s order is not author-controlled. The reviewers' "root = first input token" — weaker: it narrows the input-order dependence instead of removing it. Consequence: no `--centre` flag is needed. |
| 4 | **`run` DERIVES the frame; it does not preserve the caller's rotation.** Fixups afterwards are quarter-turn flips and small texel pans. | Preserve-and-compose (`rotate --bend \| align --run`) — proposed by the agent, rejected by the owner, and vindicated by the spike: rotation alone leaves the phase broken (finding 2) and `run` deriving solves the case outright (finding 3). |
| 5 | **The turn is a scalar angle in unreal rotation units, folded into `run`, spelled `--turn UU`.** | `--rotate` — collides with `brush build --rotate` (actor orientation, a triple) and, worse, with `brush poly rotate` in the same noun, where the same word would carry the opposite continuity guarantee. A boolean `--across` — covers only quarter turns. A separate post-pass — pivots each face about its own centroid and re-breaks the seams. |
| 6 | **`--ring` is renamed `run`.** | Keeping `--ring` — a 90° arc is not a ring, and an author would not find the flag; `run` is already the codebase's own word (`polyalign._check_orientation`: *"turning runs deferred"*). |
| 7 | **Align modes are SUBCOMMANDS**: `brush poly align wall\|floor\|run\|one-tile` (§2.0). | A mutually-exclusive flag group — the flags are disjoint per mode, so `-h` becomes one blob of mostly-invalid options and every bad combination needs a runtime check — the shipped code carries exactly one (`--fit-perimeter` outside `--ring`), and the new `--turn` would need another that nobody has written. |
| 8 | **Density RESETS TO UNIT** — no mode adopts a seed face's texel scale, so `--fresh-frame` has one possible value and is deleted. **This binds `run` ALONE** — `wall`/`floor` take the projection's own `\|proj\|` density (ruling 9) and `one-tile` derives its density from the face (ruling 10), so neither is inside it to begin with. | Adopt-seed as the default — it makes the result depend on which face was listed first, which rulings 3 and 9 remove everywhere else. |
| 9 | **`wall` and `floor` are WORLD-SPACE aligned in orientation AND anchor, adopting UnrealEd's `FLOOR`/`WALLX`/`WALLY` projection family** (§2.3): anchored where the plane crosses the projection axis; `floor` projects along Z, `wall` along whichever of X/Y the face faces more. **Its consequence is accepted: a face not square to its axis is stretched, so density is `\|proj\|`, not 1.** | `builders._tex_basis` — measured against the editor, the two agree on **none** of seven face directions, and `_tex_basis` lets V point up on roughly half a room's walls. A seed face's centroid as the anchor — it makes two invocations over one plane disagree, which is exactly what the ruling removes. `WALLDIR` — unit and never stretched, but its sign depends on the CSG **surface** normal, which a model-side tool does not have (§2.3, §4b). |
| 10 | **`one-tile` is FIT TO THE POLY** (§2.6) — one tile spans the face, stretched non-uniformly, anchored at the face's minimum corner — taking the projection **directions, ORTHOGONALISED by Gram-Schmidt of U against V** (`V` kept, `U = normalize(U − V(U·V))`) and then scaled by the fit, so a sign has a predictable up-vector *and* square corners. **Its density comes from the face**, which is one of the two reasons ruling 8 binds `run` alone. | `_tex_basis`'s orientation — no predictable up-vector, so a sign can render sideways. **Merely normalising the projected pair** — `proj(B₁)·proj(B₂) = −(N·B₁)(N·B₂)`, so on a corner face `N = (0.577,0.577,0.577)` the axes stay **120° apart** (a 30° shear) and the anchor misses its own tile (`U ∈ [−85.33, 170.67]`, not `[0,256]` — `uv_preview.py`'s `onetile-skew` scene). **`U = V × N`** — orthogonal, but it picks its own sign and mirrors the image. Aspect-preserving fit — that is `scale` (§2.5); a letterboxed sign is the wrong default. A flag on `wall`/`floor` — implies a shared frame it structurally cannot provide. |
| 11 | **`brush poly scale` is IN SCOPE** as the fourth canonical surface op (§2.5) — after ruling 8 it is the only general way to express a texel density. | Deferring it — it was out of scope until reset-to-unit removed every other route to a non-unit density; `--fit-perimeter` (closed runs only) would have been the sole remaining channel. |
| 12 | **`--fit-perimeter` fits whole TILES, not whole texels** (§2.4.4), using the pixel size of the axis the along-run advance lands in. | The shipped integer-texel rule — measured, it removes 0.47 texels of a 31.47-texel mismatch on the standard 8-sided cylinder. Using `USize` unconditionally — a 4× error at `--turn 16384` on a non-square texture. |
| 13 | **No `--seam` flag**, and **both `wall` and `floor` exist** (not one merged mode). | A `--seam` flag — it would re-introduce the author-placed seam that ruling 3 derives; `--fit-perimeter` makes the closing seam exact, so its position stops mattering on the workflow that ships. Merging `wall` and `floor` into one auto-axis mode — the projection axis is a design choice on a slanted face (`floor` on a ramp is a legitimate, different answer from `wall` on it), so deriving it would remove a choice rather than a chore. |

### 3.2 Agent choices (→ the `rationale/` tree on landing)

`rationale/surface.md` already holds the verb-level ones; the frame math goes to a new `polyalign`
sibling, created with step 4.

- **Orthogonal frame, centreline reference radius** — from the measured trade in §2.7, not taste.
  Also answers the owner's deferred arc-length question: per-strip arc length and the sheared frame
  are *the same construction*, so option (a) is rejected on that evidence; per-facet fit (option c) is
  disqualified because it reproduces the restart defect.
- **Chord, not arc**, for the phase advance.
- **Exact component path at quarter turns**, scoped to axis-aligned orthogonal frames.
- **Non-quarter `--turn` allowed + stderr shear report**, rather than an error.
- **There is NO cap predicate: ONE branch error, which always carries the `--item Side` hint**
  (§2.4.1 step 4), with its accepted narrowing stated. Rejected: two geometric predicates (one
  backwards in both directions, one needing the run tangent that only exists after the walk it gates)
  and an adjacency one (`degree == |set| − 1` is a set-size coincidence — it calls a 4-face T-junction
  a cap and misses a prism selected with both caps, which is the plain `align run <Box>` invocation).
- **Root selection fixes the WALK DIRECTION too** (§2.4.1 step 7): on a closed run the walk leaves the
  lowest-index root toward its lower-indexed neighbour, so U increases with poly index and the open
  seam stays between the highest and lowest index — where `--ring` puts it today. Rejected: naming
  only the entry seam, which reverses U on every shipped cylinder wrap and is invisible to every
  existing assertion.
- **The across-run axis takes the negative side of its OWN largest-magnitude world component**
  (ties to the lowest axis index) (§2.4.2), fixed once at the root and propagated. Rejected:
  `--ring`'s "+Z-ish" tie-break — degenerate on a flat run, where it hands the sign to the walk
  direction; **a fixed `Ẑ`-then-`Ŷ`-then-`X̂` axis priority** — it needs a tie epsilon and is
  discontinuous *at* the flat bed, mirroring V between a dead-flat track bed and one with 0.6° of
  grade; and a per-face world test, which flips mid-sweep wherever `ĉ` crosses the rule's 45°
  discontinuity (a flat bed turning 90° does). **Its user-visible consequence for existing content
  is NOT an agent choice** — the V-flip on every already-wrapped cylinder is an owner narrowing,
  §7.
- **A terminal face's far edge is the quad edge opposite its seam**, its midpoint standing in for the
  missing seam midpoint; the root's phase zero sits on it (§2.4.2). Rejected: extrapolating a tangent
  from the single seam's own endpoints, which is the endpoint-derived tangent the chord rule already
  rejects.
- **The across-run zero is fixed ONCE at the root and propagated by seam continuity** (§2.4.2).
  Rejected: re-deriving a low endpoint per face (today's behaviour) — indistinguishable on a cylinder,
  wrong on a run whose cross section changes.
- **Connectivity is validated as one component of maximum degree 2** (§2.4.1 step 5). Rejected:
  relying on the walk to notice — two disjoint chains produce no branch and no error.
- **`wall`/`floor` drop the coplanarity and co-orientation guards** (§2.3), because the world-derived
  frame removes what they protected. Rejected: keeping coplanarity "to be safe" — it forbids the
  one-world-grid-across-many-planes capability the ruling is for.
- **A face failing the `|N.A| > 0.05` guard exits 2** rather than being silently skipped as the editor
  does (§2.3), per `direction/conventions.md` "No silent half-answers".

## 4. What the implementation must pin

`rules/spikes.md` requires a checkable finding to ship with a regression, and `CLAUDE.md` requires
every named-error path to carry one.

### 4.1 Migration of `uedcli/tests/test_polyalign.py` (39 tests, enumerated)

**5 are deleted, 14 change, 20 survive unchanged.** *This is the most important table in the change*:
the cylinder wrap is the only capability that ships today, and a test relaxed to make it pass is how
that capability is lost quietly. Verdicts below were read off the file, not inferred. **"Changes"
counts a re-worded `match=` as a change** — the three verdict words are the only three, and a test
whose assertion text must be edited is not one that survives unchanged. **Tests in OTHER files also
go red** — `test_name_not_found_sweep.py` drives the deleted `--wall`/`--floor` spellings — and they
are listed with their steps at the end of §4.3, because this table covers one file only.

**Coplanar `wall`/`floor` (8)**

| test | verdict |
|---------------------------------------------------|---
| `test_wall_two_brushes_uv_continuous_across_seam` | **survives** — the two `+Y` faces are coplanar, so the world-derived frames are identical and the seam is still continuous. It also still exercises the per-brush inverse transform and `touched == ["W1","W2"]` (ruling 2 leaves the model return alone). |
| `test_wall_continuous_when_second_brush_is_rotated` | **survives unchanged** — the rotated neighbour's stored frame still differs while the world mapping matches. |
| `test_wall_adopt_seed_preserves_seed_pan` | **DELETED** — pins adopt-seed, which ruling 8 removes. Not adapted ("No back-compat cruft"). |
| `test_wall_fresh_frame_zeroes_pan_and_uses_unit_axes` | **changes** — loses `fresh_frame=True` (the only behaviour). `Pan == (0,0)` survives. The unit-axis assertion survives **only because the fixture face is axis-aligned** (`N = (0,1,0)` ⇒ `proj(X̂)`, `proj(Ẑ)` are unit); it must be re-stated as "unit on a face square to its projection axis" and joined by a tilted-face case asserting `\|TextureU\| = \|proj\|`. |
| `test_wall_rejects_horizontal_face` | **changes** — still exit 2, **new message**. `N = (0,0,1)` ties `\|N.X\| = \|N.Y\| = 0`, so `wall` picks `X̂` and the `\|N.X\| > 0.05` guard fails. `match="horizontal"` must be re-derived against the projection-axis message; the old "use --floor" advice is gone. |
| `test_floor_rejects_vertical_face` | **changes** — the same way, on `\|N.Z\| = 0`. |
| `test_wall_rejects_non_coplanar_set` | **DELETED** — the coplanarity guard is deleted (§2.3). **Replaced** by a positive test: a `+X` face and a `+Y` face in ONE `wall` invocation each get their own correct projected frame. |
| `test_wall_rejects_coplanar_but_opposite_facing_faces` | **DELETED** — the co-orientation guard is deleted. **Replaced** by a positive test asserting the two opposite faces receive a **byte-identical** frame, which pins the `N → −N` invariance §2.3 rests on. |

**`run` (the eight `test_ring_*`)** — all renamed `test_run_*`; assertions kept unless a ruling
genuinely changes the answer. ⚠ **None of these eight observes the walk DIRECTION or the across-axis
SIGN**: `_assert_seam_continuous`, the per-facet U-span assertion and the closing-gap measurement are
all direction-agnostic, so every one of them stays green under a run walked backwards or textured
upside-down. That is a hole in the shipped suite, not a licence — §4.2 adds the two pins that close
it.

| test | verdict |
|-------------------------------------------------|---
| `test_ring_wrap_seam_continuous_and_perimeter` | **survives** (renamed) — a built cylinder already carries unit axes, so reset-to-unit changes nothing; each facet still spans exactly one chord. |
| `test_ring_leave_seam_vs_fit_perimeter` | **changes** — the `--fit-perimeter` half must be re-derived against whole **TILES**, and the fixture (`cylinder(200,100,7)`, untextured) needs a bound texture plus an injected `(USize, VSize)`. The default half ("density is exactly 1, total U fractional") survives. |
| `test_ring_continuous_on_rotated_relocated_cylinder` | **survives unchanged** (renamed) — the inverse-transform path is untouched. |
| `test_ring_fresh_frame_unit_density_and_continuous` | **changes** — loses `fresh_frame=True` and becomes the default case; both assertions unchanged. |
| `test_ring_keeps_pan_integer` | **INVERTS** — it seeds `pan = (3,5)` and asserts every face carries it; under ruling 8 the answer is `(0,0)` on every face. Keep the "components are `int`" half. |
| `test_ring_fit_perimeter_closes_the_seam` | **changes** — integer-texel meet → whole-**tile** meet; needs a texture and injected sizes; and `--fit-perimeter` now also requires a quarter `--turn`, which the default 0 satisfies. |
| `test_ring_rejects_cap_face` | **changes** (intent survives, message re-derived) — the cap is now caught by the plain branch check (§2.4.1 step 4); there is no cap classification, so `match="not a ring side face"` becomes the branch message. **Assert the `--item Side` hint, not a classification** — the hint rides on every branch error, and step 6's placement after step 4 is what keeps it reachable on this fixture. |
| `test_ring_rejects_multi_brush` | **changes** (message re-worded) — `match="ONE cylinder brush"` → one *brush* (a run is no longer cylinder-only). |

**Everything else (23)**

| test | verdict |
|-------------------------------------------------|---
| `test_fit_perimeter_requires_ring` | **DELETED** — argparse makes it unreachable under §2.0, and `polyalign.align()`'s `if fit_perimeter and mode != "ring"` guard becomes dead code that "No back-compat cruft" requires removing in the same change. |
| `test_align_empty_tokens_is_noop` | **survives unchanged.** |
| `test_resolve_targets_bare_name_is_all_polys_ordered` | **survives** — but `resolve_align_targets`'s docstring claim *"the ring seam is the first face"* goes with ruling 3. |
| `test_resolve_targets_dedups_preserving_order` | **survives unchanged.** |
| `test_resolve_targets_unknown_brush` | **survives unchanged.** |
| `test_resolve_targets_bad_selector` | **survives unchanged.** |
| `test_find_faces_item_filter_drops_caps` | **survives unchanged.** |
| `test_find_faces_facing_filter` | **survives unchanged.** |
| `test_find_faces_texture_filter_last_component` | **survives unchanged.** |
| `test_find_faces_non_brush_raises` | **survives unchanged.** |
| `test_dispatch_poly_find_prints_selectors` | **survives unchanged.** |
| `test_dispatch_poly_find_json` | **survives unchanged.** |
| `test_dispatch_poly_find_bad_facing_exit2` | **survives unchanged.** |
| `test_dispatch_poly_find_unknown_brush_exit2` | **survives unchanged.** |
| `test_dispatch_poly_align_positional_saves` | **changes twice** — the `SimpleNamespace` loses `fresh_frame` and takes `mode="run"`; and `assert out.strip() == "Tower"` **inverts** to eight `Tower:idx` lines (ruling 2), while `src.save(touched=["Tower"])` stays. |
| `test_dispatch_poly_align_reads_stdin_selectors` | **changes** — args shape only. |
| `test_dispatch_poly_align_empty_stdin_noop` | **changes** — args shape only. |
| `test_dispatch_poly_align_mixing_stdin_and_names_exit2` | **changes** — args shape only. |
| `test_dispatch_poly_align_error_exit2_no_save` | **changes** — args shape, and `"ring side face"` → the new branch message (§2.4.1 step 4). |
| `test_engine_fact_uv_formula_is_base_relative_plus_pan` | **survives unchanged** — a T3D-convention fact. |
| `test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n` | **survives unchanged** — a fact about `builders.cylinder`. |
| `test_align_emits_no_zero_pan_so_materialize_can_verify_the_built_map` | **survives** — a `+Z` cube face passes `floor`'s `\|N.Z\| = 1` guard and the mode writes `Pan = (0,0)`, so no `Pan` line is emitted and the materialize round trip still compares equal. Keep it: it guards a shipped bug. |
| `test_align_still_carries_a_non_zero_seed_pan_into_the_trunk` | **DELETED** — it asserts `Pan U=7 V=3` survives an align, which ruling 8 makes impossible (every mode writes `(0,0)`). Its real subject — *only* the all-zero pan is a spelling of the default — must be **re-homed onto `brush poly pan --to 7,3`**, the only verb left that writes a non-zero pan, in step 1. Losing it silently would leave `emit_polygon`'s non-zero-pan half unguarded. |

The helpers `_assert_seam_continuous`, `_shared_world_points` and `_editor_reexport` are unaffected.

### 4.2 New pins

**Editor parity — the cheapest high-value pin in the change, and the only thing that catches a dropped
negation or a swapped axis.** `spikes/2026-07-26-unrealed-texalign-semantics/` already ships
`texalign_model.py` (the executable statement of the editor's rules) and `measured.json` (44 faces ×
9 modes, straight out of the editor), and `test_engine_facts.py` already loads both
(`test_texalign_model_reproduces_every_measured_editor_frame`). So:

- **`align floor` reproduces `FLOOR`'s frame** on every `measured.json` face that passes the
  `|N.Z| > 0.05` guard — comparing `Origin`, `TextureU`, `TextureV` and `Pan` at the spike's own
  tolerances (2e-3 on a texture vector, 0.2 uu on an anchor, `Pan` exactly);
- **`align wall` reproduces `WALLX` on the faces where it derives `A = X̂`, and `WALLY` where it
  derives `A = Ŷ`** — which additionally pins the derivation itself, since a wrong axis choice picks
  the wrong golden and fails. **It needs the SAME guard filter its `floor` sibling has: restrict the
  comparison to faces that pass `|N.A| > 0.05` for the axis `wall` DERIVES.** Without it the pin is
  wrong on 12 of `measured.json`'s 44 faces: every face with `|N.Z| = 1` (`CubeA:4`, `CubeA:5`,
  `BoxB:4/5`, `CubeC:4/5`, `Room:4/5`, `SlantXYZ:0`, `SlantXZ:2`, `SlantYZ:2`, `WallYaw:4`) ties
  `|N.X| = |N.Y| = 0`, so `wall` picks `X̂` and exits 2 on the `|N.X| > 0.05` guard — while the
  editor's `WALLX` golden for those faces is the face **untouched** (verified: `CubeA:4`'s `WALLX`
  entry equals its `faces` entry byte for byte). Comparing an exit 2 against an untouched golden
  fails a correct implementation;
- **the tie-break** `|N.X| == |N.Y|` → `X̂` — **on `SlantXYZ:3`, a MEASURED golden, not a synthetic
  normal.** Its `n_surf` is `(0.57735, 0.57735, 0.57735)`: an exact tie that also passes the guard
  (`|N.X| = 0.577 > 0.05`), which is why it is usable where the 12 faces above are not. It is the
  same corner normal §2.6's 120° example is built on. Its two goldens differ
  (`WALLX` gives `TextureU = (0.333, −0.667, 0.333)`, `WALLY` gives `(−0.667, 0.333, 0.333)`), so a
  tie resolved the wrong way picks `WALLY`'s golden and fails. (An earlier draft claimed
  `measured.json` contains no usable tie and proposed a synthetic 45°-yaw normal; the `WallYaw`
  normals `(0.6,0.8,0)` and `(0.8,−0.6,0)` indeed do not tie, but `SlantXYZ:3` does.);
- **the `N → −N` invariance** — feeding the negated normal yields a byte-identical frame (§2.3). This
  is what licenses uedcli's brush-polygon normal where the editor uses the CSG surface normal.

These live with the other `test_texalign_*` regressions, because they assert conformance to an
editor-produced golden.

**Continuity (`run`)**
- **Cylinder runs stay exact under `--turn`** — ΔU = ΔV < 2e-3 at turns 0, 8192 and 5000.
- **Flat-bend shear matches the closed form** — assert `|max ΔU − d_u·2·sin(Δθ/2)·half_width| < 2e-3`
  and `max ΔV < 2e-3`, stating the fixture. **Do NOT pin six-decimal goldens**: the same alignment
  re-run over an already-aligned trunk moves them (12.546615 → 12.546781 → 12.6278) because
  `emit.clean`'s `CLEAN_EPS` snapping accumulates on off-grid vertices. Port
  `spikes/2026-07-26-poly-rotate-curved-track/seam_check.py` as the measurement.
- **Turn axis selection, stated by STORED COMPONENT** (not by "along/across", which inverts and is
  easy to misread): on the flat-bend fixture, `--turn 0` gives `ΔV < 2e-3` with `ΔU ≈ 12.55`;
  `--turn 16384` gives `ΔU < 2e-3` with `ΔV ≈ 12.55`; `--turn 8192` gives both `≈ 8.87`.
- **The across-run axis DIRECTION — V runs DOWN, and nothing currently pins it** (§2.4.2). Four
  assertions, because one geometry cannot show them all: (a) on an upright cylinder, `TextureV·Ẑ < 0`
  and the `V = 0` rim is the **top** one — which is a deliberate flip of what `--ring` writes today
  (§7 narrowing 2), so it is the pin that would catch an accidental revert; (b) on a **flat** run
  (the curved track bed, where `ĉ` is horizontal) the dominant component is `Ŷ`: on a bed travelling
  `+X̂`, `TextureV·Ŷ < 0` — **and on the mirror-image bed, built so the walk travels `−X̂`,
  `TextureV·Ŷ < 0` again**, the *same world direction*. A sign that leaked from the walk direction
  flips between those two and nothing else catches it; (c) **on a bed tilted ~1° out of horizontal**,
  `TextureV·Ŷ < 0` **still** — the assertion the rejected `Ẑ`-then-`Ŷ`-then-`X̂` priority chain fails,
  because a hair of grade is enough to make its `Ẑ` test decide and mirror V against the flat bed of
  (b). Build it as (b)'s fixture with the bed's Z raised linearly along the run (`ĉ` acquires a
  `|ĉ·Ẑ| ≈ 0.017` component, far from the 45° tie, so the dominant axis is still `Ŷ`); (d) feeding
  the **negated** face normal (the subtractive case) yields a byte-identical frame.
- **The across-run axis SIGN is fixed once at the root and propagated** — not recomputed per face
  against a world axis, which would flip mid-sweep and mirror V. **Pin on a flat bed turning at
  least 90°**, the geometry where the two rules differ. The fixture is a `builders.revolve` of a
  rectangular profile with `axis="x"`, whose `Side0` strip is a flat curved bed:
  `revolve([(192,−16),(256,−16),(256,16),(192,16)], 180, 6, axis="x")` — verified 2026-07-26 that all
  six of its `Side0` faces have normal exactly `(0,0,−1)`, i.e. one horizontal plane — selected with
  `brush poly find <brush> --item Side0`. (90° would do; 180° crosses the tie twice.) As
  the bed turns, `ĉ` rotates from `∓Ŷ` to `±X̂` and passes through `(−0.707, 0.707, 0)`, where the
  per-face rule's two largest components tie with opposite signs and it flips. Assert `TextureV` is
  continuous across **every** seam, including the one straddling the 45° point — a per-face rule
  mirrors V exactly there and leaves every other seam looking fine.
- **Walk DIRECTION on a closed run** (§2.4.1 step 7) — on the shipped 8-sided cylinder, U increases
  with poly index and the open seam is `sides[-1] | sides[0]`, not `sides[0] | sides[1]`. Assert the
  *position* of the open seam (the one pair whose U gap is ≈ the full perimeter), not just its size:
  every shipped assertion is direction-agnostic, so this is the only thing standing between the
  generalisation and a silently reversed wrap.
- **The across-run zero is the ROOT's entry-edge low endpoint, propagated** — pin it on a run whose
  cross section CHANGES along it, which is the only fixture where the propagated and the per-face
  rules differ (§2.4.2). A cylinder cannot detect this. **No shipped builder emits a varying cross
  section** (a `cylinder`'s, an `extrude`'s and a `revolve`'s swept quads all keep one seam-edge
  length), so this fixture is **hand-assembled** from explicit vertex rings — the only one in the
  change that is. Concretely, a two-quad flat bed in `Z = 0` that narrows along `+X̂`:
  `A = [(0,−64,0), (128,−48,0), (128,48,0), (0,64,0)]` and
  `B = [(128,−48,0), (256,−32,0), (256,32,0), (128,48,0)]` — free edge 128 uu, shared seam 96 uu,
  far free edge 64 uu. Both faces are terminal (§2.4.2). The propagated rule puts `V = 0` on the
  root's far-edge endpoint at `y = +64` for **both** faces; a per-face rule would re-derive `B`'s own
  low endpoint at `y = +48` and shift `B`'s V by 16 uu. Assert the seam is V-continuous and that
  `B`'s `V = 0` line passes through `y = +64`, not `y = +48`.
- **The stderr SHEAR REPORT** (§2.4.3), which nothing else observes because it is not on stdout and
  changes no written frame. Two assertions on captured stderr: on the **closed 8-sided cylinder** the
  report does **not** mention the closing seam's full-perimeter gap (`1567.47` must not appear — it
  is the deliberately-open seam, and printing it as "worst-case shear" every time would be noise);
  on the **flat-bend** fixture at `--turn 0` it **does** report the shear, `≈ 12.55`. Match a
  tolerance, not a six-decimal golden, for the reason the flat-bend bullet above gives. The figure is
  **measured from the written frames**, so the assertion is on the same number `seam_check.py`
  computes — never on the closed form.

**The pre-walk (§2.4.1), one test per decided rule**
- **Ordering invariance** — shuffling **all** tokens, the first included, produces a byte-identical
  result. Plus a positive pin on the derived root: an open run roots at its lower-poly-index end, a
  closed run at its lowest index. (An earlier draft pinned "changing the first token moves the seam",
  which asserts the opposite of ruling 3 and cannot pass.)
- **Branching** — one message, so the pins assert *what it names* rather than which of two it is.
  (i) the flagship 8-sided cylinder + cap exits 2 and the message carries the `--item Side` hint;
  (ii) a **square prism selected with BOTH caps** — the plain `align run <Box>` set — exits 2 too,
  which the abandoned `degree == |set| − 1` predicate did not catch; (iii) a genuine **T-junction** of
  quads exits 2 naming the offending face and its neighbour count. All three name **every** degree-≥3
  member, so (i) lists all nine faces of the cylinder+cap fixture — assert the cap is among them.
- **Connectivity** — (i) two disjoint 3-face chains exit 2 (four degree-1 ends, no branch, so nothing
  else catches it); (ii) a set containing one isolated face exits 2.
- **Terminal faces** — on a 3-face open run, the root's far edge maps to `U = 0` and the last face's
  far edge to `U = total chord`; a **two-face** run (both faces terminal) aligns and is seam-continuous.
- **Non-quad ordering** — a set containing a triangle exits 2 naming the face, but the cylinder+cap set
  still reports the BRANCH message (with its hint) rather than "not a quad" (this is what step 6's
  placement after step 4 buys, and it is the whole reason the ordering is load-bearing).

**Behaviour**
- **`wall`/`floor` idempotence and set-independence** — aligning face A alone and face B alone (same
  plane, separate invocations) yields byte-identical frames; a second run over the same set changes
  nothing; and a set spanning **two different planes** succeeds, each face getting its own anchor.
- **`wall`/`floor` guard failure exits 2 naming EVERY failing face** (pin a set with two of them, and
  that no face in the set was written), on both sides of `|N.A| = 0.05`
  (the spike brackets the editor's threshold live at `0.049` / `0.051`).
- **`scale`** — `--by 2,2` halves the stored magnitudes (texture looks twice as big); `--to 128,128`
  on a `W×H` texture gives `|TextureU| = W/128`; the face centroid's `(U,V)` is unchanged by both;
  `Pan` untouched. `--by` needs no catalog, `--to` does.
- **`one-tile` orientation** — on a `+Y`-facing wall, `TextureV` is `−Ẑ` (V runs downward, so a
  top-row-first texture renders upright) and the axes are unit before the fit scales them; on a floor,
  `−X̂`/`−Ŷ`. Pin a slanted face too, since unpredictable up-vectors there are the defect this rule
  exists to prevent.
- **`one-tile` axes are ORTHOGONAL** — on the corner normal `N = (0.577, 0.577, 0.577)`, assert
  `TextureU·TextureV ≈ 0` (90°, not the 120° the un-orthogonalised pair gives) **and** that `TextureV`
  still points along `−proj(Ẑ)`, which is what fixes Gram-Schmidt's direction: an implementation that
  squared V against U instead, or took `U = V × N`, passes the first half and fails the second.
- **`one-tile` fit** — a `W×H` texture on an `E_u × E_v` face gives `|TextureU| = W/E_u`,
  `|TextureV| = H/E_v`, `Pan` (0,0), `Origin` at the min corner; a rectangular face's corners map to
  exactly (0,0), (W,0), (W,H), (0,H) — **an assertion that is only valid for an orthogonal frame, and
  is the cheapest end-to-end check that the orthogonalisation happened**; a triangle maps its bounding
  box; a zero-extent axis and a texture missing from the catalog each exit 2 naming the face or the
  ref, all offenders at once.
- **Coplanar sets are accepted** by `run` (the deleted "all faces are parallel" rejection), and the
  same coplanar set gives a **different** result under `floor` than under `run` — one straight, one
  turning. Pin both, since "they collapse into each other" is the obvious wrong reading.
- **`--fit-perimeter`** closes a closed run in whole TILES, on a **non-square** texture (256×64), at
  `--turn 0` (fits `USize`) and `--turn 16384` (fits `VSize`) — the pair that catches the 4× error.
- **Quarter-turn exactness**, split by verb because they are different assertions:
  (a) `brush poly rotate --by 16384` on a `+Z` face with `TextureU=+X, TextureV=+Y` yields exactly
  `TextureU=+Y, TextureV=−X` — this is also the **sign** pin;
  (b) `align run --turn 16384` produces axis **directions** identical to the `--turn 0` axes
  swapped/negated, with each axis keeping its own magnitude. Scope it to an **unrotated** brush
  (`_write_world_frame` inverse-transforms through `R`) or assert directions only.
- **`brush poly pan --to`/`--by`**, including `--to 0,0` emitting no `Pan` line **and `--to 7,3`
  emitting `Pan U=7 V=3`** (the re-homed half of the deleted `test_align_still_carries…`), plus dedup
  of an overlapping target set (no double-apply). Same dedup pin for `rotate` and `scale`.
- **`rotate`'s out-of-plane guard, BOTH branches of `max(TOL_ABS, TOL_REL·|axis|)`** (§2.2) — a
  relative-only or an absolute-only implementation passes one and fails the other, so neither alone
  is a pin: (a) the **relative** branch on a **unit-magnitude** axis — an axis with a `0.005` normal
  component is accepted and one with `0.05` exits 2, bracketing `TOL_REL = 1e-2`; (b) the
  **absolute** branch on a **short** axis — take a face through `brush poly scale --by 8,8` (`|axis|
  = 0.125`, where `TOL_REL·|axis| = 1.25e-3` sits *below* the serializer's own noise) and assert a
  `1.4e-3` normal component is **accepted**, which a relative-only gate rejects, while `5e-3` still
  exits 2. Plus (c) that it is a **pre-pass**: nothing is mutated when face 7 of 12 trips, and every
  offender is named.
- **stdout format** — every per-face mutator emits `BRUSH:idx` lines that `-` re-consumes; assert the
  round trip, not just the format. The model functions keep returning **brush names** for
  `src.save(touched=…)`, which is a session-store contract; only the CLI print changes.

**Error paths — ONE standard, applied to argparse-level and uedcli-level rejections alike.** The two
are pinned differently and an earlier draft mixed them, demanding a `match=` pin for `--to` with
`--by` (which argparse rejects) while declaring `--turn` on `wall` "not an error path" (which
argparse also rejects). The rule:

- **uedcli-level** — the message is uedcli's, so the pin asserts **exit 2 AND matches the message
  text**, per `CLAUDE.md` "Never let a Python exception reach the CLI user".
- **argparse-level** — a combination the *grammar* forbids never reaches uedcli code, so there is no
  uedcli message to match and asserting one would pin argparse's own wording. **One grammar pin per
  parser**, asserting exit 2 and **no `match=`.** This covers `--to` with `--by` on `pan`/`scale`,
  and `--turn` or `--fit-perimeter` on `wall`/`floor`/`one-tile` (§2.0's whole point is that these
  become grammar errors). It is not "no coverage": the pin exists, it just asserts what is actually
  true.

**uedcli-level, each a named exit 2 with a regression:** branch (one message, always carrying the
`--item Side` hint); disconnected set; isolated face; edge shared by >2 faces; a pair of faces
sharing MORE THAN ONE edge (§2.4.1 step 2); a degenerate (zero-area) face; `< 2 faces`; multi-brush
set; non-quad face; `pan`/`scale` with **neither** `--to` nor `--by` *when called in the model*
(from the CLI, argparse's required mutually-exclusive group fires first — say which layer the test
drives); a zero or negative `scale` factor; `one-tile` on a face with a zero extent; `wall`/`floor`
failing the `|N.A|` guard; a texture absent from the catalog, a face with no texture, or a project
with no synced catalog, for each of `scale --to`, `one-tile` and `--fit-perimeter`; a run whose faces
carry different textures under `--fit-perimeter`; `--fit-perimeter` on an open run; `--fit-perimeter`
at a non-quarter `--turn`; a face whose texture axes have a normal component beyond §2.2's tolerance.

**Each of those that can have more than one offender is pinned on a set with TWO**, asserting both are
named and that nothing was written — `conventions.md` requires the complete set, and an
all-or-nothing batch is only observable when the failure is not the first face.

**Gone entirely, and their tests are DELETED not moved:** `polyalign.align()`'s own
`--fit-perimeter`-outside-`--ring` check (the guard becomes dead code under §2.0 — the *grammar* pin
above replaces it, not a re-homed `match=`); a non-coplanar or opposite-facing `wall`/`floor` set
(§2.3 deletes both guards); "a root that is not a run end" (unreachable once the pre-walk derives the
root).

### 4.3 Docs to update in the same change

A rename with no shim, so every occurrence is a broken instruction.

⚠ **Cited by ANCHOR TEXT, never by line number — THROUGHOUT THIS SPEC, not only in this section.**
The step-1 plan already ruled this (board item `brush-poly-rotate-turns-against-the-visible` §6) and this
section is the reason: its numbers were "verified against the working tree" twice and were wrong both
times, because several sessions edit this tree concurrently and a line number is stale the moment
someone inserts a paragraph above it. An anchor is grep-able and survives that. §2's citations of
`polyalign.py`, `builders.py`, `surface.py` and `texture_catalog.py` were converted to anchors on the
same rule; if you add a citation anywhere in this document, name the function and quote the string,
never the line. Every string below was grepped 2026-07-26.

**The `step` column is the build step (§4.4) each doc edit ships in** — no step may end with a doc
describing a CLI it does not yet have, or omitting one it does. A row spanning steps names each.

| file | step | anchor to grep for → what to change |
|-----------------------------------------------------|------|---
| `docs/usage.md` | 1, 2 | `Output streams for mutators.` → it lists `poly set` / `align` as printing touched brush names; ruling 2 makes every per-face mutator print `BRUSH:idx`. **Step 1** covers `set`/`pan`/`rotate`/`scale` and must state that `align` still differs; **step 2** closes it and deletes that caveat |
| `docs/usage.md` | 2 | `selectors, for piping` (the verb-table row) and `is a stateless producer` (the paragraph) → `poly find`'s own output description, the other half of the pipe ruling 2 changes. *Omitted from the previous draft* |
| `docs/usage.md` | 1, 2, 4, 5 | `## Brush shape & surfaces` → in that verb table, the `poly set` row and the `poly align` row become seven rows: `set`, `pan`, `rotate`, `scale`, and the four align modes. Each row appears in the step that ships its verb: `pan`/`rotate`/`scale --by` in 1, `wall`/`floor`/`run` in 2, `--turn` in 4, `one-tile` and `scale --to` in 5 |
| `docs/usage.md` | 1 | `edits surface attributes model-side` → drop `--pan-to`/`--pan-by`, and move the "a pan of 0,0 **is** the unpanned state" note that follows them onto `pan` |
| `docs/usage.md` | 2, 3 | `### Continuous texture alignment` and, inside it, `That canonical frame is` → the whole align section. **Step 2** restructures it per subcommand; **step 3** inverts the ⚠ paragraph that says uedcli's frame is *not* a reproduction of the editor's — for `wall`/`floor` it then **is** (`run`/`one-tile` stay uedcli-only) |
| `docs/usage.md` | 2 | `an exact meet at the closing seam` → **false as shipped** (§2.4.4 measures ~31 texels left on the standard 8-sided cylinder). Step 2 keeps the shipped whole-texel behaviour, so it must correct the claim in the same step; step 5 then rewrites the line again for whole tiles |
| `docs/usage.md` | 2 | **`align run` is RING-ONLY until step 4** → say so where `run` is documented: closed cylinder-style rings, caller's chain order, coplanar sets rejected. §2.4's general run, `--turn` and the derived pre-walk arrive in step 4 |
| `docs/usage.md` | 4 | **the `run` V-FLIP warning** (§7 narrowing 2) → `align run` puts `V = 0` on a cylinder's TOP rim with V growing downward, so **re-aligning an existing wrap flips its texture vertically**. A behaviour change to existing content, so it is a ⚠ at the point of use, not a footnote |
| `docs/usage.md` | 1–5 | **new sections** → one per new verb (`brush poly pan`, `rotate`, `scale --by` — step 1; `scale --to` — step 5) plus a sub-heading per align mode as each mode ships (2, 4, 5); the ⚠ destructive-on-imported-content warning (§2.3) **at the point of use** (step 3); and the ordering rules (`pan` after `align`, `scale` before `align run`) in step 1 |
| `docs/leveldesign/general/textures-and-surfaces.md` | 1, 2 | `--pan-by 0,32`, `align - --floor`, `auto-aligns (walls, floors/ceilings, or around a cylinder)`, and `is uedcli's own alignment` → the worked examples and the same "not a copy of the editor" warning. The `--pan-*` example moves in step 1, the `align` spellings in step 2 |
| `dev/docs/unrealed/leveldesign/kb/textures.md` | 1, 2 | `--pan-to/--pan-by`, `- **Auto-align:**`, `- **Manual:** Pan / Rotate / Scale`, and the cheat-sheet `Align` / `Pan` rows → the Manual row still calls Rotate and Scale GUI-only; they are uedcli verbs now (step 1). The `Align` row follows the subcommand rename in step 2 |
| `dev/docs/rationale/emit.md` | 1 | `--pan-to 0,0` (three occurrences) → all three name `brush poly set` as the producer of the zero-`Pan` case, the durable rationale §2.1 depends on, and must name `brush poly pan --to 0,0`. One also names `surface.set_surface`, a function that does not exist (`apply_surface_edit` does) — fix while there |
| `dev/docs/unrealed/texalign.md` | 3 | `## How uedcli differs` → it says uedcli's frame is "**not** any of the editor's rules" and carries the seven-direction divergence table; under ruling 9 `wall`/`floor` ADOPT the projection family, so the section inverts. Engine-fact doc: the editor facts above it do not move, only the uedcli comparison |
| `dev/docs/architecture.md` | 1, 2, 3, 4, 5 | `verb: pure texture-vector` (the module-map line) and `Surface texture alignment` (the subsystem entry) → verb list, flags, adopt-seed, the coplanarity guard. `CLAUDE.md` requires *what IS* to track the code, so this pair is re-checked at the end of **every** step, not once |
| `uedcli/polyalign.py` | 3 | the **module docstring** — `This is uedcli's OWN alignment, NOT a port of the editor's` … `is an open product question` → ruling 9 *answers* that question and inverts the paragraph for `wall`/`floor`; the docstring also still describes anchoring on the seed face's centroid, which §2.3 removes. *Omitted from the previous draft* |
| `uedcli/polyalign.py` | 4 | `the ring seam is the first face` (in `resolve_align_targets`'s docstring) → ruling 3 deletes the behaviour, so the claim goes with it. It survives step 2 truthfully (the ring algorithm is untouched there) and goes with the pre-walk in step 4; §4.1 flags it against `test_resolve_targets_bare_name_is_all_polys_ordered` |
| `uedcli/emit.py` | 1 | `--pan-to 0,0` → one comment carrying the old spelling |
| `uedcli/query.py` | 1 | `target) prints as` → the `pan` column docstring, which names the old spelling |
| `uedcli/surface.py` | 1 | `pan_to` / `pan_by` (in `apply_surface_edit`'s signature) and `at least one of --texture/--add-flag/--remove-flag/` → the parameters, and the message, which drops from five flags to three |
| `uedcli/cli.py` | 1, 2 | `--pan-to` / `--pan-by` (the `add_argument` calls on the `poly set` parser — step 1) and `: make a texture flow continuously across a face set` (the align-parser comment) → the flags, and the whole `poly align` parser in step 2 |
| `uedcli/tests/test_cli_consistency.py` | 2 | `(matching \`brush poly align\`)` — a comment claiming `align`'s stdout is touched actor **names**, which ruling 2 inverts. Not a failing assertion, so nothing catches it; it is a doc edit inside a test file |
| `docs/leveldesign/general/recipes/` | 4 | **new file** → a curved-run recipe; the motivating workflow (§1) has none. It needs the general `run`, so it cannot land before step 4 |

**Tests OUTSIDE `uedcli/tests/test_polyalign.py` that go red, by step** — §4.1 enumerates only
`test_polyalign.py`, and a red test in another file is how a step "ends green" turns out to be false:

| file | step | what breaks |
|-------------------------------------|------|---
| `tests/test_name_not_found_sweep.py` | 2 | **two entries drive the deleted flag spellings** — `("brush-poly-align", ["brush","poly","align","--wall", …])` in the positional table and `("brush-poly-align-stdin", [… "--floor","-"])` in the stdin table. Both must become the subcommand form (`align wall …` / `align floor -`). The file's stated purpose is BOTH tables, so covering one is covering half of it |
| `tests/test_cli.py`, `test_surface.py`, `test_dispatch.py`, `test_actor_name_resolution.py`, `test_cli_consistency.py`, `test_emit.py` | 1 | the `--pan-to`/`--pan-by` split, enumerated with counts in board item `brush-poly-rotate-turns-against-the-visible` §6. Listed here so this spec's own picture is complete, not to restate that plan |
| `tests/test_engine_facts.py` | 3 | **grows** rather than breaking — the §4.2 editor-parity pins live beside the existing `test_texalign_*` regressions, which already load the spike's `measured.json` and `texalign_model.py` |

**Leave alone:** in `dev/docs/unrealed/t3d.md`, the two passages anchored on
`**A minimal repro on a plain cube**, live 2026-07-26` and
`making the whole` … `` `brush poly find … | brush poly align …` → build workflow unusable `` spell
the old flags inside a **record of a live repro actually run on 2026-07-26**. Rewriting a historical evidence citation to a syntax that did not exist when it was run
would falsify the record. The surrounding prose is about `emit_polygon`, not about the align flags.

**`--segments` must be documented as a texture-quality parameter**, with the shear formula **scoped to
flat bends**, and the caveat that doubling segments halves each seam's shear but **doubles the number
of seams**.

### 4.4 Build order

`CLAUDE.md` "BATCH small changes" — a subtle change to load-bearing code gets its own round. **Five
steps.** The governing rule, which an earlier draft of this section broke three ways: **no step may
introduce a flag, a subcommand or a deletion whose behaviour arrives in a later step**, and the
converse: no step may leave a doc describing behaviour it does not have. §4.3's `step` column is the
per-step doc assignment that makes "fully documented" checkable rather than an aspiration. Every step
below ends with a CLI that is internally consistent and fully documented.

1. **`set`/`pan` split + `rotate` + `scale --by`** — mechanical promotions, settled semantics, no
   catalog, no `polyalign` frame math. **Already planned and building**:
   board item `brush-poly-rotate-turns-against-the-visible` (revised after its round-1 plan review; its own
   header carries its current gate state). `scale --by` belongs
   here because it needs no catalog; `scale --to` does, so it waits for step 5.
2. **`align` flags → subcommands** (§2.0), over the modes that **exist**: `align wall`, `align floor`,
   `align run` (the `--ring` rename, ruling 6, algorithm untouched). Three things ride along because
   they are the same CLI change:
   - **`--fresh-frame` is deleted, and the FRESH branch is what survives** — a canonical frame at unit
     density with `Pan = (0,0)`. Adopt-seed is deleted with the flag (ruling 8). Deleting the flag and
     keeping *adopt-seed* would leave the tool doing the opposite of the ruling for two whole steps,
     which is what the previous draft did.
   - **`align` joins the `BRUSH:idx` stdout contract** — ruling 2's other half, which the previous
     draft assigned to no step at all and the step-1 plan (§9) logged as an interim inconsistency.
     This step closes it.
   - **`--turn` and `one-tile` do NOT appear here.** Each arrives with its implementation (steps 4 and
     5), so no author ever sees a flag or a subcommand that does nothing.
   - **`--fit-perimeter` survives with its SHIPPED behaviour, and the docs must say what that
     behaviour actually is.** The tile fix is step 5 and the algorithm is untouched here, so between
     this step and that one the flag still snaps to whole **texels**, which §2.4.4 measures as
     leaving **~31 texels** of mismatch on the standard 8-sided cylinder. `usage.md` today claims
     "an exact meet at the closing seam", which is false and must be corrected **in this step**, not
     in step 5 — otherwise the governing rule is broken in the other direction: a documented
     behaviour that does not arrive until later. Its two new guards (closed run, quarter `--turn`)
     do **not** belong here either — see step 4.
   Not separable and not mechanical: one atomic change across `cli.py`, `dispatch.py`, `polyalign`'s
   entry point, `usage.md` and the recipes.

   ⚠ **What step 2 must DOCUMENT, because the CLI is honest only if the docs are.** `align run` here
   is the `--ring` algorithm under a new name, so for two steps it accepts **only** what `--ring`
   accepts: a closed ring of cylinder-style side faces, in the caller's own chain order, rejecting
   coplanar sets. It is **not** yet the general run of §2.4. `usage.md`'s `run` section must say so —
   "ring-only for now" and "`--fit-perimeter` leaves ~31 texels; it is corrected to whole tiles when
   the catalog lands" — rather than describing §2.4's capabilities ahead of them.
3. **`wall`/`floor` world-space rewrite** (§2.3) — the projection family, the derived wall axis, the
   `|N.A|` guard replacing `_check_orientation`, the deletion of the coplanarity/co-orientation guards,
   and the §4.2 editor-parity pins. Small, self-contained, and the one step with an editor-produced
   golden to check itself against, so it goes before the frame math rather than after.
4. **`align run`** (§2.4) — the pre-walk (steps 1–8, including the derived root **and walk
   direction**), the frame math, the across-axis convention, reset-to-unit, **the `--turn` flag and
   its behaviour together**, and the stderr shear report. Reviewed alone; this is the riskiest *logic*.
   - **§2.4.4's two `--fit-perimeter` GUARDS land here, beside `--turn`** — exit 2 on an **open** run
     and exit 2 at a **non-quarter** `--turn`. Not step 2 (there is no `--turn` to check and no open
     run to reject: the shipped algorithm accepts only closed rings) and not step 5 (that would leave
     `align run --fit-perimeter --turn 5000` silently producing a wrong answer for a whole step,
     which is exactly what this section's governing rule forbids). A guard belongs in the step that
     first makes its failure case reachable, and `--turn` plus open runs both arrive here.
5. **Catalog plumbing + `--fit-perimeter` tile fix + `one-tile` (subcommand and behaviour together) +
   `scale --to`** — introduces a new cross-module dependency and a project requirement on a verb that
   is pure model-side today. Riskiest *coupling*, so it goes last where it gets its own round.

> ⚠ **Renumbering note for the step-1 plan.** board item `brush-poly-rotate-turns-against-the-visible` was
> written against the previous **four**-step order and calls the catalog step "step 4"; it is now
> **step 5**, and step 1's content is unchanged. Nothing in that plan's scope moves.

## 4b. UnrealEd parity — MEASURED 2026-07-26 (evidence)

Spike: [`dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/`](../../../spikes/2026-07-26-unrealed-texalign-semantics/README.md);
verified facts in [`dev/docs/unrealed/texalign.md`](../../../unrealed/texalign.md). 44 faces × 9 modes, twice (once
from a zero pan, once from an authored `Pan U=7 V=13`), plus eight one-wedge levels bracketing the
guard thresholds, plus disassembly of `UEditorEngine::polyTexAlign`. **This section is evidence only —
every question it used to carry is ruled in §3.1.**

**Three things this section previously asserted, which the spike disproved:**

| earlier claim | measured |
|--------------------------------------------|---
| "six modes against our two" | **nine** — `commands.md` was missing `DEFAULT`, `WALLPAN`, `WALLCOLUMN` |
| "we cannot say what any of them does" | all nine measured, 396 (mode, face) predictions reproduced |
| "`ONETILE` — fit exactly one tile to the face" | **`ONETILE` is a NO-OP**; so is `WALLCOLUMN` |

**There is no fit-a-tile-to-a-face operation in UnrealEd 2.2.** `WALLCOLUMN`'s switch entry *is* the
`default:` branch and `ONETILE`'s falls through to the bare epilogue. So `align one-tile` (§2.6) is a
uedcli invention, not a port.

**No mode changes texel density TO FIT A FACE — but the projection family is NOT 1 texel/uu on a
tilted face.** *(The previous draft said "no mode changes texel density … at 1 texel/uu", which the
very spike it cited disproves.)* Precisely: every mode writes 1 texel per world unit **measured along
the projection it uses**, and none of them reads a texture's `USize`/`VSize` except `CLAMP`'s single
`PanV` write. On a face square to its projection axis that is 1 texel/uu on the face too; on any other
face the projection family stores `|proj| < 1` and the texture looks stretched by `1/|proj|`.
`TEXELS=<n>` is parsed and never read.

**Measured semantics**, with `N` = the **surface** normal (reversed vs the brush polygon on a
subtractive brush), `d = N·P`, `proj(B) = B − N(N·B)` **not renormalised**
(`|proj(B)| = √(1 − (N·B)²)`):

- **`FLOOR` / `WALLX` / `WALLY`** — one family: orthographic projection down world Z/X/Y. `Pan` zeroed
  (measured against an authored non-zero pan, not merely observed to stay zero); guard
  `|N[axis]| > 0.05`, bracketed live at 0.049/0.051; a face failing it is left **untouched**, pan
  included. **The axis assignment is not cyclic:**

  | mode | drops | `TextureU` | `TextureV` | new `Origin` |
  |---------|-------|------------|------------|---
  | `FLOOR` | Z | `−proj(X̂)` | `−proj(Ŷ)` | `(0, 0, d/N.Z)` |
  | `WALLX` | X | `−proj(Ŷ)` | `−proj(Ẑ)` | `(d/N.X, 0, 0)` |
  | `WALLY` | Y | `−proj(X̂)` | `−proj(Ẑ)` | `(0, d/N.Y, 0)` |

  The anchor is a **world axis**, so every coplanar face shares one grid: a 128³ cube centred at
  `(512, 96, 48)` had its top face's `Origin` moved from `(512, 96, 112)` to `(0, 0, 112)`. A tilted
  face is stretched: a 45° ramp under `FLOOR` gets `|TextureU| = 0.70711`; `N = (0.211, 0.281, −0.936)`
  under `WALLX` gets `|TextureV| = 0.35112` (~2.8×).
- **`WALLDIR`** — `TU = normalize(N.Y, −N.X, 0)`, `TV = normalize(TU×N)`, both negated; unit, never
  stretches, **V always points down**; anchor untouched; guard `|N.Z| < 0.95`.
- **`WALLPAN`** — slides the anchor along `TextureV` to world `Z = 0`; axes and pan untouched.
- **`DEFAULT`** — regenerates the frame from the polygon's own winding; a reset, not a design tool.
- **`CLAMP`** — `DEFAULT` plus `PanV = VSize − 1`.

**Which of these a model-side tool can adopt at all.** `proj(B)` and `d/N.A` are both **invariant under
`N → −N`**, so the projection family gives the same answer from the brush polygon's normal (all uedcli
has) as from the CSG surface normal (what the editor uses). `WALLDIR` is **not** invariant —
`normalize(N.Y, −N.X, 0)` flips outright — so adopting it would need a BSP uedcli does not build. That,
not preference, is why §2.3 takes the projection family.

### Diff against uedcli, after the §3.1 rulings

| editor mode | uedcli | verdict |
|-------------|-----------------|---
| `FLOOR` | `align floor` (§2.3) | **ADOPTED** — same axes, same negation, same world anchor, same `0.05` guard. One deliberate divergence: a face failing the guard **exits 2** here and is silently skipped there (`conventions.md` "No silent half-answers") |
| `WALLX` / `WALLY` | `align wall` (§2.3) | **ADOPTED, with the axis DERIVED** — the editor makes the author choose `WALLX` vs `WALLY`; `wall` picks the larger `\|N.X\|`/`\|N.Y\|`, ties to X̂. Same divergence on the guard |
| `WALLDIR` | — | **deliberately NOT adopted** — its sign depends on the CSG surface normal, which a model-side tool does not have; and V-always-down is already supplied by `WALLX`/`WALLY`'s `−proj(Ẑ)` |
| `WALLPAN` | — | **no equivalent** — re-phasing a wall to world `Z = 0` without touching its axes is cheap and absent; filed to `board/inbox/`, not folded in here |
| `DEFAULT` | — | **no equivalent, and none wanted** — winding-order dependent, so two coplanar faces come out 90° apart |
| `CLAMP` | — | **no equivalent**; what it is FOR was not determined (only what it writes) |
| `ONETILE` / `WALLCOLUMN` | `align one-tile` (§2.6) | **nothing to conform to** — both editor modes do nothing |
| — | `align run` (§2.4) | **uedcli-only** — UnrealEd has no cylinder-wrap or run mode at all |
| — | `poly pan` / `rotate` / `scale` | **uedcli-only as frame ops** — the editor's equivalents are GUI Surface-properties controls (`POLY TEXSCALE`/`TEXMULT`), not `TEXALIGN` |

**One practical fact that is not about rules at all:** `POLY TEXALIGN` walks `Model->Surfs`, which only
CSG produces, so driving it would cost a paste + `MAP REBUILD` per alignment (measured: with no
`MAP REBUILD`, 0 of 11 faces changed). That is an independent reason `brush poly align` stays
model-side whatever it decides about matching the editor's *rules*.

## 5. Sequencing

`board/to-plan/` carries board item `brush-poly-find-facing-component-predicate`, **both gates passed**, which
drops `--facing +Z` for a predicate grammar and makes `brush poly find` accept a brush **set**. This
spec's motivating workflow drives everything through `--facing +Z`, and §6 puts multi-brush runs out
of scope precisely as `find` starts emitting multi-brush sets routinely.

**This is a soft note, not a hard gate** — an earlier draft asserted "that spec lands first", which
does not survive scrutiny: nothing in §2 depends on the predicate grammar (every example here uses
`--item Side` or `--facing +Z`), and that spec making `find` emit multi-brush sets more often would
make this verb's `run` exit 2 *more* often, not less. The concrete overlap is only the doc/recipe
examples and the `test_polyalign.py` `--facing` fixtures, which **both** specs migrate. Whichever
lands second rebases its examples onto the current grammar. `run` exits 2 naming the brushes on a
multi-brush set either way.

## 6. Out of scope

- **Non-quad faces in a run — DECIDED, not deferred: exit 2 naming the face.** The quad assumption is
  load-bearing (a terminal face's free edge is found as the opposite edge of the quad); generalising
  needs a different rule for "the far edge" and no shipped builder produces a non-quad swept face.
  Filed to `board/inbox/` as its own item rather than guessed at here.
- **Runs spanning more than one brush** — exit 2 naming the brushes.
- ~~`brush poly scale`~~ — **pulled INTO this change** on the owner's 2026-07-26 ruling; see §2.5.
- Fixing `level photo --native`'s inability to render a revolve (spike finding 6; filed). It makes
  this feature harder to *verify* but does not change its design.

## 7. Owner confirmation still required

Per `CLAUDE.md` "Direction docs", the durable landing of §3.1 in `direction/conventions.md` needs the
owner's explicit yes and a `Confirmed: conventions` trailer. Until then the proposed text is parked
verbatim as an `[OWNER — confirm]` item on `board/inbox/`, so it survives this session.

**Nothing is outstanding on the design.** Every gap the review rounds raised is now closed, and §3.1
carries the complete ruling set rather than the first six:

- the **owner's** thirteen rulings are §3.1, parked verbatim on `board/inbox/` in the two
  `[OWNER — confirm]` items ("The per-surface verb split" — rulings 1–6 — and "SEVEN further
  per-surface rulings" — rulings 7–13). **Keep §3.1 and those two items in step** — the same text is
  awaiting the same yes. (The board's `[resolved]` pre-walk entry records how ruling 3 was *resolved*;
  it is not a fourteenth ruling and is not the parked text.)
- the **algorithm** questions the re-gate left open are decided in §2.4.1 (branching, with no cap
  predicate at all; connectivity as one component of maximum degree 2; the derived root **and walk
  direction**) and §2.4.2 (terminal faces, where the two phase zeros sit, and the across-run axis
  convention). Those are **agent** choices, so they land in the `rationale/` tree — the new
  `polyalign` topic that step 4 creates, beside the existing `rationale/surface.md` — and need no
  owner confirmation; they are listed in §3.2 with their rejected alternatives.

**TWO product narrowings** this rewrite answers rather than defers, and which the owner may want to
overrule. Both change how **existing content renders**, which is the one thing
`direction/conventions.md` "No back-compat cruft" singles out as needing thought before it is
changed ("the T3D trees are the one place to **think** before deleting, because a user's *content*
lives there"). Both are parked on `board/inbox/` beside the ruling text, so neither can be lost
with this spec.

**(1) Deleting the `wall`/`floor` coplanarity and co-orientation guards** (§2.3). **State the
consequence honestly, because an earlier draft of this section put a false premise in front of the
owner:** it is *not* true that "there is nothing left to mirror". A byte-identical frame is exactly
what mirrors two opposite-facing coplanar faces — they are viewed from opposite sides, so one
world→UV map reads reversed on the back one, which is what the co-orientation guard's own comment in
`polyalign._coplanar_align` ("would share the frame but render the texture MIRRORED") says today.
What ruling 9 changes is whether that is a *fault*: the editor's projection family is polarity-blind
by construction (`proj(B)` and `d/N.A` are invariant under `N → −N`), and a world-axis grid has no
notion of facing, so under ruling 9 the mirroring is the family's defined behaviour rather than an
accident the guard was catching. The narrowing to accept or overrule is therefore: **a double-sided
wall that errors today will succeed and come out mirrored on its back face.** Both `wall`/`floor`
and `run` behave this way (§2.4.2), by the same invariance.

**(2) `align run` FLIPS THE TEXTURE VERTICALLY on every cylinder already wrapped by `--ring`.**
§2.4.2's across-run convention puts `V = 0` on a cylinder's **top** rim with V growing downward,
where today's `--ring` puts it on the **bottom** rim with V growing upward. The reasoning is that a
UE1 texture's `V = 0` row is its top (`unrealed/texalign.md` `WALLDIR`; §2.6), so today's `--ring`
renders an asymmetric texture upside-down, and `align wall` and `align run` on the same cylinder
currently disagree by 180°. **But the consequence is that re-running the alignment on any existing
wrap re-renders it mirrored vertically** — a change to how already-authored content looks, not just
to what a new invocation produces. Nothing migrates it: the trunk is only re-textured when the
author runs the verb again, so a map keeps its current wrap until someone re-aligns it and then
changes appearance under them. The narrowing to accept or overrule is therefore: **every cylinder
wrap in existing content flips vertically the next time it is aligned.** (`--ring`'s V-up behaviour
cannot simply be kept as an option — `conventions.md` "No back-compat cruft" forbids the "old way"
branch, and keeping V-up would leave `align wall` and `align run` permanently disagreeing.) Pinned
by §4.2's V-down assertions; documented in `usage.md` per §4.3.
