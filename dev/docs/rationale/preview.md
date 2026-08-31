# `preview.py` — the `actor`/`stash`/`prefab preview` renderer

Why the stdlib-only schematic renderer is the way it is. Revised in place — agents maintain this freely.

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

## The addressable grid's default density is auto-picked (agent choice, 2026-08-31, supersedes the flat `12`)

The always-on coordinate grid (owner-ruled 2026-08-02) leaves the DEFAULT cell count to us; a later
owner ruling (2026-08-31) fixed the GOAL — locator cells should visually align with the world
gridline overlay, not just independently pick a legible pixel size — and left the algorithm to us.
On an ortho view, `_auto_locator_lattice` walks power-of-two multiples of the gridline overlay's own
escalated step (so a boundary always coincides with a real drawn line) and validates the REAL
resulting cell widths (after merging any too-thin partial edge cell) against the label footprint,
escalating until every cell clears it. `iso` has no gridline lattice to anchor to, so it keeps the
earlier `_auto_locator_cells` — the finest independent power-of-two pixel size that avoids label
crowding. `--layout quad`'s 4 panes resolve density independently (each ortho pane may anchor to a
different step; `iso` always uses the pixel-fit fallback), so two panes can legitimately report
different `cols`/`rows`.

**Refs.** `uedcli/preview.py` `_auto_locator_lattice`/`_lattice_boundaries`/`_auto_locator_cells`;
`uedcli/tests/test_preview.py` locator/lattice tests; `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/`
(the world gridline overlay this anchors to).

**Rejected.** *8* — coarse; a cell spans a large area, so `D4` barely narrows a busy scene. *16/26* —
finer, but at 256-px panes (quad, breakdown) the gutter letters abut, and 26 reaches the last
single-letter column so any bump needs `AA`. *A world-space cell* — rejected in the spec: geometry
lands anywhere, so a fixed world grid would not divide the IMAGE evenly and `D4` would move with the
camera. The number is not load-bearing — `--grid N` overrides it — so 12 is a legibility default, not
a measured constant.

**Refs.** `uedcli/preview.py` `_col_label`/`_cell_of_pixel`/`_actor_cells`/`_draw_grid_gutter`;
`uedcli/cli/rendering.py` `_GRID_MAX`/`_grid_legend_lines`/`_grid_json`; `uedcli/tests/test_preview.py`
(the cell-math unit tests) and `test_actor_preview.py` (the legend/JSON/`--grid` dispatch tests).


## `textured` — the texel path over the SAME cull and depth buffer

`textured` reuses `flat`'s cull, `array("f")` depth buffer and occlusion test unchanged; only the
fill differs — each pixel samples the face's decoded texture through its authored UV frame instead
of one flat hue (`_fill_face_textured`).

**Why it is this way.**

- **UV is affine in screen space, solved once per face — no per-pixel perspective divide.** Under
  the orthographic preview camera `u(P) = dot(P − base_w, tu_w) + pan` is affine in world `P`, so it
  solves from the SAME three plane probes the depth map already uses (`_face_uv_affine` shares
  `_plane_screen_probes` with `_face_depth_affine`). One consequence pays for another: the screen
  gradients `(au, bu)`/`(av, bv)` the UV solve produces ARE the mip term below, computed for free.
- **The mip level is per FACE, from that face's own screen-space UV gradients**
  (`_mip_level` = `log2(max(hypot(du_dx,du_dy), hypot(dv_dx,dv_dy)))`, clamped to the pyramid). A
  single view-global projection gain understates the rate on an oblique wall — ~1.7× at the default
  iso angle, unbounded near edge-on — and would alias exactly the grazing surfaces a texture check
  most needs to read.
- **Nearest-neighbour with Euclidean wrap** (`int` `%` on the mip's `w`/`h`). Matches `render.rs`;
  no filtering, so a texel edge is a texel edge in the preview.
- **A masked hole writes neither colour NOR depth.** When the face is masked and the sampled texel's
  `mask == 0`, the pixel is skipped entirely, so a face BEHIND the hole shows through; an unmasked
  face draws palette index 0 as an ordinary colour. The masked answer is resolved in dispatch as
  `(poly.flags | actor PolyFlags) & PF_Masked` **OR** the decoder's `bMasked`, off the typed result —
  one gate, no separate predicate.
- **Shade matches the native tier.** `_face_shade` = `0.55 + 0.45·|N·L|/|N|` on the world Newell
  normal, and the colour is `min(int(texel·shade), 255)` per channel — byte-for-byte `render.rs`'s
  key light and truncation, so `--native` and this tier agree up to f32-vs-f64 (spec §4.9). A face
  `render.rs` also skips (< 3 vertices, zero-length normal) shades `None` and is dropped.

**Rejected.**

- **A view-global projection gain for the mip** — two earlier drafts of the feature derived it this
  way and both were measured wrong; the per-face gradient is the correction, tested at a non-default
  `--iso-angle` where the wrong derivation is ~7× off.
- **`DEFAULT_GREY` as a fallback for a texture the render cannot produce** — a non-finite UV frame,
  or an unreadable/bare/undecodable ref. Grey is pixel-identical to a legitimately untextured face
  (`tex_index < 0`), so a fallback would hide the very defect this mode exists to surface. Each such
  case is a clean exit 2 naming the actor/poly or listing every offending ref (a bare ref says to
  qualify it `Package.Name`); a missing resolver names which of its three causes applies; a scene
  that references NO texture renders with no texture source at all (the owner's literal "needs").
  The refusals themselves are the owner's product ruling (board item
  `four-actor-preview-faces-rulings-need-a-durable`), recorded here only for the engineering reason
  grey cannot stand in.
- **Bilinear filtering, and scaled/sheared brushes under `textured`** — both deferred (plan §5). A
  scaled or sheared brush exits 2 listing every offender, because its geometry is built with the full
  linear transform while the UV frame uses rotation only, so the texture would not follow the
  geometry — a wrong answer in the one tool meant to be authoritative about UV.

**Refs.** `uedcli/preview.py` `_fill_face_textured`, `_face_uv_affine`, `_mip_level`, `_face_shade`,
`_plane_screen_probes`, `DEFAULT_GREY`; `uedcli/cli/rendering.py` `preview_textures`,
`_reject_transformed_brushes`, `_reject_explicit_brush_colors`, `_texture_resolver_cause`;
`uedcli/tests/test_preview_faces.py` and the golden `tests/fixtures/preview_textured_golden_iso.png`.
