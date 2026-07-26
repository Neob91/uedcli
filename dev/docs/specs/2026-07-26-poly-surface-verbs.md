# Spec — per-surface texture verbs: `pan`, `rotate`, and `align --run`

**Date:** 2026-07-26 · **Status:** revised after spec review round 1 · **Evidence:**
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
| `brush poly align --wall \| --floor [--fresh-frame]` | unchanged | coplanar faces, one shared frame, orientation-guarded |
| `brush poly align --ring [--fresh-frame] [--fit-perimeter]` | `brush poly align --run [--turn UU] [--fresh-frame] [--fit-perimeter]` | generalised from "cylinder sides" to "any connected run", coplanar sets allowed |

Per `CLAUDE.md` "No back-compat cruft": `--pan-to`/`--pan-by` on `set` and the `--ring` spelling are
**deleted outright** in the same change that adds their replacements. No aliases, no shims.

### 2.1 `brush poly pan (--to | --by) U,V`

Straight promotion of the existing flags. Targets are `BRUSH:SELECTOR` positionals or `-`; `-` is the
sole source; empty stdin is a clean no-op (exit 0). Exactly one of `--to`/`--by` is **required**
(today `apply_surface_edit` raises "at least one of … is required"; keep that). Values are **integer
texels**, written to the polygon `Pan` field. A duplicate/overlapping target set is **deduped before
applying**, because `--by` is relative and would otherwise double-apply (`surface.apply_surface_edit`
already does this deliberately — carry it forward).

`--to 0,0` clears the pan, which emits **no `Pan` line** (`t3d.md`: an absent `Pan` ≡ zero; see the
2026-07-26 `emit` fix).

**It never touches `Origin`.** The precise safety claim — an earlier draft overstated this:

- `--run` writes its continuity offset into the float `Origin`, so **a uniform `pan` applied to the
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
the target set is **deduped** (relative operation, same reason as `pan`). `--by` is the only form:
there is deliberately **no `--to`**, because a face's texture frame has no canonical zero to be
absolute against — state that in the help so nobody adds one.

- `--by` is in **unreal rotation units** (16384 = 90°), matching `brush build --rotate`,
  `mover key rotate` and the `level preview` pose grammar. Positive = the texture image turns
  counter-clockwise viewed from outside the face (i.e. the axes turn clockwise). **This sign must be
  pinned by a test** — it is exactly the kind of claim that silently flips.
- The rotation is `U' = n̂ × U`, `V' = n̂ × V` for a quarter turn — arithmetic, no trig.
- **Quarter turns are exact ON AN AXIS-ALIGNED FACE with an orthogonal frame.** Scoped deliberately:
  on a slanted face `n̂` is already an inexact float triple, so "no float dust" is unachievable there
  no matter how the rotation is coded; and a naive swap of the two stored vectors is *wrong* whenever
  `|U| ≠ |V|`, because T3D carries the texel scale in the magnitudes. Detect `uu % 16384 == 0` and
  take the exact path; assert exactness only for the axis-aligned orthogonal case, which is the one
  that pollutes trunk diffs.
- **No continuity guarantee.** Applied across a run, each face pivots about its own centroid, which
  breaks the seams `--run` matched — and equally breaks a `--wall`/`--floor` shared frame. This is
  the verb for a one-off face (a sign, a panel, a soffit). Document it, and note the contrast with
  `--run --turn`, which is the run-aware operation.

### 2.3 `brush poly align --run [--turn UU] [--fresh-frame] [--fit-perimeter]`

The generalisation of `--ring`. Walks a connected run of faces and lays one continuous texture along
it: U follows the run, V across it, phase accumulating along the run.

**Phase accumulates by the CHORD between consecutive seam midpoints** — the straight-line distance,
not the true arc. This is what the shipped `--ring` already does (`usage.md`: "U advances by each
facet's true chord `2·r·sin(π/N)`", pinned by
`test_polyalign.py::test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n`), and it is what makes
the phase actually meet at the seam, since the anchor is a point. Arc length would inject ~0.18
texels of error per seam on the spike's fixture, and is not even computable without a bend centre,
which ruling 3 says the verb will not have.

