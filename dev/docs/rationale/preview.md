# `preview.py` — the `actor`/`stash`/`prefab preview` renderer

Why the stdlib-only schematic renderer is the way it is. See [`README.md`](README.md) for the index and
the entry shape. Revised in place — agents maintain this freely.

What the renderer DOES is [`../architecture.md`](../architecture.md) "Preview internals"; the owner's
product decisions about `actor preview` are parked on `dev/docs/board/inbox/` pending a `direction/`
home. This file holds only the engineering.

---

## `--focus` over a FILLED mode: ONE scene-order pass, plus a per-pixel dim mask

Every filled face — de-emphasised or not — goes through **one** rasterizing loop in **scene order**,
writing one depth buffer. A byte per pixel records whether the surface that WON it belongs to a
de-emphasised brush, and `_fade_dimmed` fades exactly those pixels toward `BG` afterwards.

**Why it is this way.** Three properties have to hold at once, and this is the shape that gets all three:

- **One blend per pixel.** Blending as each face rasterizes blends once per face that passes the depth
  test, so N overlapping de-emphasised faces fade a pixel N times and the result depends on face
  iteration order. Fading once at the end, off the mask, cannot.
- **Visibility must not depend on `--focus`** (the owner's model). The depth test is strictly `<`, so a
  coplanar tie goes to whichever face is rasterized FIRST. **Any** design that groups the de-emphasised
  faces into their own pass therefore lets `--focus` decide which of two flush surfaces you see — and a
  flush add/subtract pair is ordinary pre-CSG geometry. One list in scene order is what makes the
  tie-break independent of focus, not a detail of how the blend is done.
- **One depth buffer**, so nothing is privileged by being focused.

**Rejected.** *Resolving the de-emphasised faces into a scratch canvas and compositing it first* — this
was shipped and then removed. It satisfies the first and third properties but breaks the second: focusing
a room lost the room's own floor and showed a flush slab through it at context brightness, and
`--layout breakdown` focuses every brush pane in turn, so it was the common case rather than a corner.
The mask also deletes the scratch canvas outright, so the correct version is the cheaper one.
*Fading per face and accepting the order dependence* — makes the render a function of poly order, which
nothing else in this renderer is. *An epsilon depth bias to break ties deterministically* — a bias only
relocates the arbitrariness, and `_fill_face` rejects it for that reason.

**The model itself is NOT this file's decision.** That the cull is the whole of visibility and everything
past it is ordinary physical depth regardless of focus is the **owner's ruling** (2026-07-29), described in
[`../architecture.md`](../architecture.md) "Preview internals" and parked for a `direction/` home on board
item `four-actor-preview-faces-rulings-need-a-durable`. Same for `--highlight`: it overrides `--focus`'s
dimming but not depth, so a highlighted face nothing can see contributes nothing.

**Refs.** `uedcli/preview.py` `_fade_dimmed`, `_fill_face`'s `dim`/`dimmed`, `render_brushes_pgm`;
`uedcli/tests/test_preview_faces.py` (the once-per-pixel replay, the coplanar tie across `--focus`, and
the three physical-depth cases).

## The fill dim strength is a SEPARATE constant from the line one — `_DIM_FILL_ALPHA = 0.35`

Distinct from the `_DIM_ALPHA` (0.15) that dims a non-focused wireframe, which is unchanged. **0.35 is
the owner's value, picked from a ladder of real renders rather than from arithmetic** (their decision
2026-07-26 reserved the call; ruled 2026-07-29).

**Why it is this way.** 0.15 was tuned for thin LINES, where a faint stroke still reads as a stroke. A
large flat AREA at that strength is near-uniform with the background. Only the engineering half is this
file's: the constant exists **separately** rather than being shared, because one number cannot serve both
a 1-px stroke and a 200,000-px surface, and it is **applied as a single composite** of the resolved
context rather than baked into the fill colour, so the same fill value keeps its exact palette entry when
unfocused (the legend is read against it).

**Rejected.** *One constant for both* — **measured, and 0.15 rejected on the measurement**: on the ladder
scene the dominant surface is the subtracted room's interior, 215,434 of 490,000 px, and at 0.15 it lands
**3–17 levels off `BG`** per channel. Walls and the crease between them stop reading, so the render loses
the spatial context `--focus` exists to preserve — worse than the ~14-level mid-grey prediction suggested.
*`_fade(rgb, 0.75)` then a 0.25 composite* (the original specification) — it leaves `0.0625·c + 210`
against `BG` 224, i.e. invisible. *Deriving the value from a contrast target* — the owner reserved the
call precisely because arithmetic had already produced those two wrong answers; re-run the ladder instead.

**0.35 is not precise, and must not be treated as if it were.** 0.40 was judged **equally acceptable**
and the useful band measured out at roughly 0.30–0.45; the ends (0.15/0.25 too faint, 0.50/0.70 no
spotlight left) are what the choice was made against. A future change inside that band is a judgement
call, not a regression — but it is the owner's call, and it needs new renders.

**Refs.** `dev/docs/spikes/2026-07-27-preview-focus-dim/` (the ladder, the before/after pair and the
harness); `uedcli/preview.py` `_DIM_FILL_ALPHA`; `uedcli/tests/test_preview_faces.py` pins the value.
