# Spec DRAFT — `actor diagram` rendering improvements

Status: draft for owner review. **Replaces the prior spec, which was stale** — it described a
330-line `brush preview` with a pure-wireframe renderer and no golden fixtures. Since then the verb
is `actor diagram`, `preview.py` is ~2600 lines, `--faces {wire,flat,textured}` shipped (board
`actor-preview-faces`), and byte-pinned goldens exist. This draft re-enumerates the wanted
improvements against what is actually shipped.

## Goal

Make stacked / concentric brush geometry legible in the offline viewer, and get pane captions off the
geometry — without undoing the opaque, non-x-ray visibility model the owner ruled for `--faces
flat`/`textured`.

## Enumeration — every wanted improvement vs shipped state

| Improvement | Shipped? | Verdict |
|-------------------------------------------------|----------|---
| Filled faces (solid fills) | YES — `--faces flat` | done |
| Depth resolution (nearest wins) | YES — z-buffer `_fill_face` (`preview.py:823`) | done |
| Concentric-face index disambiguation | YES — on-face inscribed-box decals (`_max_inscribed_box`, `preview.py:1458`) place each index inside its OWN face | done |
| Translucent grey back-to-front compositing (x-ray for stacked/concentric shells) | NO — `flat` is opaque, x-ray ruled OUT | **fork** (§A) |
| Pane captions in a header strip, not overlaid (quad) | NO — quad overlays; breakdown already strips | ship (§B) |
| Dashed hidden lines | NO — shipped a lighter-grey back edge instead (`BACK=(165,165,165)`, `preview.py:95`) | recommend skip (§C) |
| Per-pane axis hint (e.g. `TOP X→ Y↑`) | NO | optional, fold into §B |

## Current state (file:line)

- `--faces {wire,flat,textured}` — `cli/parsers/_arguments.py:219`. `flat`/`textured` are opaque,
  nearest-wins, non-x-ray **by owner ruling** (board `four-actor-preview-faces-rulings-need-a-durable`:
  "A SOLID BRUSH IS OPAQUE", "nearest surface wins per pixel", "never an x-ray" — ruled deliberately,
  more than once).
- Quad captions are **overlaid** on the geometry: `render_quad_pgm` draws each pane name with
  `_draw_text` at the pane corner, nudged below the legend (`preview.py:2536–2539`).
- `--layout breakdown` **already** uses a 16 px header band per pane (`_BREAKDOWN_CAPTION_H`,
  `cli/rendering.py:286–296`) — the pattern §B wants for quad.
- Wire back edges are lighter grey, not dashed (`preview.py:95`, `2158`).
- Depth/composite primitives already exist: `_face_depth_affine` (`preview.py:634`), `_blend_px`
  alpha (`preview.py:1658`), `_face_shade` (`preview.py:716`).

## A. Translucent x-ray mode (the fork)

A grey back-to-front alpha composite lets concentric shells and stacked volumes show through — the
OPPOSITE intent of `flat`'s opaque model. It cannot be a tweak to `flat`; it is a distinct mode whose
whole point is x-ray, which the owner ruled out for the opaque modes. **Whether the owner still wants
it, given those rulings, is the item's central question** (`questions/translucent-xray-mode.md`).

If approved, the surface consistent with `--faces` already being the fill-model selector
(`direction/conventions.md` "verbs compose / one flag") is a fourth value:

```
--faces {wire,flat,textured,ghost}
  ... 'ghost' = every face composited back-to-front in translucent grey (painter's order by
  face depth), so stacked and concentric volumes all show through — an occupancy / x-ray view,
  NOT what the game would show. Loads the class hierarchy for the mover-vs-subtract check like
  flat/textured, so it needs a resolved project + games config (unlike wire).
```

- Mechanics: sort faces far→near by `_face_depth_affine`, `_blend_px` each at a fixed grey alpha.
  The alpha constant is **chosen by looking at a render**, not arithmetic (the owner's ruling), and
  the before/after image is kept with the value.
- `ghost` is additive: it does not touch `flat`/`textured`. `--highlight`/`--focus` behaviour under
  an inherently-x-ray mode is part of the question.
- Rejected surface: a separate `--xray` boolean — it combines with `--faces` into ambiguous states
  and duplicates the one fill-model selector.

## B. Quad header-strip captions (recommend: ship)

Move quad pane captions off the geometry into a band above each pane, matching `breakdown`. This is
the literal overview ask; it is a visible change to the default quad output.

- Grow each quad pane cell by a caption band (reuse `_BREAKDOWN_CAPTION_H`, scaled with `--size`),
  offset the pane blit down, draw the name into the band. Stays stdlib (quad is a pure-PPM path).
- The legend no longer has to dodge the caption, so the `preview.py:2537` special-case is removed.
- Optionally put the per-pane axis hint (`X→ Y↑`) in the band — cheap once the band exists; include
  only if the owner wants it (open question).
- No new flag; it is the new default quad appearance.

## C. Dashed hidden lines (recommend: skip)

The old spec proposed dashing obscured edges. The shipped solution instead renders back edges a
lighter grey, which already separates silhouette from occluded structure. Dashing on top would add
complexity for a marginal gain and re-pin every wire golden. Recommend not doing it unless the owner
finds the lighter-grey cue insufficient.

## Recommendation

Ship **B** now (owner already asked for it). Gate **A** on the question. Skip **C**. Treat the axis
hint as an optional add-on to B.

## Edge cases

- B changes every quad byte-pin — expected; re-pin goldens in the same change and update
  `docs/usage.md`'s `--layout` text.
- A (if approved): a one-brush scene composites to ~its outline — verify it still reads; back-only
  subtract faces must sort without a NaN depth; adding `ghost` must leave `wire`/`flat`/`textured`
  byte-unchanged.

## Tests

- B: re-pin quad goldens; assert no caption glyphs over geometry and no legend/caption overlap.
- A (if approved): goldens on a concentric fixture (two nested subtracts) showing inner geometry
  through the outer shell; a test that `wire`/`flat`/`textured` output is byte-unchanged by the new
  mode.

## Open questions

- `questions/translucent-xray-mode.md` — does the owner still want a translucent x-ray mode (A),
  given the opaque non-x-ray rulings on `flat`/`textured`? Blocks A only; B proceeds regardless.
- Confirm B (header-strip captions) becomes the default quad appearance (a visible change), and
  whether to include the per-pane axis hint.
- If A is approved: exact name (`ghost`?), grey-only vs faint CSG tint, and `--highlight`/`--focus`
  behaviour under it.