**Ordering is derived; the ROOT is the first input token.** `--ring` today requires the caller's whole
input order to be the chain order and errors otherwise; `poly find` emits poly-index order, which the
author neither controls nor sees. `--run` builds an adjacency map from shared edges and walks the
chain — but it starts from the **first token in the input set**, which fixes:

- the phase zero (where `U = PanU`),
- the seam, on a closed run,
- the walk direction (from the root toward its neighbour of lower poly index, stated so it is
  reproducible),
- which face's frame is adopted for density and `Pan`.

This keeps ruling 3 intact — the *chain order* is still derived, only the *anchor* comes from input,
which preserves today's documented "the first face is the seam/seed" guarantee.

**Closed runs are supported.** A closed loop is detected trivially (no degree-1 face) and its seam is
the root's outer edge. This is not optional: the wrap-a-cylinder workflow
(`poly find Tower --item Side | poly align --ring -`) is the only `--ring` use that ships, is
documented in `usage.md` and `architecture.md`, and is covered by twelve `test_ring_*` tests.

**`--fit-perimeter` requires a CLOSED run** and exits 2 naming the run when given an open one. (It
snaps the density so an integer texel count fits the loop; on an open run that is a wrong answer that
looks right.) Under `--turn`, it fits the **along-run** axis regardless of which stored axis that
currently is — at `--turn 16384` the along-run advance sits in V, and fitting the axis merely *called*
U would be silently wrong.

**Coplanar sets are valid.** Today's `--ring` rejects them (*"all faces are parallel — not a ring"*);
that rejection is deleted. Note this does **not** collapse `--run` into `--wall`/`--floor`: on the same
coplanar set, `--floor` yields one shared frame (texture straight across) and `--run` a turning frame
(texture follows the curve). Both are wanted; they are different operations on the same input.

**`--fresh-frame` is KEPT and means the same thing it does today**: synthesize a canonical frame
(density 1/1, `Pan` (0,0)) instead of adopting the seed's. It does not conflict with ruling 4 —
"derives" governs the *orientation and phase*, which come from run geometry either way; `--fresh-frame`
governs only the *density and pan source*. Stated explicitly because the goldens differ between the
two branches.

**Density is derived by PROJECTION**, as `_ring_align` does today (`polyalign.py:324-328`): resolve
which stored axis is along-run vs across-run by projecting the seed's axes onto the run tangent and
the across direction. Do not simply take `|TextureU|`/`|TextureV|` — that silently mis-assigns density
on a builder frame whose U runs along the axis. (The spike prototype took the naive path; that is a
prototype shortcut, not the specified behaviour.)

**`--turn UU`** applies a uniform turn in each face's own **run frame**, not in world space, so every
face receives the same transform relative to the run. The arc advance is accumulated as a displacement
vector in the face plane and expressed in the rotated basis, so it distributes across both axes.

**Non-quarter `--turn` is ALLOWED, and must not be silent.** At a quarter turn exactly one axis is
continuous; at any other angle **neither** is — the mismatch vector merely rotates
(`ΔU = S·|cos θ|`, `ΔV = S·|sin θ|`, verified: 8.87/8.87 at 8192). Per `direction/conventions.md`
"No silent half-answers" this cannot be left to be discovered, but it is also not an error — the
author may legitimately want the angle. **Ruling: allow it, document the redistribution in
`usage.md`, and have `--run` print the computed worst-case seam shear to stderr** (a human summary
belongs on stderr; it is the only way an author ever learns the number).

**Guards carried over from `--ring`**, which must not be lost in the generalisation: single-brush
(a multi-brush set exits 2 naming the brushes — see §6), `< 2 faces`, and the **cap-face rejection**
with its actionable message (`"exclude caps, e.g. brush poly find <brush> --item Side | …"`). Under a
bare adjacency walk a cylinder cap becomes a degree-N node and falls out as the generic "the set
forks" error, which is a strictly worse message for the most common mistake — keep the specific one.

