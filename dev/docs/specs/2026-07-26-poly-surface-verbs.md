# Spec — per-surface texture verbs: `pan`, `rotate`, and `align --run`

**Date:** 2026-07-26 · **Status:** gate passed (2 rounds), then extended by owner rulings — world-space align, reset-to-unit, subcommand modes, `one-tile`, and the `--fit-perimeter` tile fix. **Re-gate before planning.** · **Evidence:**
[`../spikes/2026-07-26-poly-rotate-curved-track/`](../spikes/2026-07-26-poly-rotate-curved-track/README.md)

> Ephemeral, per `CLAUDE.md` "Documentation". Once built, the durable half goes to
> `direction/conventions.md` (the owner's rulings — **which needs their explicit yes and a
> `Confirmed:` trailer**, see §7) and `rationale/polyalign.md` (the engineering choices). Do not cite
> this file from a durable doc.

## 1. Problem

UnrealEd surface editing has four canonical operations — **pan, rotate, scale, align**. uedcli ships
pan (as two flags on `brush poly set`) and a narrow align (`brush poly align --wall/--floor/--ring`).
Rotate and scale do not exist. The 2026-07-19 usability probe flagged the two missing ones; the
2026-07-26 curved-track spike then showed the gap is worse than "two verbs missing":

- On a **revolved** brush's flat top face, all facets share one world-axis-aligned frame, so the
  texture runs dead straight across the bend and ignores it entirely (spike finding 1).
- `--ring` (the old flag), the only mode that carries a texture along a curve, **rejects coplanar sets** — exactly
  the case a curved floor/track bed presents (finding 3).
- `brush poly set`'s `--pan-*` flags exist only because pan had nowhere else to live; the verb now
  mixes attribute assignment (texture, flags) with frame transformation.

Result: a curved track bed — a routine level-design shape — cannot be textured correctly by any
combination of shipped verbs.

## 2. The verb set

| Today | Proposed | Why |
|---------------------------------------|-----------------------------------------|---
| `brush poly set --texture --add-flag --remove-flag --pan-to --pan-by` | `brush poly set --texture --add-flag --remove-flag` | `set` assigns STORED per-face fields. Pan/rotate transform the FRAME. Two different jobs. |
| — | `brush poly pan (--to \| --by) U,V` | integer texel offset, promoted out of `set` |
| — | `brush poly rotate --by UU` | a face on its own terms; no continuity guarantee |
| `brush poly align --wall \| --floor [--fresh-frame]` | `brush poly align wall \| floor` | mode becomes a SUBCOMMAND; aligns to WORLD SPACE, not a seed face; `--fresh-frame` deleted |
| `brush poly align --ring [--fresh-frame] [--fit-perimeter]` | `brush poly align run [--turn UU] [--fit-perimeter]` | generalised from "cylinder sides" to any connected run; coplanar sets allowed |
| — | `brush poly align one-tile` | fit exactly one tile to each face — signs, monitors, light panels |
| — | `brush poly scale (--to \| --by) U,V` | the fourth canonical surface op; the only general density control |

### 2.0 Modes are SUBCOMMANDS, not a mutually-exclusive flag group

`brush poly align <mode> <targets…|->`, with `<mode>` one of `wall`, `floor`, `run`, `one-tile`.
Owner ruling 2026-07-26. The reason is that **the flags are disjoint per mode**:

| mode | valid flags | shape of the operation |
|------------|--------------------------|---
| `wall` | — | stamp a world basis on coplanar faces; guarded vertical |
| `floor` | — | same, guarded horizontal |
| `run` | `--turn`, `--fit-perimeter` | walk a connected run, carry phase across seams |
| `one-tile` | — | per-face fit; no continuity, no orientation guard |

As a flag group that cannot be expressed: `-h` shows one blob in which most options are invalid for
most modes, and every bad combination has to be caught at runtime — `polyalign.align()` already
carries `"--fit-perimeter applies only to --ring"`, and the review rounds found the *missing*
`--turn`-with-`wall` and `--fit-perimeter`-with-`wall` paths. As subcommands those errors become
**structurally impossible** (argparse rejects them) and `brush poly align run -h` lists exactly the two
flags that apply, which is what `CLAUDE.md` requires of `-h`.

It also matches the precedent already in the CLI: **`brush build <shape>`** is the same problem — one
operation, several parameterised variants with disjoint flags (`--sides` for cylinder,
`--angle`/`--segments` for revolve, `--point` for extrude) — and it is already solved this way. The
cost is depth (`brush poly align run` is four levels); consistency with `build` outweighs it.

Per `CLAUDE.md` "No back-compat cruft": `--pan-to`/`--pan-by` on `set`, the `wall`/`floor`/`--ring` (the old flag)
**flag** spellings, and `--fresh-frame` are **deleted outright** in the same change. No aliases, no
shims.

### 2.1 `brush poly pan (--to | --by) U,V`

Straight promotion of the existing flags. Targets are `BRUSH:SELECTOR` positionals or `-`; `-` is the
sole source; empty stdin is a clean no-op (exit 0). Exactly one of `--to`/`--by` is **required** — a
required mutually-exclusive argparse group, with its own message. (Do *not* carry over
`apply_surface_edit`'s "at least one of …" text: that is `set`'s, it names five flags, and its rule is
*at least* one rather than *exactly* one.) Values are **integer texels**, written to the polygon `Pan`
field.

**Target grammar across the three per-face verbs.** `align` also accepts a bare brush Name meaning
all its polys (`resolve_align_targets`); `pan` and `rotate` take `BRUSH:SELECTOR` only. That asymmetry
is deliberate — a whole-brush pan is meaningful, a whole-brush *run* is what `align` is for — but it
must be stated, since ruling 2 unifies their **output** and a reader will assume the input matches. A duplicate/overlapping target set is **deduped before
applying**, because `--by` is relative and would otherwise double-apply (`surface.apply_surface_edit`
already does this deliberately — carry it forward).

