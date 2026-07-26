# Spike — aligning a repeating texture around a REVOLVED (curved) brush

**Date:** 2026-07-26 · **Status:** complete

## What this spike answers

The owner's measured revolve diagnosis (`board/inbox.md`, commit `725af04`) established that a
revolved brush's texture restarts at every facet, and left open what feature fixes it. That entry
measured the **outer curving wall** (`Side1`). This spike measures the **top face** — the surface a
train track sits on — and answers three questions with numbers rather than opinion:

1. Is a per-face **rotate** enough to make a texture follow a bend?
2. If not, what is? (Answer: a generalised `align --run`.)
3. Can a run be made **exactly** seam-continuous, and what does it cost?

Terms used below, defined once. A **facet** is one of the flat quadrilaterals a revolve is built
from — a 90° sweep at `--segments 8` has 8 of them across its top. A **seam** is the edge two
adjacent facets share. The **texture frame** of a face is the triple
`(Origin, TextureU, TextureV)` that maps a world point to a texture coordinate via the T3D
convention `U = (Vertex − Origin)·TextureU + PanU` (see `../../unrealed/t3d.md`); the texel scale
lives in the *magnitude* of `TextureU`/`TextureV`, so a unit-length axis means 1 texel per world unit.

## Fixture

Throwaway project at `_scratch/trackspike/` (gitignored). Rebuild it with `fixture.sh`.

A 90° curved track bed — `brush build revolve --axis x --point 512,0 --point 640,0 --point 640,16
--point 512,16 --angle 16384 --segments 8` — 128 uu wide, 16 uu thick, bend centre at the world
origin. Its 8 top faces carry `CoreTexMisc.Railwaytrack01`, a texture with strong directional
banding so that a facet whose texture does not follow the bend is obvious by eye.

---

## Finding 1 — the top facets all share ONE world-axis-aligned frame

Read out of the emitted T3D. All 8 top facets carry **identical** texture vectors:

```
TextureU +1,0,0        TextureV +0,1,0        (no Pan line on any facet)
```

Each facet's `Origin` is its own centroid, but the axes never rotate. So on the **top** face the
defect is not merely "the pattern restarts per facet" — the texture is mapped **dead straight across
the whole annulus**, ignoring the bend entirely.

This extends the owner's `Side1` measurement rather than contradicting it. The *curving wall* facets
each have a distinct normal, so a plane-derived basis necessarily rotates with them. The *flat
annular top* has one normal for all 8 facets, so a plane-derived basis has no reason to rotate
within the plane — and doesn't. The wall needs pan continuity; the top needs rotation as well.

## Finding 2 — a per-face ROTATE is necessary but NOT sufficient

`apply_bend.py` rotates each facet's frame by its own bearing around the bend (a clean −11.25° per
facet = 90°/8). Result, rendered: the rails **follow the curve** correctly. But the pattern
**restarts on every facet** — the same sleeper cluster appears 8 times with a jump at each seam,
because rotation sets each facet's texture *direction* and nothing advances its *phase*. Every facet
still renders the identical ~113 uu window of the texture (mean radius 576 × 11.25° = 113 uu of arc,
against a 256-texel texture at 1 texel/uu).

Evidence: `_scratch/trackspike-shots/BEFORE-top.png` → `AFTER-top.png`.

## Finding 3 — `align --run` is the right primitive, and it solves the case outright

`run_align.py` prototypes a generalised `align --run`: it auto-orders the facets into a connected
run by shared edges, derives U along the run direction and V across it, and accumulates the **chord
between consecutive seam midpoints** so the phase carries across seams. It **derives** the frame
rather than preserving what is there, which is the owner's 2026-07-26 ruling.

