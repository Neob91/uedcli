# `polyalign.py` — `brush poly align`

Why the alignment code is the way it is. Sibling of [`surface.md`](surface.md). Revised in place —
agents maintain this freely. Owner product decisions live in `../direction/conventions.md` (once
confirmed) and are parked meanwhile on `dev/docs/board/inbox/`; this file holds the engineering.

`align` has five modes. `floor` reproduces the editor's `POLY TEXALIGN` `FLOOR` projection, measured
in [`../unrealed/texalign.md`](../unrealed/texalign.md); that doc is the authority for its math.
`wall` used to reproduce `WALLX`/`WALLY` the same way — it now reproduces `WALLDIR` instead (board
item `align-wall-walldir-style-axes-split-off-a-wall`), and `wall-pan` is new, reproducing `WALLPAN`.
`run` (a continuous texture along a connected strip of faces) and `one-tile` have no editor analogue
and are uedcli's own — this file is about their algorithms.

---

## `floor`: a per-face world-projected stamp, no set relationship

Each face's frame is a pure function of its own plane and the world axes: the texture anchored where
the plane crosses the Z axis, U/V the other two world axes projected in and negated, `Pan` zeroed.
So a set is simply a batch — aligning face A alone and face B alone gives byte-identical frames, and
re-running changes nothing.

**Why it is this way.** The projection family is what makes a texture flow across a whole floor on
one world grid regardless of brush boundaries, which is the point of the verb.

**Rejected.** A seed-anchored frame (the pre-2026-07-26 code, anchored on the first face's centroid):
its result depended on which face came first, so two invocations over subsets of one plane
disagreed. **Rejected.** The coplanarity and co-orientation guards: a world-derived frame removes
their motivation — faces on different planes legitimately share one grid, and two opposite-facing
coplanar faces get an identical frame (the texture reads mirrored on the back, which is the family's
defined polarity-blind behaviour, not a fault). The `|N·Z| > 0.05` guard stays, because `d/N·Z`
diverges as the face turns edge-on to Z. (`wall` shared this same world-axis-projection code and
these same rulings until it was redefined onto `WALLDIR` — see below; they still apply to `floor`
unchanged, and to `wall`'s history.)

---

## `wall`: `WALLDIR`, the visible normal, and why it needed its own normal helper

Redefined from `WALLX`/`WALLY` (the same world-axis family as `floor`, above) onto UnrealEd's
`WALLDIR`: a unit frame from the face's own horizontal run and downward slope, anchored on the
face's own centroid, never stretching. Full derivation, the formulas, and the review history that
found three real correctness bugs in three successive drafts of the design are in the spec —
`../board/to-build/align-wall-walldir-style-axes-split-off-a-wall/spec.md` (revision 4) — not
repeated here; this section is the short version plus what a future maintainer needs to not
reintroduce those bugs.

**`WALLDIR` is sign-sensitive; `WALLX`/`WALLY`/`FLOOR` are not.** Flipping the face normal flips
`WALLDIR`'s `TextureU` but not `TextureV` (the `TextureV.Z > 0` flip cancels the same way both
times) — verified algebraically. So unlike `floor`, `wall` cannot use just any normal with the right
axis and a don't-care sign; it needs the one the author actually sees, matching why `rotate` needed
it (`../rationale/surface.md` "`rotate` turns against the visible surface normal").

**`_oriented_world_normal` exists because NEITHER existing normal helper is right here, and is
deliberately NOT built by sharing code with either.** `polyalign._world_normal` (Newell recomputed
on world vertices) is what `floor` uses and is WRONG for `wall`: it flips sign under a mirrored
(negative-determinant) brush, because `Newell(L·v) = det(L)·(L⁻¹)ᵀ·Newell(v)` — invisible to `floor`
only because that whole family cancels any sign error, from any source. `query.visible_normal` gets
the geometry right (the covariant transform `(L⁻¹)ᵀ` on the LOCAL normal) but the wrong HANDLING for
`wall`'s needs: it silently returns `(0,0,0)` for a degenerate transform or zero-area face (fine for
its own callers, a division-by-zero crash waiting to happen here), and it composes with
`csg_is_subtract`, which silently treats `CSG_Intersect`/`CSG_Deintersect` as "not subtract" (a
silent half-answer `wall` cannot inherit). `_oriented_world_normal` reuses `query.visible_normal`'s
covariant-transform MATH (independently known correct) without its zero-defaulting HANDLING — it
raises, naming the face or brush, instead.

**`query.csg_sign` is exact-case and does NOT call `query._csg_oper`/`csg_is_subtract`, on purpose.**
Those match `CsgOper` case-insensitively (with their own regression pinning it); `surface.
_visible_normal` (the `rotate` precedent) matches exact-case. Building `csg_sign` on top of the
case-insensitive lookup would have silently WIDENED `rotate`'s refusal behaviour the moment
`surface._visible_normal` was refactored to call it — caught in spec review before it shipped, not
after.

**The mirrored-brush question `rotate` leaves open does not apply here, by construction.**
`rotate`'s visible-normal is LOCAL (never reads `MainScale`/`PostScale`), so it cannot see a mirrored
brush's reversed rendered winding — a documented, unmeasured gap (`../rationale/surface.md`).
`_oriented_world_normal` computes Newell on the ACTUAL WORLD vertex positions (full transform
applied, mirroring included), so the winding it sees already IS the one the engine renders; there is
no separate correction to be missing. Still reasoned, not measured against a corpus fixture (none
carries a mirrored brush) — a `rules/spikes.md` job if it ever needs confirming live.