`--to 0,0` clears the pan, which emits **no `Pan` line** (`t3d.md`: an absent `Pan` ≡ zero; see the
2026-07-26 `emit` fix).

**It never touches `Origin`.** The precise safety claim — an earlier draft overstated this:

- `run` writes its continuity offset into the float `Origin`, so **a uniform `pan` applied to the
  whole run preserves continuity**;
- **panning a SUBSET of a run breaks it**, because those faces' U shifts relative to their
  neighbours. This is easy to do by accident, since the idiom is `poly find … | poly pan -` and
  `find` filters. Document it;
- **pan-then-align loses the nudge**: `_write_world_frame` writes the seed's `Pan` onto *every* face,
  so a later align overwrites per-face pans. Ordering is pan-**after**-align, and the docs must say so.

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
  `mover key rotate` and the `level preview` pose grammar.
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
  face whose stored axes have a normal component **exits 2 naming the face** rather than being
  silently projected — with a **relative tolerance**: `|axis·n̂| / |axis| > 1e-3`. An exact-zero test
  would reject ordinary content, since `emit.clean`'s `CLEAN_EPS` snapping and a normalised cross
  product both leave dust, and the batch is all-or-nothing so one noisy face would kill the whole
  invocation. Pin both sides of the threshold.
- **No continuity guarantee.** Applied across a run, each face pivots about its own centroid, which
  breaks the seams `run` matched — and equally breaks a `wall`/`floor` shared frame. This is
  the verb for a one-off face (a sign, a panel, a soffit). Document it, and note the contrast with
  `--run --turn`, which is the run-aware operation.

### 2.3 `brush poly align run [--turn UU] [--fit-perimeter]`

The generalisation of `--ring` (the old flag). Walks a connected run of faces and lays one continuous texture along
it: U follows the run, V across it, phase accumulating along the run.

**Phase accumulates by the CHORD between consecutive seam midpoints** — the straight-line distance,
not the true arc — and it is what makes the phase actually meet at the seam, since the anchor is a
point. Arc length would inject ~0.18 texels of error per seam on the spike's fixture. The chord
*magnitude* matches the shipped `--ring` (the old flag) (`usage.md`: "U advances by each facet's true chord
`2·r·sin(π/N)`", pinned by
`test_polyalign.py::test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n`) — but see the anchor
rule below, which does **not** match `--ring` (the old flag).

**The anchor, stated separately from the advance** (an implementer porting `_ring_align` faithfully
would get this wrong, because today's code anchors at `start[0]`, the *low endpoint* of the seam
edge, `polyalign.py:382`):

- the **along-run** phase anchors at the **seam MIDPOINT** — `U(midpoint) = accumulated chord`. The
  midpoint is what makes `half_width` the lever arm in the shear formula; anchoring at an endpoint
  would measure the inner-radius chord on a flat bend (100.4 uu instead of 112.92 on the fixture) and
  double the shear;
- the **across-run** zero stays where `--ring` (the old flag) puts it today — the seam endpoint with the lower
  projection on the across axis. On a cylinder that is the bottom rim, so **existing cylinder wraps do
  not shift**. Deliberate: a midpoint anchor for both axes would move `V = PanV` from the bottom rim
  to mid-height on every cylinder the tool has ever textured, and `direction/conventions.md` singles
  out the T3D trees as the one place to think before changing, because a user's *content* lives there.

Both anchors are satisfiable by one `Origin`: two constraints, two in-plane degrees of freedom.

**The order the faces are passed in has NO bearing on the result.** Not the chain order, and not the
root either — owner ruling, 2026-07-26. `--ring` (the old flag) today requires the caller's whole input order to be
the chain order and errors otherwise; `poly find` emits poly-index order, which the author neither
controls nor sees, so any dependence on it is a hidden coupling.

`run` therefore does a **PRE-WALK** before aligning anything:

1. Build the shared-edge adjacency map over the set, and compute every member's neighbour count.
2. **Branch check** — any face with **3 or more** neighbours in the set exits 2 naming the face and
   its count: *"face `BRUSH:idx` has N neighbours in the set; a run cannot branch — align each arm as
   its own set"*. A run's phase cannot fork: at a junction it would have to be simultaneously
   consistent along two continuations, and nothing picks which arm continues. Catching it in the
   pre-walk gives a specific message instead of a mid-walk surprise.
3. **Root selection**, entirely derived:
   - an **open** run has exactly two degree-1 ends; the root is the one with the **lower poly index**;
   - a **closed** run has no ends, so the root is the **lowest poly index in the set**, and the seam is
     its shared edge with its own lower-indexed neighbour.
4. Walk from the root, which fixes the phase zero, the seam, the walk direction, and whose frame is
   adopted for density and `Pan` — all reproducibly, from geometry and index alone.

**Consequence, stated because it is a real change:** the author can no longer place the seam of a
closed run, which input order allows today. Accepted deliberately — `--fit-perimeter` makes the
closing seam exact, so on the shipped cylinder workflow the seam's position stops mattering, and a
determinism that cannot be perturbed by an upstream filter is worth more than the control it replaces.
There is deliberately **no `--seam` flag**.

**The per-face run tangent is `unit(exit_seam_midpoint − entry_seam_midpoint)`** — stated because it
is load-bearing and only coincides with an endpoint-derived tangent on a cylinder; take endpoints on a
flat bend and the phase stops meeting.