> **Chord, not arc length.** The advance is the straight-line distance between the entry and exit
> seam midpoints — 112.92 uu here (`2·576·sin(5.625°)`), against a true centreline arc of 113.10 uu.
> Chord is what makes the phase actually meet at the seam, because the anchor is a *point*, and it is
> what the shipped `--ring` already does (`usage.md`: "U advances by each facet's true chord
> `2·r·sin(π/N)`", pinned by `test_polyalign.py::test_engine_fact_cylinder_facet_chord_is_2r_sin_pi_over_n`).
> An earlier draft of this document said "arc length" throughout; that was wrong wording for the
> right construction, and using true arc length would inject ~0.18 texels of error at every seam.

Measured on the fixture: 8 facets ordered 18→25, 112.92 uu each, 903.33 uu total, run direction
sweeping a smooth 90°. Rendered (`RUN-top-close.png`): one unbroken rail around the whole bend with
sleepers perpendicular to travel — visually correct track.

**So per-face rotation was only ever a workaround for `--run` being cylinder-only.** Today's
`--ring` rejects a coplanar set outright (*"all faces are parallel — not a ring"*); a generalised
`--run` must accept it, because the flat annulus is exactly the case that needs it.

## Finding 4 — seam continuity has an EXACT closed form, and screenshots hide it

**The renders lie.** `RUN-top-close.png` looks continuous. `seam_check.py` — which computes the
(U,V) of each shared-edge endpoint from *both* adjoining faces and compares — shows it is not:

| `--turn` | max ΔU | max ΔV |
|-------------|---------|---
| 0 | **12.547** | 0.0005 |
| 8192 (45°) | 8.872 | 8.872 |
| 16384 (90°) | 0.0005 | **12.547** |
| 5000 | 11.154 | 5.797 |

The mismatch is **12.5 texels out of 256** (~5%), concentrated at the track edges where the strong
features are not — which is why it survives visual inspection. **The seam check is the test; the
render is not.**

### The closed form — and the geometry it is SCOPED TO

> **seam shear = density_u × 2·sin(Δθ/2) × half_width**, in texels, where Δθ is the per-facet turn
> and `half_width` is half the run's cross-run extent measured from the phase reference (the
> centreline). At the fixture's 1 texel/uu and 128 uu width that is `2·sin(Δθ/2)·64`.

**⚠ This applies ONLY to a run whose seams lie IN the plane of the turn** — a flat bend, like this
track bed's top. It is **not** a property of `--run` in general, and the distinction is not subtle:

**A cylinder-style run has ZERO shear.** Measured 2026-07-26 on a closed 8-sided cylinder through the
**shipped** `brush poly align --ring`:

```
seam 0|1 … 6|7    dU = 0.000000   dV = 0.000000     ← all 7 interior seams, EXACT on both axes
seam 0|7          dU = 1567.472357                  ← the closing seam --ring deliberately leaves
                                                      (= the full perimeter; --fit-perimeter closes it)
```

Why: on a cylinder the seam edge runs **parallel to the turn axis**, so each face's U axis is
perpendicular to the seam from both sides (`tu·e = 0`) and V is the axis itself — both match exactly.
On the flat annulus the seam is radial, lying *within* the plane the faces turn in, so each face's U
tilts by ±Δθ/2 relative to seam-perpendicular and the mismatch appears. Any generalised `--run` must
therefore preserve the cylinder case's exactness, and a regression must pin it.

**A second unstated assumption:** the "one axis is exact" result needs the seam to **bisect** the
turn, i.e. both adjacent facets turning by the same Δθ. The across-axis gradients are `cos(Δθ_A/2)`
and `cos(Δθ_B/2)`, equal only when the turns are equal. A uniform revolve satisfies this; a run of
unequally-turned facets does not.

Verified predictive within that scope, not merely fitted:

| segments | Δθ | closed form | measured (single pass, clean trunk) |
|----------|--------|-------------|---
| 8 | 11.25° | 12.546194 | 12.546615 |
| 16 | 5.625° | 6.281 | 6.281331 |

### ⚠ The measured digits are NOT stable — assert the closed form, with tolerance

Re-running the same alignment over an already-aligned trunk changes the low-order digits, because
`emit.clean`'s `CLEAN_EPS = 0.001` snapping acts on a revolve's off-grid vertices every round trip:

| trunk state | max ΔU |
|-------------------------------|---
| closed form | 12.546194 |
| one pass from a clean baseline | 12.546615 |
| two passes | 12.546781 |
| after many passes (incl. a sheared frame in between) | 12.6278 |

So a regression must assert **`|max ΔU − density_u·2·sin(Δθ/2)·half_width| < 2e-3`** and
**`max ΔV < 2e-3`** — never a six-decimal golden, which pins fixture history rather than the result.
(The measured ΔV "zero" is 0.0005, the same order as this noise.)

**Why.** Along the shared edge, the *across*-run axis has gradient ∝ `cos(Δθ/2)` — cosine is even, so
both faces agree exactly. The *along*-run axis has gradient ∝ `±sin(Δθ/2)` — sine is odd, so the two
faces disagree by twice that. The offsets match at the seam midpoint (where the phase is anchored)
and the error grows linearly outward, peaking at the track edges.

### Consequence for `--turn`

Exactly **one** axis can be continuous, and only at **quarter turns**; the turn selects which one.
`--turn 0` gives an exact across-axis, `--turn 16384` an exact along-axis, and any intermediate angle
(8192, 5000) is continuous on **neither** — the error merely redistributes. A non-quarter `--turn`
silently costs the only continuity guarantee the verb can make.

## Finding 5 — an EXACT frame exists, and its cost is unbounded

T3D stores `TextureU`/`TextureV` as independent FVectors with **no orthogonality requirement**, so a
deliberately sheared frame is representable. `shear_align.py` constructs one.

The ideal "every radial strip advances by its own arc length" mapping is `U = du·r·ψ` (polar
coordinates about the bend centre), which is **not** affine and so cannot be reproduced over a whole
facet by any texture frame. But a frame only has to agree with its *neighbour*, and neighbours meet
on a seam — a radial edge at fixed ψ, where `r·ψ` is linear in `r`. Matching the ideal on both of a
facet's seams gives three conditions (a gradient along each seam's radial direction, plus the value
at the bend centre) on three degrees of freedom, and they are consistent **because both seams
independently want `U = 0` at `r = 0`**. Setting `Origin` = the bend centre satisfies the last
condition for both axes at once.

**It works exactly:** max ΔU = 0.000647, max ΔV = 0.000340 — float precision on *both* axes, against
12.547 for the orthogonal frame.

**And it is still the wrong choice**, because of how it degrades along the run:

| facet | ψ along bend | \|TextureU\| | angle between U and V |
|-------|--------------|--------------|---
| 18 | 0–11° | 1.006 | 84.4° |
| 21 | 34–45° | 1.217 | 55.4° |
| 25 | 79–90° | **1.787** | **34.1°** |

The stretch follows `√(1+ψ²)` — **86% at the end of a 90° bend** (`√(1+(π/2)²) = 1.862`); the 1.787
in the table is the last facet's *centre*, at ψ ≈ 84.4°, not the endpoint — and the frame skews to
34°. Rendered
(`SHEAR-top.png`), the rails are genuinely seamless and the **sleepers lean over progressively**
instead of staying perpendicular.

**The decisive asymmetry** is what each error responds to:

| | seam continuity | texture distortion | reducible by `--segments`? |
|--------------------------|------------------|--------------------|---
| orthogonal (per-facet) | `2·sin(Δθ/2)·half_width` | none; texels stay square | **yes** — halves per doubling |
| sheared (per-strip) | **exact** | `√(1+ψ²)` stretch + skew | **no** — depends only on ψ |

The sheared frame's distortion depends only on how far around the bend a facet sits, not on how
finely the bend is cut, so adding segments does not help it at all — and it *grows* with total bend
angle, so a 180° curve is worse than this 90° one. The orthogonal frame's error shrinks toward zero
with a dial the author already has.