**Anchor: the face's own centroid, at `(U,V)=(0,0)`, needing no precedent.** `wall` is a
from-scratch derive — there is no existing frame the way `wall-pan` assumes one — so there is
nothing for an anchor choice to preserve; centroid-at-origin is simply the plainest anchor
available. (An earlier spec draft cited `rotate`/`scale`'s centroid re-anchor as precedent for this
and review caught it as false: those two preserve the centroid's PRE-EXISTING `(U,V)`, not zero,
which has no analogue in a from-scratch derive.)

---

## `wall-pan`: an anchor-only slide on an EXISTING frame, in WORLD space

Reproduces `WALLPAN`: slides `Origin` along the CURRENT `TextureV` until its world Z reaches zero,
touching nothing else. Unlike every other `align` mode, it does not derive a fresh frame — the frame
must already exist (typically from `wall`).

**Reads/writes via `world_uv_frame`/`_write_world_frame`, never `surface._frame`'s local fields.**
`WALLPAN`'s real target — UnrealEd's `Model->Surfs` — is a WORLD-space surface. Reading/writing the
LOCAL `poly.origin`/`texture_u`/`texture_v` fields directly would slide the brush's LOCAL Z to zero,
which only coincides with WORLD Z=0 when the brush sits at the world origin with no rotation — wrong
on any placed or rotated brush. (An earlier spec draft proposed the local fields, by analogy with
`rotate`/`scale`; caught in review before it shipped.)

**Needs its own missing-frame check, because `world_uv_frame` silently defaults instead of
raising.** A `None` `Origin` silently becomes local zero; a missing OR present-but-all-zero
`TextureU`/`TextureV` silently becomes a synthesized `_tex_basis` frame (`texframe.py`'s own
`_zero()` test, which `wall-pan`'s pre-check mirrors exactly — catching a PRESENT-but-zero axis,
not just a `None` one, took two review passes to get right). Calling `world_uv_frame` directly on a
never-aligned face would silently proceed with a synthesized frame instead of naming an error — a
silent half-answer `direction/conventions.md` forbids.

**Target grammar matches `align`'s (a bare brush Name is accepted), not `pan`/`rotate`/`scale`'s
narrower one.** Phase-syncing every wall face of a brush to world Z=0 is the normal use of this
verb, not a blanket edit an author would regret the way a blanket scale/rotate would be
(`../rationale/surface.md` "the target grammar is narrower than align's").

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

**Multi-brush.** Every step above keys off `(brush, poly)` pairs, not a bare poly index, and none of
the algorithms care: adjacency is a world-point edge match (`_edges_coincide`), already
brush-identity-blind before this even mattered, and branch/connectivity/non-quad/root-and-direction
all just walk whatever graph that adjacency produces. The one genuinely new code path is cross-brush
edge matching itself — `wall`/`floor`'s existing multi-actor precedent only proves the world-space
math (`_world_verts` per actor), never edge-coincidence matching, since those modes have no set
relationship to begin with. The root/phase tiebreak extends unchanged: sorting `(brush, poly)` tuples
sorts by brush name first, an arbitrary-but-deterministic choice in the same spirit as the
poly-index tiebreak above — it only moves where phase zero and the initial across-axis sign land,
never correctness.

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

## `one-tile`: reusing the projection table, but orthogonalised

`one-tile` fits exactly one texture tile per face, independently — no shared frame, no orientation
guard. It reuses `wall`/`floor`'s world-axis projection table (`_AXIS_UV`), keyed on the face's own
argmax axis over all three (not just X-vs-Y), but the raw table's two projected axes are NOT
perpendicular off that axis — `proj(B₁)·proj(B₂) = −(N·B₁)(N·B₂)`, zero only when `N` is square to
one of the two. On a corner normal `(0.577,0.577,0.577)` the raw pair is 120° apart, which both
shears the fitted image and moves the extent's minimum corner off a vertex (the min of a skewed
parallelogram's projections is not one of its own corners).

**Why it is this way.** Gram-Schmidt of U against V — keep V exactly as the table gives it (the
predictable up-vector the mode exists for), square U to it. Verified on the same corner normal: the
pair comes back to exactly 90° and the fit spans exactly `[0, extent]` on both axes. On every
axis-aligned face (the common case) the table's pair is already orthogonal and this is a no-op.

**Rejected: `U = V × N`.** Also orthogonal, but it re-derives its own sign rather than inheriting the
table's — it would mirror the image on half the face directions, the one failure this mode must not
have.

**The anchor is exact only because the frame is orthonormal.** With `Û ⊥ V̂ ⊥ n̂`, the world point
whose `(Û,V̂)` projections are exactly the extent's minimum corner is `Origin = P0 − (P0·Û)Û −
(P0·V̂)V̂ + min(pu)Û + min(pv)V̂` for any reference vertex `P0` — algebraically, `P0` with its `Û`/`V̂`
components replaced by the minimum corner's. Under the skewed (non-orthogonalised) pair this
construction does not hold, because the minimum of a skewed parallelogram's projections is not
reachable as a point of the frame at all.

**A zero-extent face is a division guard, not a real path.** A positive-area planar polygon has
nonzero extent along any direction in its own plane, so `_world_normal`'s zero-area check already
catches every real degenerate face before the extent guard could fire.

**Refs.** `../board/inbox/the-per-surface-verb-split/spec.md` §2.6;
`../board/to-plan/per-surface-texture-verbs/spec.md` §4; `uedcli/polyalign.py::_one_tile_align`.