**Edge coincidence is a DISTANCE test, not bucket rounding.** Two edges coincide when their endpoints
are within `_WELD` (0.5 uu) of each other, matched **unordered** (either endpoint to either). Note
`polyalign._edge_eq` is NOT the rule to copy: it compares only the *bottom* endpoints of two
axis-parallel edges, which is valid only under the cylinder-axis assumption `run` deletes. The spike prototype
buckets coordinates (`round(p / 0.5)`), which mis-welds any pair straddling a bucket boundary — a real
risk on a revolve's off-grid vertices after `emit.clean` snapping, and it would surface as a phantom
fork or a phantom disconnection rather than as anything obviously wrong. Do not port the prototype's
version.

**Closed runs are supported.** Not optional: the wrap-a-cylinder workflow
(`poly find Tower --item Side | poly align --ring -`) is the only `--ring` (the old flag) use that ships, is
documented in `usage.md` and `architecture.md`, and is covered by eight `test_ring_*` tests.

**`--fit-perimeter` is BROKEN as shipped and must be fixed in this change.** It is documented as
giving "an exact seam meet" and does not: it snaps the total U advance to a whole number of **texels**
(`target = max(1, round(total_chord * density_u))`), but a texture repeats every **W texels**. Measured
on the standard 8-sided R=256 cylinder with a 256-wide texture:

| | total U advance | visible mismatch (mod 256) |
|--------------------------|-----------------|---
| default (leave the seam) | 1567.472357 | 31.47 texels |
| `--fit-perimeter` today | 1567.000187 | **31.00 texels** |
| corrected (whole tiles) | 1535.999876 | **0.0001 texels** |

So it removes 0.47 texels of a 31.47-texel error. **The corrected rule is
`target = max(1, round(total/T))·T`** — a whole number of TILES, with the `max(1, …)` clamp the shipped
code already carries for a reason: `round(total/T)` is 0 for any run shorter than half a tile, giving
density 0 and a zero-length `TextureU`, which `builders._tex_basis`'s docstring says *crashes REBUILD*.

**`T` is the pixel size of the axis the along-run advance LANDS IN**, not always the width: at
`--turn 0` that is the texture's `USize`; at `--turn 16384` the advance sits in V, so it is `VSize`.
Non-square textures are real (the texalign spike's own fixtures are 256×64 and 128×256), so using `W`
unconditionally is a 4× error on exactly the case the quarter-turn note was added to protect.

The catalog records both (`texture_catalog` entries carry `width`/`height`), so it resolves offline —
but it means `align run --fit-perimeter` **requires a resolved project and a synced catalog**, and
exits 2 naming what is missing for: a texture absent from the catalog, a face with **no** texture at
all (every freshly built brush), a run whose faces carry **different** textures (one density cannot
satisfy two), or no catalog at all. Prototyped and measured by
`spikes/2026-07-26-poly-rotate-curved-track/fit_demo.py`.

**The plumbing seam must be specified, because `polyalign` has no project context today** (it is
documented as pure model-side texture-vector math taking only a `Level`). The CLI layer resolves
`(USize, VSize)` for the run's texture and passes it into `polyalign`; `polyalign` does **not** import
`texture_catalog`. That also gives the unit tests their injection point — every existing
`test_polyalign.py` fixture builds a bare `Level` with no project, so without an injectable size the
§4 fit-perimeter pins are not implementable at all.

Note this is the **same dependency `one-tile` needs**, so the texture-catalog coupling is not new to
that mode — `--fit-perimeter` has needed it since it shipped and has been quietly wrong without it.

**`--fit-perimeter` requires a CLOSED run and a quarter `--turn`**, exiting 2 naming the offending
value otherwise:

- on an **open** run — the flag snaps the density so an integer texel count closes the loop, and a run
  with no closing seam has no loop to close. Fitting a texture to an *open* run is a legitimate but
  **different** operation (and would want a different flag name); filed to `board/inbox.md` rather
  than folded in here;
- at a **non-quarter** `--turn` — the advance then splits across both stored axes
  (`ΔU = d_u·S·|cos θ|`, `ΔV = d_v·S·|sin θ|`), so closing the loop would need *both* components to
  land on integers, which scaling one density cannot achieve. Silently fitting one is exactly the
  half-answer `direction/conventions.md` forbids.

At a quarter turn it fits the **along-run** axis regardless of which stored axis currently holds it —
at `--turn 16384` the along-run advance sits in V, and fitting the axis merely *called* U would be
silently wrong.

**Coplanar sets are valid.** Today's `--ring` (the old flag) rejects them (*"all faces are parallel — not a ring"*);
that rejection is deleted. Note this does **not** collapse `run` into `wall`/`floor`: on the same
coplanar set, `floor` yields one shared frame (texture straight across) and `run` a turning frame
(texture follows the curve). Both are wanted; they are different operations on the same input.

**There is NO seed, and `--fresh-frame` is DELETED from `brush poly align` entirely.** `--fresh-frame`
existed only to choose between "canonical" and "adopt the seed's density/pan"; with adopt-seed gone it
is a flag with one possible value, so per "No back-compat cruft" it goes.

**Owner ruling 2026-07-26: `wall` and `floor` are WORLD-SPACE aligned; `one-tile` is FIT TO THE
POLY.** Those are two different things and the difference is the point — world-space means the frame
ignores the individual face entirely; fit-to-poly means it is derived from that one face.

| mode | orientation | **anchor** | density | pan |
|------------|-----------------------------------|-----------------------|--------------------|---
| `wall` / `floor` | **the editor's projection family** (§4b) — orthographic projection down a world axis | **world axis**: where the surface plane crosses the projection axis | `1/\|proj\|` — unit only on a face square to the axis | (0,0) |
| `run` | along/across the run, from the walk | the seam midpoint (§ above) | 1 texel/uu, unless `--fit-perimeter` | (0,0) |
| `one-tile` | `builders._tex_basis(n̂)` | the face's min corner along those axes | **fit to the face**: `W/E_u`, `H/E_v` | (0,0) |

**Owner ruling 2026-07-26: `wall`/`floor` adopt the EDITOR's orientation**, i.e. `POLY TEXALIGN`'s
`FLOOR`/`WALLX`/`WALLY` family, measured in §4b — not `builders._tex_basis`. Concretely, for
projection axis `A` with `N` the surface normal and `d = N·P`:

- `floor` → `A = Z`; `wall` → `A` is whichever of **X or Y** the face faces more (larger `|N.A|`),
  which is the one thing we add: the editor makes the author choose `WALLX` vs `WALLY`, we derive it.
- `TextureU`/`TextureV` = `−proj` of the other two world axes, where `proj(V) = V − N(N·V)` and is
  **deliberately not renormalised**;
- `Origin` = the plane's crossing of `A` (`(0,0,d/N.Z)` for `floor`, `(d/N.X,0,0)` / `(0,d/N.Y,0)` for
  `wall`); `Pan` = (0,0);