### 2.4 Frame construction, and what it costs

Orthogonal axes, phase measured on **one reference radius (the centreline)**.

**Where the seams are exact, and where they are not** (spike findings 4–5, and the round-1
correction):

- **A run whose seams are parallel to the turn axis — cylinder sides — is EXACTLY continuous on both
  axes.** Measured on the shipped `--ring`: all 7 interior seams of a closed 8-sided cylinder give
  ΔU = ΔV = 0.000000. `--run` must preserve this.
- **A run whose seams lie IN the plane of the turn — a flat bend, like the track bed's top — shears
  one axis** by `density_u · 2·sin(Δθ/2) · half_width` texels, where `half_width` is half the run's
  cross-run extent measured from the centreline. The other axis is exact, and only at quarter turns.
  This also assumes a **uniform** per-facet turn (the seam must bisect it); unequal turns break the
  even-cosine cancellation that makes the exact axis exact.

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
| 3 | **`--run` orders the chain itself** (the root still comes from the first input token — §2.3). | Trusting pipe order for the whole chain, as `--ring` does — `find`'s order is not author-controlled. Consequence: no `--centre` flag is needed. |
| 4 | **`--run` DERIVES the frame; it does not preserve the caller's rotation.** Fixups afterwards are quarter-turn flips and small texel pans. | Preserve-and-compose (`rotate --bend \| align --run`) — proposed by the agent, rejected by the owner, and vindicated by the spike: rotation alone leaves the phase broken (finding 2) and `--run` deriving solves the case outright (finding 3). |
| 5 | **The turn is a scalar angle in unreal rotation units, folded into `--run`, spelled `--turn`.** | `--rotate` — collides with `brush build --rotate` (actor orientation, a triple) and, worse, with `brush poly rotate` in the same noun, where the same word would carry the opposite continuity guarantee. A boolean `--across` — covers only quarter turns. A separate post-pass — pivots each face about its own centroid and re-breaks the seams. |
| 6 | **`--ring` is renamed `--run`.** | Keeping `--ring` — a 90° arc is not a ring, and an author would not find the flag; `run` is already the codebase's own word (`polyalign._check_orientation`: *"turning runs deferred"*). |

Rulings 5 and 6 were confirmed 2026-07-26 after the review round raised both as open.

### 3.2 Agent choices (→ `rationale/polyalign.md` on landing)

- **Orthogonal frame, centreline reference radius** — from the measured trade in §2.4, not taste.
  Also answers the owner's deferred arc-length question: per-strip arc length and the sheared frame
  are *the same construction*, so option (a) is rejected on that evidence; per-facet fit (option c) is
  disqualified because it reproduces the restart defect.
- **Chord, not arc**, for the phase advance.
- **Adjacency walk rooted at the first input token.**
- **Exact component path at quarter turns**, scoped to axis-aligned orthogonal frames.
- **Non-quarter `--turn` allowed + stderr shear report**, rather than an error.

## 4. What the implementation must pin

`rules/spikes.md` requires a checkable finding to ship with a regression, and `CLAUDE.md` requires
every named-error path to carry one. Non-negotiable:

**Continuity**
- **Cylinder run reproduces `--ring` exactness** — `--run` over a cylinder's sides gives interior-seam
  ΔU = ΔV = 0. *The most important test in the change*: it is the only capability that ships today.
- **Flat-bend shear matches the closed form** — assert
  `|max ΔU − density_u·2·sin(Δθ/2)·half_width| < 2e-3` and `max ΔV < 2e-3`, stating the fixture.
  **Do NOT pin six-decimal goldens**: the same alignment re-run over an already-aligned trunk moves
  them (12.546615 → 12.546781 → 12.6278) because `emit.clean`'s `CLEAN_EPS` snapping accumulates on
  off-grid vertices. Port `spikes/…/seam_check.py` as the measurement.
