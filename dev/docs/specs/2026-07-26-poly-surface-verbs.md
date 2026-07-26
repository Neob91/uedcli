# Spec — per-surface texture verbs: `pan`, `rotate`, and `align --run`

**Date:** 2026-07-26 · **Status:** draft, not yet reviewed · **Evidence:**
[`../spikes/2026-07-26-poly-rotate-curved-track/`](../spikes/2026-07-26-poly-rotate-curved-track/README.md)

> Ephemeral, per `CLAUDE.md` "Documentation". Once built, the durable half goes to
> `direction/conventions.md` (the owner's rulings) and `rationale/polyalign.md` (the engineering
> choices). Do not cite this file from a durable doc.

## 1. Problem

UnrealEd surface editing has four canonical operations — **pan, rotate, scale, align**. uedcli ships
pan (as two flags on `brush poly set`) and a narrow align (`brush poly align --wall/--floor/--ring`).
Rotate and scale do not exist. The 2026-07-19 usability probe flagged the two missing ones; the
2026-07-26 curved-track spike then showed the gap is worse than "two verbs missing":

- On a **revolved** brush's flat top face, all facets share one world-axis-aligned frame, so the
  texture runs dead straight across the bend and ignores it entirely (spike finding 1).
- `--ring`, the only mode that carries a texture along a curve, **rejects coplanar sets** — exactly
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
| `brush poly align --wall \| --floor` | unchanged | coplanar faces, one shared frame, orientation-guarded |
| `brush poly align --ring [--fit-perimeter]` | `brush poly align --run [--rotate UU] [--fit-perimeter]` | generalised from "cylinder sides" to "any connected run", coplanar sets allowed |

Per `CLAUDE.md` "No back-compat cruft": `--pan-to`/`--pan-by` on `set` and the `--ring` spelling are
**deleted outright** in the same change that adds their replacements. No aliases, no shims.

### 2.1 `brush poly pan (--to | --by) U,V`

Straight promotion of the existing flags. Targets are `BRUSH:SELECTOR` positionals or `-`; `--to` and
`--by` are mutually exclusive; values are **integer texels**, written to the polygon `Pan` field.

It **never touches `Origin`**. That is what makes it safe to use after an align: `--run` writes its
fractional continuity offset into the float `Origin` and leaves `Pan` at the seed's value, so an
author's integer nudge and the computed continuity occupy different fields and cannot overwrite each
other. (This division already exists in `poly align` and is preserved deliberately.)

### 2.2 `brush poly rotate --by UU`

Rotates a face's `TextureU`/`TextureV` within the face plane, re-anchoring so the face's world
**centroid** keeps its `(U,V)` — i.e. the texture spins in place rather than sliding.

- `--by` is in **unreal rotation units** (16384 = 90°), matching `brush build --rotate`,
  `mover key rotate` and the `level preview` pose grammar. Positive = counter-clockwise viewed from
  outside the face.
- **A multiple of 16384 MUST be exact.** Rotating an axis through `sin`/`cos` leaves float dust
  (`cos 90° ≈ 6.1e-17`) that lands in the trunk and shows up in every subsequent diff. Detect
  `uu % 16384 == 0` and perform an exact component swap/negate instead. UU makes this a clean integer
  test, which is a further reason the unit is right.
- **No continuity guarantee.** Applied across a run, each face pivots about its own centroid, which
  breaks seams that `--run` had matched. This is the verb for a one-off face — a sign, a panel, a
  soffit — that is not part of a run. Documented as such.

### 2.3 `brush poly align --run [--rotate UU]`

The generalisation of `--ring`. Walks a connected run of faces and lays one continuous texture along
it: U follows the run, V across it, phase accumulating by arc length.

**Ordering is derived, not trusted.** `--ring` today requires the caller's input order to be the
chain order and errors otherwise; `poly find` emits poly-index order, which the author neither
controls nor sees. `--run` builds an adjacency map from shared edges and walks the chain from a
seed. Deterministic while each face has at most two neighbours in the set; a fork, a disconnected
member, or a closed loop with no chosen seam is a clean exit 2 naming the face.

**It DERIVES the frame; it does not preserve one.** Owner ruling (below). The caller does not
pre-rotate anything.

**Coplanar sets are valid.** Today's `--ring` rejects them (*"all faces are parallel — not a ring"*);
that rejection is deleted. A flat annulus is the motivating case. Note this does **not** collapse
`--run` into `--wall`/`--floor`: on the same coplanar set, `--floor` yields one shared frame (texture
runs straight across) and `--run` yields a turning frame (texture follows the curve). Both are wanted
and they are different operations that happen to accept the same input.

**`--rotate UU`** applies a uniform turn in each face's own **run frame**, not in world space, so
every face receives the same transform relative to the run and continuity is computed *with* the turn
rather than broken by it afterwards. Well-defined at any angle, not just quarter turns: the arc-length
advance is accumulated as a displacement vector in the face plane and expressed in the rotated basis,
so it distributes across both axes.

**`--fit-perimeter` gains a closure check.** Under the name `--ring` the flag's meaning came from the
name implying a closed loop. `--run` carries no such implication, so fitting an integer texel count to
an *open* run is a wrong answer that looks right — it must exit 2 when the run does not close.