- guard `|N.A| > 0.05`, replacing today's dominant-axis `_check_orientation`. This is far more
  permissive: `floor` now accepts anything up to ~87° off horizontal.

⚠ **This makes `wall`/`floor` density NON-UNIT on any face not square to its projection axis** — the
`1/|proj|` stretch of §4b (a 45° ramp → `|TU| = 0.707`; a measured face → 2.8×). That is the editor's
deliberate behaviour and it is *useful* — a ramp's texture stays continuous with the flat floor it
meets — but it means the reset-to-unit ruling now applies to `run` alone, and the `wall`/`floor`
row above says `1/|proj|`, not 1.

**The world anchor is what makes `wall`/`floor` idempotent.** Identical *axes* are not identical
*frames* — phase lives in `Origin`, so a face-derived anchor (today's `_coplanar_align` uses the seed
face's centroid, `polyalign.py:254`) gives two invocations over different subsets of one plane
different phases. With a world-derived anchor, aligning face A alone and face B alone produces
byte-identical frames and re-running is a no-op. That is the property the ruling is for, it must be
pinned, and it matches the editor, which anchors `FLOOR`/`WALLX`/`WALLY` on a world axis (§4b).

**`one-tile` is deliberately exempt from unit density** — a fit-to-poly mode whose density comes from
the face is the one thing that cannot also be 1 texel/uu.

**Open, and NOT assumed:** `one-tile` still takes its orientation from `_tex_basis(n̂)`, whose in-plane
choice ("the world axis least aligned with the normal") is unpredictable on a slanted face — so a sign
can come out sideways, for the one use case the mode exists to serve. Adopting the same
projection-axis *directions* (normalised, since `one-tile` supplies its own density) would make the
up-vector predictable. The owner's ruling was scoped to `wall`/`floor`; this is filed rather than
silently extended.

**`wall`/`floor` therefore align to WORLD SPACE, not to any one poly** (owner ruling). Because
`_tex_basis` depends only on the normal, two coplanar co-oriented faces receive *identical* frames
whether or not they were aligned together — continuity stops being computed and becomes structural.

⚠ **This is DESTRUCTIVE on imported content, and must be documented as such.** Real maps carry
deliberate texel scales: across the committed editor fixtures, 17 of 253 `TextureU` magnitudes are
non-unit, 14 of them exactly `0.667` (= 2/3, authored, not float noise). Aligning imported geometry
resets those to 1:1, and **there is currently no verb that can put them back** — `--fit-perimeter`
(closed runs only) is the sole remaining channel to a non-unit density. Accepted deliberately; it
raises the priority of `brush poly scale`, and `usage.md` must warn about it at the point of use, not
in a footnote. `brush poly scale` (§2.5) is the general control that puts a density back; `one-tile`
and `--fit-perimeter` reach non-unit densities too, but only for their own specific fits.

**`--turn UU`** applies a uniform **rigid** turn in each face's own **run frame**, not in world space,
so every face receives the same transform relative to the run and the along-run density follows the
along-run direction into whichever stored slot it lands in. The chord advance is accumulated as a
displacement vector in the face plane and expressed in the rotated basis, so it distributes across
both axes.

**The across-run axis direction must be specified**, because the cylinder axis that supplied it is
gone: it is `n̂ × t̂` (face normal × run tangent), with the same determinism tie-break `--ring` (the old flag) uses
today (orient "+Z-ish"; `polyalign.py:308`). Seam continuity alone does not pin this — a cylinder
aligned upside-down and backwards is equally continuous — so it needs its own assertion.

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
deliberately left open and measures the full perimeter (1567.47 on the spike's cylinder) — printing
it as "worst-case shear" every time would be noise, not information.

**Guards carried over from `--ring` (the old flag)**, which must not be lost in the generalisation: single-brush
(a multi-brush set exits 2 naming the brushes — see §6), `< 2 faces`, and the **cap-face rejection**
with its actionable message (`"exclude caps, e.g. brush poly find <brush> --item Side | …"`).

That guard needs a **new predicate**, because today's is `|n̂·axis| > _RADIAL_EPS` against a cylinder
axis derived from two non-parallel side normals — and coplanar runs, which `run` now accepts, have no
such axis. **Specify it by the SHARED EDGE, not by normals.** A run adjacency crosses an edge that is
*across* the run — perpendicular to the run tangent. A cap adjoins its neighbours along an edge that
runs *with* the neighbour's tangent (the rim). So: a member sharing an edge **parallel to its
neighbour's run tangent** (within a stated tolerance) is a cap and gets the cap-specific message.

An earlier draft specified this as "a member whose normal is not perpendicular to the run tangent of
each face it adjoins", which is **wrong in both directions** and would have shipped: a cylinder cap's
normal is the axis and the side tangents are tangential, so `n̂·t̂ = 0` — perpendicular, so the cap
passes and gets walked into; while for a legitimate side face `n̂_k · t̂_{k+1} = sin Δθ` = 0.707 on an
8-gon — not perpendicular, so **every real side face** is rejected as a cap.

**The cap check must run BEFORE the branch check.** On the flagship fixture the cap shares an edge with
all 8 sides, making it a degree-8 node: with the branch check first it trips *"a run cannot branch"*
and the author never sees the `--item Side` hint. `test_ring_rejects_cap_face` pins that message, and
§4 requires it to survive.

### 2.4 `brush poly align one-tile`

Fit **exactly one tile of the texture to each face** — the sign / monitor / light-panel case. Owner
request 2026-07-26.

- **Per-face and independent.** Each face gets its own density and anchor; there is no shared frame
  and no continuity between faces. That is why it is its own mode rather than a flag on `wall`/`floor`,
  which would imply a shared frame it structurally cannot provide.
- **No orientation guard.** Unlike `wall`/`floor` it accepts **any** face orientation — a sign goes on
  a slanted face as happily as a vertical one.
- **Orientation** comes from `builders._tex_basis(n̂)`, the same world-derived basis `wall`/`floor` use.
- **It STRETCHES to fill, non-uniformly.** One tile spans the face's U extent and one tile its V
  extent, so the image fills the face exactly and is distorted when the aspect ratios differ. That is
  the point: a letterboxed sign is wrong, and authors size the brush to the sign or vice versa.
  Aspect-preserving fit is a different operation and belongs to `brush poly scale`, where U and V
  density are set explicitly.
- **Anchor: the MINIMUM corner of the face's extent** measured along the chosen U/V axes (the min of
  the vertices' projections). Texture `(0,0)` lands there, so the tile covers the face's bounding box
  exactly. Deterministic, because the axes are a pure function of the normal. Rejected: centroid
  anchoring, which needs a half-extent offset to mean the same thing and is harder to reason about.
- **On a NON-RECTANGULAR face** (a triangle, a trapezoid, a cap tile) the tile covers the *bounding
  box*, so the face shows a sub-region of the texture. Documented, not discovered.
- **Requires the texture catalog**, for the same reason `--fit-perimeter` does: `|TextureU| = W / E_u`
  needs the texture's pixel size. Exit 2 naming the ref when it is not in the catalog.

Open, flagged rather than decided: `one-tile` is arguably a **scale** operation wearing an align hat —
it sets density and anchor, not a shared frame — so it will overlap `brush poly scale` when that
lands. Kept under `align` because the author's intent is "make this texture fit this face", which is
alignment.

### 2.5 `brush poly scale (--to U,V | --by FU,FV)`

The fourth canonical surface op, pulled into this change on the owner's 2026-07-26 ruling. After
reset-to-unit it is the **only general way to express a texel density**: `one-tile` fits one tile to a
face and `--fit-perimeter` closes a loop, but neither lets an author say how big a texture should be.

Targets are `BRUSH:SELECTOR` positionals or `-`, same grammar as `pan`/`rotate`; `-` is the sole
source; empty stdin is a clean no-op; the target set is **deduped** (`--by` is relative and would
otherwise compound).

- **`--by FU,FV` multiplies the texture's APPARENT SIZE**, so `--by 2,2` makes the texture look twice
  as large. Note that this *divides* the stored magnitudes (`|TextureU| ← |TextureU| / FU`), because
  T3D density is texels-per-world-unit — bigger magnitude means a smaller-looking texture. The verb is
  named for what the author sees, not for what is stored, and the help must say so or the sign of the
  effect will surprise everyone once. Pure math, no catalog needed.
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

### 2.6 Frame construction, and what it costs

Orthogonal axes, phase measured on **one reference radius (the centreline)**.

**Where the seams are exact, and where they are not** (spike findings 4–5, and the round-1
correction):

- **A run whose seams are parallel to the turn axis — cylinder sides — is EXACTLY continuous on both
  axes, at every `--turn` angle.** Measured on the shipped `--ring` (the old flag) (all 7 interior seams of a closed
  8-sided cylinder, ΔU = ΔV = 0.000000) and on an open 7-face sub-run at turns 0, 8192 and 5000
  (same). `run` must preserve this.
- **A run whose seams lie IN the plane of the turn — a flat bend, like the track bed's top — shears
  one axis** by `S = 2·sin(Δθ/2)·half_width` world units, appearing on each stored axis scaled by
  **that axis's own density**: `ΔU = d_u·S·|cos θ|`, `ΔV = d_v·S·|sin θ|`. **`half_width`** is the
  greatest distance from the phase reference (the seam midpoint) to a seam endpoint — the cross
  section need not be symmetric about the centreline. The other axis is exact at **multiples of a
  quarter turn** (`--turn 0` included, which is the default and the case §4 tests). This also assumes
  a **uniform** per-facet turn — the seam must bisect it; unequal turns break the even-cosine
  cancellation that makes the exact axis exact.

**What this means for corners, which is the first thing an author will ask.** The discriminator is the
seam's orientation relative to the turn, not how sharp the turn is — so a 90° corner can be perfect or
unusable depending only on which way the seam runs:

| run | seam vs turn | measured |
|-----------------------------------------|-------------------|---
| L-shaped **wall**, 90° corner | ∥ the turn axis | **ΔU = ΔV = 0.000000**, at `--turn` 0 and 8192 |
| flat bend, Δθ = 45° (2-segment revolve) | in the turn plane | ΔU = 48.98 (closed form 48.983) |
| flat **L**, Δθ = 90°, 128 uu wide | in the turn plane | 90.5 texels (closed form) |

A wall run turning a corner is exact and needs no compromise. A **flat** corner is the pathological
case: 90.5 texels of shear out of a 256-texel texture, at one seam — and unlike a revolve it cannot be
improved by adding segments, because Δθ is fixed by the corner itself. This is what the stderr shear
report is for: on a flat L it prints ~90 and tells the author to mitre the corner or accept a visible
seam, at the moment they need to know.

Any **degree-2 chain** runs, including the minimal two-face case (two faces, one seam, both ends).

The alternative — a sheared, non-orthogonal frame — is exactly continuous on **both** axes but
stretches by `√(1+ψ²)` (86% at the end of a 90° bend) and skews the frame to 34°, and **neither
degradation is reducible by segmentation**, whereas the orthogonal frame's shear halves with every
doubling of `--segments`. Measured both ways; see finding 5.

## 3. Decisions

### 3.1 Owner rulings (2026-07-26)

| # | Ruling | Rejected, and why |
|---|--------|---
| 1 | **Pan moves out of `poly set` into its own verb.** | Leaving it on `set` — the `--pan-to`/`--pan-by` compound spelling exists only because it shares a verb; alone it is `pan --to/--by`, matching every other transform in the CLI. |
| 2 | **Per-face mutators echo `BRUSH:idx` on stdout**, not touched brush names. Applies to `poly set`, `poly pan`, `poly rotate` **and `poly align` (all modes)**. | Keeping brush-name output — a bare name means *all* that brush's polys, so a second per-face verb in the pipe silently widens the set. |
| 3 | **`run` orders the chain itself, and the order faces are passed in has NO bearing on the result — the ROOT is derived by a pre-walk too** (lower-poly-index end; lowest index on a closed run). Confirmed 2026-07-26, superseding the reviewers' "root = first input token" proposal. | Trusting pipe order for the whole chain, as `--ring` (the old flag) does — `find`'s order is not author-controlled. Consequence: no `--centre` flag is needed. |
| 4 | **`run` DERIVES the frame; it does not preserve the caller's rotation.** Fixups afterwards are quarter-turn flips and small texel pans. | Preserve-and-compose (`rotate --bend \| align --run`) — proposed by the agent, rejected by the owner, and vindicated by the spike: rotation alone leaves the phase broken (finding 2) and `run` deriving solves the case outright (finding 3). |
| 5 | **The turn is a scalar angle in unreal rotation units, folded into `run`, spelled `--turn`.** | `--rotate` — collides with `brush build --rotate` (actor orientation, a triple) and, worse, with `brush poly rotate` in the same noun, where the same word would carry the opposite continuity guarantee. A boolean `--across` — covers only quarter turns. A separate post-pass — pivots each face about its own centroid and re-breaks the seams. |
| 6 | **`--ring` (the old flag) is renamed `run`.** | Keeping `--ring` (the old flag) — a 90° arc is not a ring, and an author would not find the flag; `run` is already the codebase's own word (`polyalign._check_orientation`: *"turning runs deferred"*). |

Rulings 5 and 6 were confirmed 2026-07-26 after the review round raised both as open.

### 3.2 Agent choices (→ `rationale/polyalign.md` on landing)

- **Orthogonal frame, centreline reference radius** — from the measured trade in §2.4, not taste.
  Also answers the owner's deferred arc-length question: per-strip arc length and the sheared frame
  are *the same construction*, so option (a) is rejected on that evidence; per-facet fit (option c) is
  disqualified because it reproduces the restart defect.
- **Chord, not arc**, for the phase advance.
- **Adjacency walk with the root DERIVED by pre-walk** (lower-poly-index end; lowest index on a
  closed run) — no dependence on input order.
- **Exact component path at quarter turns**, scoped to axis-aligned orthogonal frames.
- **Non-quarter `--turn` allowed + stderr shear report**, rather than an error.

## 4. What the implementation must pin

`rules/spikes.md` requires a checkable finding to ship with a regression, and `CLAUDE.md` requires
every named-error path to carry one. Non-negotiable:

**Continuity**
- **The eight existing `test_ring_*` tests are carried over to `run`** — renamed, but their
  assertions kept unless the reset-to-unit ruling genuinely changes the answer. *This is the most
  important item in the change*: the cylinder wrap is the only capability that ships today.
  **Which ones legitimately change, and why**, so nobody relaxes a test to make it pass:
  `test_ring_fresh_frame_unit_density_and_continuous` loses its `fresh_frame=True` and becomes the
  default case. `test_ring_keeps_pan_integer` seeds `pan = (3,5)` and asserts it is carried — under
  reset-to-unit the answer is `(0,0)`, so its assertion inverts. `test_ring_leave_seam_vs_fit_perimeter`
  and `test_ring_fit_perimeter_closes_the_seam` both assert the **integer-texel** rule and must be
  re-derived against whole TILES — and both run on *untextured* `cylinder(200,100,7)` fixtures, so they
  need a bound texture plus an injected `(USize, VSize)`; that fixture work is a precondition for the
  change's most important regression set, not an afterthought.
  `test_wall_adopt_seed_preserves_seed_pan` pins adopt-seed and is **DELETED**, not adapted
  ("No back-compat cruft"). Everything else — continuity, the rotated/relocated cylinder, the cap and
  multi-brush errors — must survive **unchanged**. Add an explicit assertion on the **across-axis
  direction and handedness**: the sign is fixed once at the root and **propagated along the walk**, not
  recomputed per face against a world axis, which would flip mid-sweep on a turning run and mirror V.
- **Cylinder runs stay exact under `--turn`** — ΔU = ΔV < 2e-3 at turns 0, 8192 and 5000.
- **Flat-bend shear matches the closed form** — assert `|max ΔU − d_u·2·sin(Δθ/2)·half_width| < 2e-3`
  and `max ΔV < 2e-3`, stating the fixture. **Do NOT pin six-decimal goldens**: the same alignment
  re-run over an already-aligned trunk moves them (12.546615 → 12.546781 → 12.6278) because
  `emit.clean`'s `CLEAN_EPS` snapping accumulates on off-grid vertices. Port `spikes/…/seam_check.py`
  as the measurement.
- **Turn axis selection, stated by STORED COMPONENT** (not by "along/across", which inverts and is
  easy to misread): on the flat-bend fixture, `--turn 0` gives `ΔV < 2e-3` with `ΔU ≈ 12.55`;
  `--turn 16384` gives `ΔU < 2e-3` with `ΔV ≈ 12.55`; `--turn 8192` gives both `≈ 8.87`.

**Behaviour**
- **Ordering invariance** — shuffling **all** tokens, the first included, produces a byte-identical
  result. Plus a positive pin on the derived root: an open run roots at its lower-poly-index end, a
  closed run at its lowest index. (An earlier draft pinned "changing the first token moves the seam",
  which asserts the opposite of the ruling and cannot pass.)
- **`wall`/`floor` idempotence** — aligning face A alone and face B alone (same plane, separate
  invocations) yields byte-identical frames; a second run over the same set changes nothing.
- **`scale`** — `--by 2,2` halves the stored magnitudes (texture looks twice as big); `--to 128,128`
  on a `W×H` texture gives `|TextureU| = W/128`; the face centroid's `(U,V)` is unchanged by both;
  `Pan` untouched. `--by` needs no catalog, `--to` does.
- **`one-tile`** — a `W×H` texture on an `E_u × E_v` face gives `|TextureU| = W/E_u`,
  `|TextureV| = H/E_v`, `Pan` (0,0), `Origin` at the min corner; a rectangular face's corners map to
  (0,0), (W,0), (W,H), (0,H); a triangle maps its bounding box; a zero-extent axis and a
  texture missing from the catalog each exit 2 naming the face or the ref.
- **Coplanar sets are accepted** by `run` (the deleted "all faces are parallel" rejection).
- **`--fit-perimeter`** closes a closed run exactly, in whole TILES.
- **Quarter-turn exactness**, split by verb because they are different assertions:
  (a) `brush poly rotate --by 16384` on a `+Z` face with `TextureU=+X, TextureV=+Y` yields exactly
  `TextureU=+Y, TextureV=−X` — this is also the **sign** pin;
  (b) `align --run --turn 16384` produces axis **directions** identical to the `--turn 0` axes
  swapped/negated, with each axis keeping its own magnitude. Bit-identity is only well-posed under
  `--fresh-frame` (densities 1/1) on an **unrotated** brush — `_write_world_frame` inverse-transforms
  through `R` — so scope the test that way or assert directions only.
- **`brush poly pan --to`/`--by`**, including `--to 0,0` emitting no `Pan` line, and dedup of an
  overlapping target set (no double-apply). Same dedup pin for `rotate`.
- **stdout format** — every per-face mutator emits `BRUSH:idx` lines that `-` re-consumes. The model
  functions keep returning **brush names** for `src.save(touched=…)`, which is a session-store
  contract; only the CLI print changes.

**Error paths**, each a named exit 2 with a regression: fork; disconnected member; edge shared by >2
faces; `< 2 faces`; cap faces included (the cap-specific message, per §2.3's predicate); multi-brush
set; non-quad face; `--to` with `--by`; `pan`/`scale` with **neither** `--to` nor `--by`; a zero or
negative `scale` factor; `one-tile` on a face with a zero extent; a texture absent from the catalog,
a face with no texture, or a project with no synced catalog, for each of `scale --to`, `one-tile` and
`--fit-perimeter`; `--fit-perimeter` on an open run; `--fit-perimeter` at a non-quarter `--turn`; a
face whose texture axes have a normal component beyond the §2.2 tolerance.

**NOT error paths, and their tests are DELETED not moved:** `--turn` or `--fit-perimeter` passed to
`wall`/`floor`. Under §2.0's subcommands argparse rejects them before any uedcli code runs, so there
is no uedcli message to name. `polyalign.align()`'s `if fit_perimeter and mode != "ring"` guard
(`polyalign.py:401`) becomes dead code that "No back-compat cruft" requires removing in the same
change, and `test_fit_perimeter_requires_ring` goes with it. Likewise "a root that is not a run end"
is unreachable once the pre-walk derives the root.

**Docs to update in the same change** — a rename with no shim, so every occurrence is a broken
instruction:
- `docs/usage.md` — verb reference, the `poly set` and align sections, and the **"Output streams for
  mutators"** paragraph that lists `poly set`/`align` as printing brush names;
- `docs/leveldesign/general/textures-and-surfaces.md` — lines 16, 24, 25, 55 (`--pan-to`/`--pan-by`
  **and** `--ring` (the old flag));
- `dev/docs/unrealed/leveldesign/kb/textures.md` — lines 19, 72, 74, 253, 254;
- `dev/docs/rationale/emit.md` — lines 49, 56, 69, 77 name `brush poly set --pan-to 0,0` as the
  producer of the zero-`Pan` case, which is the durable rationale §2.1 depends on;
- code comments and messages carrying the deleted spelling: `uedcli/emit.py:164`, `uedcli/query.py:71`,
  `uedcli/surface.py:89` and its "at least one of …" message;
- a curved-run recipe under `docs/leveldesign/general/`, and `dev/docs/architecture.md`.

**`--segments` must be documented as a texture-quality parameter**, with the shear formula **scoped to
flat bends**, and the caveat that doubling segments halves each seam's shear but **doubles the number
of seams**.

**Build order** (`CLAUDE.md` "BATCH small changes" — a subtle change to load-bearing code gets its own
round). Four steps; the earlier two-step order left the riskiest work unsequenced:

1. **`set`/`pan` split + `rotate`** — mechanical promotions, settled semantics, nothing outstanding.
2. **Flags → subcommands**, behaviour otherwise unchanged. One atomic CLI change across all four
   modes plus `usage.md` and the recipes — not separable, and not "mechanical".
3. **`align run`** + the reset-to-unit deletion of adopt-seed — the frame math, reviewed alone.
4. **Catalog plumbing + `--fit-perimeter` tile fix + `one-tile` + `scale --to`** — introduces a new
   cross-module dependency and a project requirement on a verb that is pure model-side today. Riskiest
   step, so it goes last where it gets its own round.

Step 1 is unblocked now; `wall`/`floor` inside steps 2–3 still carry one open owner decision (whether
to adopt the editor's ORIENTATION, §4b) though their world-space anchor is ruled.

## 4b. UnrealEd parity — MEASURED 2026-07-26

Spike: [`../spikes/2026-07-26-unrealed-texalign-semantics/`](../spikes/2026-07-26-unrealed-texalign-semantics/README.md);
verified facts in [`../unrealed/texalign.md`](../unrealed/texalign.md). This section previously
asserted three things the spike **disproved** — they are corrected here, not argued:

| earlier claim | measured |
|--------------------------------------------|---
| "six modes against our two" | **nine** — `commands.md` was missing `DEFAULT`, `WALLPAN`, `WALLCOLUMN` |
| "we cannot say what any of them does" | all nine measured, 396 frames over 44 faces |
| "`ONETILE` — fit exactly one tile to the face" | **`ONETILE` is a NO-OP**; so is `WALLCOLUMN` |

**There is no fit-a-tile-to-a-face operation in UnrealEd 2.2.** `WALLCOLUMN`'s switch entry *is* the
`default:` branch and `ONETILE`'s falls through to the bare epilogue. So **`align one-tile` (§2.4) is
a uedcli INVENTION, not a port** — nothing in the editor constrains it, and its design stands or falls
on its own merits rather than on parity.

**No mode changes texel density.** All nine only choose an in-plane orientation and an anchor, at
1 texel/uu; `TEXELS=<n>` is parsed and never read. Combined with the reset-to-unit ruling (§2.3),
that means **neither tool can currently set a texel scale** except `--fit-perimeter` on a closed run —
which strengthens the case for pulling `brush poly scale` into this work rather than after it.

Measured semantics, with `N` = **surface** normal (reversed vs the brush polygon on a subtractive
brush), `d = N·P`, `proj(A) = A − N(N·A)` **not renormalised**:

- **`FLOOR` / `WALLX` / `WALLY`** — one family: orthographic projection down world Z/X/Y. `TU`/`TV` are
  `−proj` of the other two world axes, `Pan` zeroed, guard `|N[axis]| > 0.05`. The anchor is a **world
  axis** (`(0,0,d/N.Z)` etc.), so every coplanar face shares one grid. A tilted face is **stretched by
  `1/|proj|`** (45° ramp → `|TU| = 0.70711`).
- **`WALLDIR`** — `TU = normalize(N.Y,−N.X,0)`, `TV = normalize(TU×N)`, both negated; unit, never
  stretches, **V always points down**; anchor untouched; guard `|N.Z| < 0.95`.
- **`WALLPAN`** — slides the anchor along `TextureV` to world `Z = 0`; axes and pan untouched.
- **`DEFAULT`** — regenerates the frame from the polygon's own winding; a reset, not a design tool.
- **`CLAMP`** — `DEFAULT` plus `PanV = VSize − 1`.

### Diff against uedcli

| editor mode | uedcli | verdict |
|-------------|-----------------|---
| `FLOOR` | `align floor` | **diverges** on all seven face directions tested (mirror / 180°); anchor differs (world axis vs face centroid) |
| `WALLDIR` | `align wall` | **diverges** similarly, up to a full 90° on a yawed wall; our V points *up* on ~half a room's walls, the editor's is always down |
| `WALLX` / `WALLY` / `WALLPAN` / `CLAMP` / `DEFAULT` | — | **no equivalent** |
| `ONETILE` / `WALLCOLUMN` | `align one-tile` | **nothing to conform to** — the editor modes do nothing |
| — | `align run` | **uedcli-only** |

Divergence is a legitimate outcome — uedcli is model-side and need not mirror an editor UI. But it is
now a visible choice. **Four `[OWNER — decide]` items are parked on `board/inbox.md`** and any of them
can change §2: whether `wall`/`floor` should adopt the editor's orientation; whether the anchor moves
to a **world axis** (which would make alignment idempotent and independent of which faces were
selected — the property the world-space ruling was reaching for, and the editor already has it);
whether `one-tile` is accepted as original; and whether to add `WALLX`/`WALLY`/`WALLPAN` equivalents,
the only editor modes that handle a turning run.

## 5. Sequencing

`board/to-plan.md` carries `specs/2026-07-24-facing-selector-grammar.md`, **both gates passed**, which
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
  Filed to `board/inbox.md` as its own item rather than guessed at here.
- **Runs spanning more than one brush** — exit 2 naming the brushes.
- ~~`brush poly scale`~~ — **pulled INTO this change** on the owner's 2026-07-26 ruling; see §2.5.
- Fixing `level preview --native`'s inability to render a revolve (spike finding 6; filed). It makes
  this feature harder to *verify* but does not change its design.

## 7. Owner confirmation still required

Per `CLAUDE.md` "Direction docs", the durable landing of §3.1 in `direction/conventions.md` needs the
owner's explicit yes and a `Confirmed: conventions` trailer. Until then the proposed text is parked
verbatim as an `[OWNER — confirm]` item on `board/inbox.md`, so it survives this session.

**Nothing is outstanding on the design.** The two gaps the review rounds raised were both ruled by the
owner on 2026-07-26: the run's root is **derived by pre-walk** (stronger than the reviewers' proposed
"root = first input token" — it removes input-order dependence rather than narrowing it), and
`wall`/`floor` are **world-space aligned** while `one-tile` is **fit to the poly**, which settles the
anchor question §2.3 had left open. §3.1 and §2.3 record both as confirmed text.
