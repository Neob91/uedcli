# Spike — how faint a `--focus`-ed-out FILL should be

**Date:** 2026-07-27 · **Status:** complete, **ruled 0.35** by the owner from these renders ·
**Unblocks:** board item `four-actor-preview-faces-rulings-need-a-durable` §4.8 (S3 of
`actor preview --faces`)

## The question

`actor preview --focus <brush>` de-emphasises every brush except one. Under `--faces wire` it does that
by compositing their outlines at `_DIM_ALPHA` (0.15) over the background. Under `--faces flat` each
brush is a solid FILL, and the same treatment does not transfer: 0.15 was tuned for thin lines, where a
faint stroke still reads as a stroke, while a large flat area at that strength is near-uniform with the
background.

So: **at what opacity should a de-emphasised fill composite?** The owner reserved this call and ruled
(2026-07-26) that the value is chosen **from a real before/after render, not from arithmetic** —
arithmetic had already produced two wrong answers, both refuted on paper before any picture existed:

- `_fade(rgb, 0.75)` then an 0.25 composite (the original specification) leaves `0.0625·c + 210`
  against `BG` 224 — invisible.
- one `_DIM_ALPHA` (0.15) composite, as the wireframe uses, leaves a mid-grey texel ~14 levels off `BG`
  — flagged by every reviewer as probably also too faint, but never measured on a real fill.

## Method

`harness/render_ladder.py` renders one candidate per alpha over a fixed scene and prints, per candidate,
how far each fill colour the scene actually dims lands from the background.

Scene: a subtracted 1024×1024×384 room with an added pillar and an added crate inside it, at
`--layout single --view iso --size 700 --faces flat --focus <pillar>` (700² = 490,000 px). Reference:
the same scene with no `--focus`. It needs a resolvable project and the per-user games config, not just a
T3D snippet — `flat` loads the class hierarchy to tell a mover from a real subtraction.
**Building that project and its game-package config from scratch, and the actor names below:**
[`demo-scene.md`](demo-scene.md).

**Every image beside this file was produced by these two commands, and they reproduce it byte-for-byte**
— the harness's own output names ARE the committed names, so there is no renaming step to get wrong. (The
second command also writes `dim-nofocus-all.png`, the annotated reference, which is deliberately NOT
committed: nothing here cites it and the un-annotated reference already shows the before state.)

```
PYTHONPATH=<repo> .venv/bin/python harness/render_ladder.py <project> <outdir> \
    --level demo --actors Room_…,Pillar_…,Crate_… --focus Pillar_…
PYTHONPATH=<repo> .venv/bin/python harness/render_ladder.py <project> <outdir> \
    --level demo --actors Room_…,Pillar_…,Crate_… --focus Pillar_… --alphas 0.35 --annotate all
```

**The measure is PER CHANNEL, max and min.** `BG` is a neutral 224, so a saturated hue fades unevenly —
the subtract-gold `(205,180,110)` is already 19 levels off `BG` in red and 114 in blue before any
dimming. A single mean distance hides that, and the MIN channel is exactly what a reader needs: it is
how close to invisible the surface gets.

## The ladder

| alpha    | mid-grey 128 | room fill (205,180,110) | crate fill (0,0,200) | reading
|----------|--------------|-------------------------|----------------------|---
| 0.15     | 14           | 17 / 3                  | 34 / 4               | the room all but disappears — walls and the interior crease stop reading
| 0.25     | 24           | 28 / 5                  | 56 / 6               | the room is legible but flat; the crate is a pale ghost
| 0.30     | 29           | 34 / 6                  | 67 / 7               | usable; the low end of the band
| **0.35** | **34**       | **40 / 7**              | **78 / 8**           | **RULED.** The room reads as a room, the crate is unmistakably secondary, the focused pillar dominates
| 0.40     | 38           | 46 / 8                  | 90 / 10              | visually near-identical to 0.35, equally acceptable
| 0.45     | 43           | 51 / 9                  | 101 / 11             | the crate starts to compete for attention
| 0.50     | 48           | 57 / 10                 | 112 / 12             | the crate competes; the spotlight is weakening
| 0.70     | 67           | 80 / 13                 | 157 / 17             | no spotlight left — the crate is nearly as bold as the focus

## What decided it

**The dominant surface, not the mid-grey reference.** On this scene the subtract room's interior gold
covers **215,434 of 490,000 px** — 44 % of the frame — and at 0.15 it lands **3–17 levels** off `BG`.
That is worse than the quoted mid-grey figure of 14 suggests: the room stops reading as a room, the
crease between its walls vanishes, and the render loses precisely the spatial context `--focus` exists
to preserve. `--focus` de-emphasises the surroundings; it does not delete them.

At the other end 0.70 leaves the non-focused crate nearly as bold as the focused pillar, so there is no
spotlight at all. The useful band measured out at roughly **0.30–0.45**, which is why 0.30/0.40/0.45
were rendered on top of the five candidates originally asked for.

## The pictures

| file                | what
|---------------------|---
| `dim-nofocus.png`   | the BEFORE — same scene, no `--focus`, every brush opaque
| `dim-0.35.png`      | the AFTER, at the ruled value
| `dim-0.35-all.png`  | the ruled value at the default `--annotate`: face indices on the focused pillar only and in its tint, with the legend still naming all three brushes
| `dim-0.15.png` … `dim-0.70.png` | **every** row of the table above, so each judgement in it can be re-checked — including the 0.30 and 0.45 ends that the "useful band" claim rests on

## Regenerated 2026-07-29, after the hidden-edge ruling

The images were re-rendered when the owner narrowed the edge pass to VISIBLE faces only (a solid brush is
opaque). **The ladder measurements above are unchanged** — every blended colour, every per-channel
distance and the mid-grey figures are identical, because that ruling changes which OUTLINES draw and not
what a fill blends to. What moved in the pictures is that a hidden face's outline no longer sits on top of
a dimmed fill. The reference `dim-nofocus.png` is byte-identical either way, since on this scene every
hidden edge was already invisible by colour over its own brush's fill. **0.35 re-confirmed by eye on the
new renders.**

## Pinned

`uedcli/tests/test_preview_faces.py::test_the_dim_fill_alpha_is_its_own_constant_and_is_pinned` asserts
the value so it cannot drift unexamined; the reasoning is
[`rationale/preview.md`](../../rationale/preview.md).