**Frame construction** (spike findings 4–5): orthogonal axes, phase measured on **one reference
radius, the centreline**. This is exact on one axis and shears the other by
`2·sin(Δθ/2)·half_width` texels. The alternative — a sheared, non-orthogonal frame — is *exactly*
continuous on both axes but stretches by `√(1+ψ²)` (79% over a 90° bend) and skews the frame to 34°,
and neither degradation is reducible by segmentation, whereas the orthogonal frame's shear halves
with every doubling of `--segments`. Measured, both ways; see finding 5's table.

## 3. Decisions

### 3.1 Owner rulings (2026-07-26)

| # | Ruling | Rejected, and why |
|---|--------|---
| 1 | **Pan moves out of `poly set` into its own verb.** | Leaving it on `set` — the `--pan-to`/`--pan-by` compound spelling exists only because it shares a verb; alone it is `pan --to/--by`, matching every other transform in the CLI. |
| 2 | **Per-face mutators echo `BRUSH:idx` on stdout**, not touched brush names. | Keeping brush-name output — a bare name means *all* that brush's polys, so a second per-face verb in the pipe silently widens the set. Invisible today with one mutator; a trap with four. |
| 3 | **`--run` (and any bend-following mode) orders the chain itself.** | Trusting pipe order, as `--ring` does — `find`'s order is not author-controlled. Consequence: a bend mode needs no `--centre` flag, since the turn comes from adjacency. |
| 4 | **`--run` DERIVES the frame; it does not preserve the caller's rotation.** Fixups afterwards are quarter-turn flips and small texel pans. | Preserve-and-compose (`rotate --bend \| align --run`) — proposed by the agent, rejected by the owner. Vindicated by the spike: rotation alone leaves the phase broken (finding 2), and `--run` deriving solves the case outright (finding 3), so the composed form was solving a problem `--run` should not have had. |
| 5 | **The turn is a scalar angle in unreal rotation units, folded into `--run`.** | A boolean `--across` (agent proposal) — covers only quarter turns; the scalar generalises. Applying the turn as a separate post-pass — it pivots each face about its own centroid and re-breaks the seams `--run` just matched. |

### 3.2 Agent choices (→ `rationale/polyalign.md` on landing)

- **Orthogonal frame, centreline reference radius** — from the measured trade in finding 5, not
  taste. Also answers the owner's deferred arc-length question: per-strip arc length and the sheared
  frame are *the same construction*, so option (a) is rejected on that evidence; per-facet fit
  (option c) is disqualified because it reproduces the restart defect.
- **Adjacency walk from a seed** for ordering.
- **Exact component swap at quarter turns** rather than a float rotation.

## 4. What the implementation must pin

`rules/spikes.md` requires a checkable finding to ship with a regression. The spike could not pin its
central formula because the code did not exist; that obligation transfers here and is **not
optional**:

- **Seam continuity test.** Port `spikes/2026-07-26-poly-rotate-curved-track/seam_check.py`: for
  `align --run` on an N-segment revolve, max ΔU over every seam equals `2·sin(Δθ/2)·half_width`
  within tolerance and max ΔV is zero. Goldens: **12.546781** at 8 segments, **6.281331** at 16.
- **Turn axis-selection test.** `--rotate 0` leaves the across-axis exact and the along-axis sheared;
  `--rotate 16384` swaps them; a non-quarter turn (8192) is exact on neither. These are the
  measured 12.547 / 0.0005 pairs in finding 4.
- **Quarter-turn exactness.** After `--rotate 16384`, the axes contain no float dust — exact
  components, not `6.1e-17`.
- Already pinned, upstream of all of the above:
  `test_generators.py::test_revolve_facets_are_evenly_spaced_by_angle_over_segments`.

Docs to update in the same change: `docs/usage.md` (the verb reference and the
`brush poly set` / align sections), `docs/leveldesign/general/` for the curved-run recipe, and
`dev/docs/architecture.md`. **`--segments` must be documented as a texture-quality parameter**, with
the shear formula — no author would guess that a bend's facet count sets its worst-case texture
mismatch.

## 5. Open questions — MUST be closed before planning

1. **The turn flag's name.** The owner wrote `--rotate 16384`; the agent proposed `--turn`. `--rotate`
   already exists on the builders meaning the *actor's* orientation and taking a **triple**
   (`PITCH,YAW,ROLL`), against a **scalar** here. Nothing is ambiguous in context — a poly has no
   actor rotation — but the same flag name at a different arity in a neighbouring verb is a real
   papercut. **Not settled; the owner's spelling is recorded above as written.**
2. **The `--ring` → `--run` rename.** Agent recommendation, on the grounds that a 90° arc is not a
   ring and an author would not find `--ring` when looking for it; `run` is already the codebase's own
   word (`polyalign._check_orientation`: *"turning runs deferred"*). **The owner asked the question
   but did not rule.** If the rename is rejected, everything else in §2.3 still stands under the old
   name.
3. **`brush poly scale`** — the fourth canonical op, still missing, and deliberately NOT specced here.
   It interacts with `--run` (which sets texel density from the seed) and adding it blind would
   duplicate that. Filed rather than guessed.

## 6. Out of scope

- Fixing `level preview --native`'s inability to render a revolve (spike finding 6; filed to
  `board/inbox.md`). It makes this feature harder to *verify* but does not change its design.
- Non-quad faces in a run. The spike's prototype handles quads and errors otherwise; the real
  implementation should decide whether to generalise or keep the error.
- Runs spanning more than one brush.
