+++
priority = "p1"
kind = "implement"
summary = "Edge visibility is per-face, so a partly hidden face x-rays its whole outline; the owner has ruled per-pixel is the answer"
+++

# Edge visibility is per-face, so a partly hidden face x-rays its whole outline

**Owner ruling: go PER-PIXEL — true hidden-line removal. Deferred to this item, deliberately not
built in S3.** *(Owner ruling, 2026-07-30.)*

## The defect

`preview.py`'s `hidden` set is keyed per **face**, not per pixel (grep `_face_is_occluded`). A face is
in `hidden` only when it is occluded *everywhere*, so a face that is **partly** visible draws its
**entire** outline — including the buried part, straight over whatever solid geometry stands in front
of it.

Measured on `Slab` (semisolid 600×600×600 at `-500,-500,0`, nearer the camera) plus
`Rear` (200×200×1400 add), `--view iso --size 300`:

| case | measurement |
|---|---|
| `--faces flat --highlight Rear:1` | changes 2874 px, of which **557 sit on pixels the slab's nearer fill won the depth test** |
| `--faces flat`, no highlight | **404 px** of `Rear`'s ordinary outline paint over `Slab`'s fill |

So it is not a highlight-only effect: every filled render leaks the outlines of partly-hidden faces
through solid brushes.

## What the owner ruled

**Per-pixel:** clip every edge against the depth buffer as it draws, so an outline stops where
geometry covers it. That makes the "never x-rays" promise literally true and is the consistent
reading of the physical model ruled in S3 — *"render everything as it would appear in the real
world"*.

**Rejected:** qualifying the docs to describe per-face behaviour instead (an approximation, cheap and
predictable, but it leaves a solid brush not reading as solid); and a split rule that depth-clips
ordinary edges while letting a highlighted face keep its full outline (reintroduces
highlight-as-x-ray, which the owner had already ruled out).

## State as of S3's close — READ THIS BEFORE STARTING

- **The behaviour is unchanged.** S3 ships per-face visibility. Nothing here is implemented.
- **The user-facing docs currently OVERCLAIM, and were deliberately left that way** so a doc edit
  would not pre-empt this ruling. Both of these state an absolute the code does not honour:
  - `docs/usage.md` — "re-colours **what is visible** and never x-rays: a highlighted face that
    something in front of it hides shows nothing"
  - `cli.py`'s `--highlight` help — "re-colours what is VISIBLE and never x-rays: a face hidden
    behind something at this `--view` draws nothing"
  Whoever implements this makes those two true. **If this item is dropped instead, they must be
  corrected to describe per-face behaviour** — leaving them as they are is not an option either way.
- `architecture.md` and `_face_is_occluded`'s docstring already say "per-FACE … deliberately not
  hidden-line removal", so the *implementation* is documented honestly; only the user-facing pair
  overclaims.
- **The related S3 note clause is already correct** and needs no change: `--highlight`'s help and
  `docs/usage.md` say the stderr note fires when a selector is "not visible for any reason", which
  covers all four causes (depth, subtract cull, `PF_Invisible`, no coverage).

## Cost, so it is priced before anyone starts

A depth test per edge pixel, on top of a fill stage that already roughly doubled when S3 added the
per-face visibility walk. Spec §7's `--faces` timing predates both, so it is stale — re-measure
rather than extrapolating. Owner decision 2.4 sets no cost ceiling, so this is information, not a
blocker.

## Where the evidence lives

Found by the S3 re-gate round 1 review. The scene above reproduces it; the demo scene and the
coplanar repro are in `dev/docs/spikes/2026-07-27-preview-focus-dim/demo-scene.md`. Related and
already resolved: the ≤1 px silhouette overhang tracked by `filled-edges-on-every-face-extend-a-faceted`
(on `master`), which S3's visibility rule fixed from the other direction.
