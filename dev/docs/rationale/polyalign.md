# `polyalign.py` — `brush poly align`

Why the alignment code is the way it is. Sibling of [`surface.md`](surface.md). Revised in place —
agents maintain this freely. Owner product decisions live in `../direction/conventions.md` (once
confirmed) and are parked meanwhile on `dev/docs/board/inbox/`; this file holds the engineering.

`align` has three modes. `wall`/`floor` reproduce the editor's `POLY TEXALIGN` projection family
(`FLOOR`/`WALLX`/`WALLY`), measured in [`../unrealed/texalign.md`](../unrealed/texalign.md); that
doc is the authority for their math. `run` (a continuous texture along a connected strip of faces)
has no editor analogue and is uedcli's own — this file is about its algorithm.

---

## `wall`/`floor`: a per-face world-projected stamp, no set relationship

Each face's frame is a pure function of its own plane and the world axes: the texture anchored where
the plane crosses the projection axis, U/V the other two world axes projected in and negated, `Pan`
zeroed. So a set is simply a batch — aligning face A alone and face B alone gives byte-identical
frames, and re-running changes nothing.

**Why it is this way.** The projection family is what makes a texture flow across a whole wall or
floor on one world grid regardless of brush boundaries, which is the point of the verb.

**Rejected.** A seed-anchored frame (the pre-2026-07-26 code, anchored on the first face's centroid):
its result depended on which face came first, so two invocations over subsets of one plane
disagreed. **Rejected.** The coplanarity and co-orientation guards: a world-derived frame removes
their motivation — faces on different planes legitimately share one grid, and two opposite-facing
coplanar faces get an identical frame (the texture reads mirrored on the back, which is the family's
defined polarity-blind behaviour, not a fault). The `|N·A| > 0.05` guard stays, because `d/N·A`
diverges as the face turns edge-on to the projection axis.

---

## `run`: the pre-walk

`run` derives everything — the chain, its root, and the walk direction — from the geometry and the
poly index, so the order faces are passed in has no bearing on the result. The steps run in a fixed
order and the order is load-bearing.

**Branching — one error, no cap predicate.** A face with ≥ 3 neighbours in the set exits 2; the
message always carries the `--item Side` hint. There is deliberately no cap-vs-branch classification.

**Rejected — three cap predicates, each wrong.** (1) A normal-vs-neighbour-tangent test: a cylinder
cap's normal is the axis while the side tangents are tangential, so `n̂·t̂ = 0` passed the cap and
rejected every real side face. (2) Keying on the shared edge being parallel to the neighbour's run
tangent: the run tangent only exists *after* the walk this check gates. (3) Pure adjacency
(`degree == |set|−1`, or ≥ 3 non-opposite edges): a genuine T-junction is announced as a cap, a
tetrahedron reports all four faces as caps, and a square prism selected with *both* caps detects
neither — and `align run <Box>` is exactly that set. Adjacency answers the only question that
matters — *does the phase fork here* — and one honest message with the hint beats two, one of which
sometimes lies.

**Connectivity.** After the branch check every member has degree ≤ 2, so a connected graph is a
simple path or cycle; the only remaining failure is disconnection, caught by one component count.
Two disjoint chains (four ends, no branch) and a lone face (degree 0) are both silent otherwise.

**Non-quad rejection comes after the branch check.** A cylinder cap is an N-gon, so a non-quad check
placed earlier would report the flagship cap as "not a quad" and the author would never see the
`--item Side` hint. The quad assumption is load-bearing: a terminal face's missing seam is found as
the opposite edge of the quad, which has no definition on a general polygon.

**Root and walk direction.** An open run roots at its lower-poly-index end (direction then forced); a
closed run roots at its lowest index and leaves through the seam it shares with the lower-indexed of
its two neighbours, so its entry seam — where phase zero sits — is the seam with the higher-indexed
neighbour, which is also the open seam. On the shipped 8-sided cylinder this makes U increase with
poly index and keeps the open seam at `sides[-1] | sides[0]`, where `--ring` put it. The opposite
choice reverses U on every existing wrap; nothing in the shipped suite caught that, so it has its own
pin.

## `run`: the frame

Orthogonal axes; phase measured on the centreline (the seam midpoints). Per face the run tangent is
`unit(exit_mid − entry_mid)`, the chord advance is `|exit_mid − entry_mid|`, and `--turn` rotates the
(tangent, across) frame rigidly, so the along-run advance distributes across both stored axes and the
seams match *with* the turn rather than being broken by it. Density resets to 1 texel/uu.

**The across-run axis sign is fixed once at the root and propagated, never re-derived per face.** The
root picks `ĉ` as the negative side of its own largest-magnitude world component (ties to the lowest
axis index); every later face takes the perpendicular continuous with its predecessor. This gives V
running *down*, independence from the walk direction, and invariance under `n̂ → −n̂` (the subtractive
case).

**Rejected — a per-face world sign rule** (rank the world axes `Ẑ`-then-`Ŷ`-then-`X̂`, take the first
non-negligible component): it needs a tie epsilon and, worse, is discontinuous *at* the flat bed this
mode exists for — a dead-flat bed and one with a hair of grade come out with V mirrored. Fixing the
sign at the root sits the only discontinuity 45° from every world axis, far from both shipped cases,
and evaluating it once means a run that sweeps through 45° mid-way never re-evaluates it.

**The two phase anchors.** The along-run phase anchors at the seam midpoint (the lever arm the shear
formula needs); the across-run zero is an *endpoint* — the root entry edge's lower-`ĉ` endpoint —
propagated by V-continuity, so `V = 0` lands on one rim rather than mid-height. They differ only on a
run whose cross section changes along it, where the propagated rule is the one that keeps V
continuous.

**What it costs (frame construction).** A run whose seams are parallel to the turn axis — cylinder
sides — is exactly continuous on both axes at every turn. A run whose seams lie in the turn plane —
a flat bend — shears one axis by `2·sin(Δθ/2)·half_width`, exact on the other only at quarter turns.
`run` reports the worst internal seam's shear to stderr (measured from the written frames), so a flat
corner tells the author to mitre it or accept a visible seam. The rejected alternative — a sheared
non-orthogonal frame, continuous on both axes — stretches 86% at the end of a 90° bend and neither
degradation reduces with more segments, where the orthogonal frame's shear halves each time.

**Refs.** `../unrealed/texalign.md`; `../board/inbox/the-per-surface-verb-split/spec.md` (§2.3, §2.4,
§2.7); `uedcli/polyalign.py`.