- **Turn axis selection** — `--turn 0` exact on the across-axis, `--turn 16384` on the along-axis,
  `--turn 8192` on neither (both components `S/√2`).

**Behaviour**
- **Ordering invariance** — a shuffled input set produces an identical result (ruling 3's central
  claim, and the easiest thing to regress).
- **Coplanar sets are accepted** by `--run` (the deleted "all faces are parallel" rejection).
- **`--fit-perimeter`** closes a closed run exactly, and exits 2 on an open one.
- **Quarter-turn exactness** of `brush poly rotate --by 16384` on an axis-aligned face — exact signed
  components, no float dust — and of `align --run --turn 16384` producing axes bit-identical to the
  swapped/negated `--turn 0` axes.
- **`brush poly rotate`'s sign convention.**
- **`brush poly pan --to`/`--by`**, including `--to 0,0` emitting no `Pan` line, and dedup of an
  overlapping target set (no double-apply).
- **stdout format** — every per-face mutator emits `BRUSH:idx` lines that `-` re-consumes.

**Error paths**, each a named exit 2: fork, disconnected member, edge shared by >2 faces, `< 2 faces`,
cap faces included, multi-brush set, `--to` with `--by`, `--fit-perimeter` on an open run.

**Docs to update in the same change:** `docs/usage.md` (verb reference, the `poly set` and align
sections, and the **"Output streams for mutators"** paragraph that currently lists `poly set`/`align`
as printing brush names); `docs/leveldesign/general/textures-and-surfaces.md` (lines 16 and 55
document the deleted `--pan-to`/`--pan-by`); a curved-run recipe under `docs/leveldesign/general/`;
and `dev/docs/architecture.md`. **`--segments` must be documented as a texture-quality parameter**,
with the shear formula **scoped to flat bends** and the caveat that doubling segments halves each
seam's shear but doubles the number of seams.

## 5. Sequencing

`board/to-plan.md` carries `specs/2026-07-24-facing-selector-grammar.md`, **both gates passed**, which
drops `--facing +Z` for a predicate grammar and makes `brush poly find` accept a brush **set**. This
spec's motivating workflow drives everything through `--facing +Z`, and §6 puts multi-brush runs out
of scope precisely as `find` starts emitting multi-brush sets routinely.

**That spec lands first.** This one is written against its grammar, and `--run` exits 2 naming the
brushes on a multi-brush set rather than silently aligning the first.

## 6. Out of scope

- **Non-quad faces in a run — DECIDED, not deferred: exit 2 naming the face.** The quad assumption is
  load-bearing (a terminal face's free edge is found as the opposite edge of the quad); generalising
  needs a different rule for "the far edge" and no shipped builder produces a non-quad swept face.
  Filed to `board/inbox.md` as its own item rather than guessed at here.
- **Runs spanning more than one brush** — exit 2 naming the brushes.
- **`brush poly scale`**, the fourth canonical op. It interacts with `--run`'s density derivation and
  adding it blind would duplicate that. Filed to `board/inbox.md`.
- Fixing `level preview --native`'s inability to render a revolve (spike finding 6; filed). It makes
  this feature harder to *verify* but does not change its design.

## 7. Owner confirmation still required

Per `CLAUDE.md` "Direction docs", the durable landing of §3.1 in `direction/conventions.md` needs the
owner's explicit yes and a `Confirmed: conventions` trailer. Until then the proposed text is parked
verbatim as an `[OWNER — confirm]` item on `board/inbox.md`, so it survives this session.

**Outstanding:** ruling 3's refinement — that the chain order is derived but the **root** comes from
the first input token (§2.3). Round 1 raised, independently and unanimously, that ruling 3 as
originally stated left the seed with no source at all. The refinement is the reviewers' consensus fix
and is recorded here as the working assumption; it amends the owner's ruling and therefore needs their
yes.
