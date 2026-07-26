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
run by shared edges, derives U along the run direction and V across it, and accumulates arc length
so the phase carries across seams. It **derives** the frame rather than preserving what is there,
which is the owner's 2026-07-26 ruling.

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

### The closed form

> **seam shear = 2·sin(Δθ/2) × half-width**, in texels at 1 texel/uu, where Δθ is the per-facet turn.

Verified predictive, not merely fitted:

| segments | Δθ | predicted | measured |
|----------|--------|-----------|---
| 8 | 11.25° | 12.546 | 12.546781 |
| 16 | 5.625° | 6.281 | 6.281331 |

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

The stretch follows `√(1+ψ²)` — 79% by the end of a 90° bend — and the frame skews to 34°. Rendered
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

- **`seam_check.py`'s assertion becomes the test**: for `align --run` on an N-segment revolve, max
  ΔU across every seam must equal `2·sin(Δθ/2)·half_width` within tolerance, and max ΔV must be zero.
  Both numbers above (12.546781 at 8 segments, 6.281331 at 16) are the goldens.
- What IS pinnable today, and is pinned by
  `test_generators.py::test_revolve_facets_are_evenly_spaced_by_angle_over_segments`, is the fact the
  formula rests on: a `--segments N` revolve of a `--angle A` sweep produces facets whose turn is
  exactly `A/N`. If the builder's segmentation ever changed, every shear number in this document
  would silently go stale. (It lives with the generator tests, not in `test_engine_facts.py`, because
  it is a fact about *uedcli's builder* — that module is reserved for facts about the real UnrealEd
  binary and editor-produced goldens.)