**Recommendation: the orthogonal frame, with phase measured on one reference radius (the
centreline).** This also answers the owner's deferred arc-length question directly: *per-strip arc
length and the sheared frame are the same thing*, so option (a) is rejected on the evidence above,
and option (c) (per-facet fit) is disqualified because it reproduces Finding 2's restart.

**And `--segments` is therefore a TEXTURE-quality parameter, not only a geometry one** — a fact no
author would guess, and which now has a formula.

## Finding 6 — ⛔ `level preview --native` cannot render a revolve at all

Measured 2026-07-26. A revolve brush does not appear in a `--native` render — not mis-drawn, absent.

| Brush | On grid? | Convex? | Renders in `--native`? |
|-----------------------------------|----------|---------|---
| `brush build cube` | yes | yes | ✅ yes |
| `brush build cylinder --sides 8` | **no** | yes | ✅ yes |
| `brush build revolve --segments 8` | no | no | ❌ **absent** |
| `brush build revolve --segments 1` | no | **yes** | ❌ **absent** |

The cylinder rules out off-grid vertices; the 1-segment revolve — a convex 6-plane hexahedron — rules
out non-convexity. So this is **not** the documented "native assumes convex solids" caveat that
`docs/usage.md` attaches to `staircase`/`extrude`: that caveat predicts a *mis-drawn* brush (a notch
filled in), and what happens here is total absence, for a convex brush. Re-measured on a clean level
containing only a subtracted room and one 128-uu-tall arc, to rule out framing and thin-slab effects.
`--game` renders the same brush correctly, so the geometry is sound.

**Cause not identified** — winding/normal orientation on the swept faces is the leading suspect (an
inside-out add brush contributes nothing to CSG), but it was not tested. Filed to the board.

Consequence: the only backend that renders this subject is `level preview --game`, which needs the
level to carry a `PlayerStart` and at least one `Light` (an unlit level renders solid black), costs
~1 min per iteration once the trunk changes, and **wedged silently three times** on one particular
pose (two timeouts, one empty log, container restarting in between) — the failure mode
`../rules/background-work.md` describes.

## Harness

| File | What it does |
|------------------|---
| `fixture.sh` | rebuilds the throwaway project from scratch |
| `poly_rotate.py` | per-face texture rotation, re-anchored so the face centroid keeps its (U,V) |
| `apply_bend.py` | Finding 2 — rotates each facet by its own bearing around the bend |
| `run_align.py` | Finding 3/4 — the `align --run` prototype, orthogonal frame, optional `--turn` in UU |
| `shear_align.py` | Finding 5 — the sheared frame that is exactly seam-continuous |
| `seam_check.py` | measures (U,V) agreement across every shared edge; the real test |

## What must be pinned when `align --run` is built

`../rules/spikes.md` requires a checkable finding to land with a committed regression, or it rots.
The shear formula cannot be pinned today because the code it describes does not exist yet — the
prototypes here are throwaway. So the obligation transfers to the implementation, and the spec must
carry it:

- **`seam_check.py`'s assertion becomes the test**, against the CLOSED FORM and a `2e-3` tolerance —
  never the six-decimal measurements, which drift with trunk history (see the stability table above).
  State the fixture with it, since `half_width` and `density_u` come from the fixture, not the verb.
- **A cylinder-run regression is mandatory**, and is the more important of the two: `--run` over a
  cylinder's sides must reproduce today's `--ring` exactness (interior seams ΔU = ΔV = 0), or the
  generalisation has silently broken the only case that shipped.
- What IS pinnable today, and is pinned by
  `test_generators.py::test_revolve_facets_are_evenly_spaced_by_angle_over_segments`, is the fact the
  formula rests on: a `--segments N` revolve of a `--angle A` sweep produces facets whose turn is
  exactly `A/N`. If the builder's segmentation ever changed, every shear number in this document
  would silently go stale. (It lives with the generator tests, not in `test_engine_facts.py`, because
  it is a fact about *uedcli's builder* — that module is reserved for facts about the real UnrealEd
  binary and editor-produced goldens.)
