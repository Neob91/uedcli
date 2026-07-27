# uedcli — `brush preview` rendering improvements (design)

**Status:** spec (ephemeral). Resolves `to-resolve.md` #16. The viewer
(`uedcli/preview.py`, stdlib-only P6 PPM) exists so an LLM can map a poly **index** to a
**face** for model-side surface edits; these changes make stacked/concentric geometry legible.
Revised after two cold reviews — see "Review corrections".

## Current state (what we're changing)

`render_brushes_pgm` draws a pure **wireframe**: front edges black (`FRONT`), obscured edges
solid light-grey (`BACK=165`), the highlighted poly red. Faces are **not filled**. Index labels
(front faces + the highlight) sit in white **knockout boxes** anchored at the face centroid,
greedily de-collided (`_place_labels`, current return shape `(anchor, label_pos, text, hi)`),
with a dot+leader **only when nudged** (`preview.py:295`, `if (lx,ly)!=(ax,ay)`). `render_quad_pgm`
tiles four panes and draws each pane's **caption over the geometry** (`preview.py:326`). Depth is
expressed by `_DEPTH[view]` (per-ortho direction vectors) and `_iso_depth(iso_angle)`, used by
`_is_front`. Helpers: `_line`, `_fill` (axis-aligned rectangle only), `_box`, `_dot`,
`_draw_text`, `_face_normal`, `_is_front`. **There are no golden-PPM fixtures** — `test_preview.py`
is property-based (pixel counts, color presence, render inequality).

## The improvements

### 1. Pane captions out of the geometry — QUAD ONLY (item: "do not overlay view labels on geometry")

Captions (TOP/FRONT/ISO/SIDE) are a **quad** concept; single-view renders have none. So this
change is confined to `render_quad_pgm`: reserve a `CAP_H = caption_height + 4` px **strip** at
the top of each pane and draw the caption there on a solid background. The sub-pane is rendered at
`size=half`, so to keep the strip clear the copy must **clip, not merely offset**: render the
sub-pane at `size = half - CAP_H` (or copy only its top `half - CAP_H` rows) into the pane
starting at row `oy + CAP_H` — a plain offset without the row-count reduction overflows the
pane/divider, and `test_it_keeps_captions_out_of_the_geometry_strip` (no geometry ink in the top
`CAP_H` rows) only holds with the clip. Remove the current over-geometry `_draw_text` caption draw
(`preview.py:326`) so it isn't double-drawn. `render_brushes_pgm` (the single-view path) is
**untouched** by captions — preserving its output and tests.

### 2. Very-translucent grey face fills (item: distinguish polygon from empty space; see stacking)

Fill each projected face with grey at **low alpha** (`FACE_ALPHA = 0.12`), composited
**back-to-front** so overlapping faces accumulate: one face is faint, stacked faces read
progressively darker, and **empty space stays white** — the "tell a polygon from the gap behind
it / see faces behind faces" the question asks for. (The precise per-pixel result depends on
fill order and the highlight's different alpha, so we claim "monotonically darker where more
faces overlap," not an exact formula.) New pieces:
- **`_fill_poly(buf, size, pts, rgb, alpha)`** — an **even-odd scanline fill** (NOT min/max-span;
  the viewer renders arbitrary `main/` brushes incl. `actor add <t3d>` content that may project
  non-convex) with per-pixel integer alpha blend `dst = int(round(dst*(1-α) + src*α))` per
  channel, reading the already-blended pixel so painter's accumulation is correct. **No-ops on
  `< 3` points or zero vertical extent** (edge-on faces project to a line — fill nothing, edges
  still draw); guards against divide-by-zero in edge slopes.
- **Depth sort:** `_face_depth(v3, view, iso_angle)` = dot product of the face centroid with the
  **same** depth vector `_is_front` uses (`_DEPTH[view]`, or `_iso_depth(iso_angle)` for iso) —
  reuse, don't invent a "dropped axis" rule (the sign is already chosen to match the cull). Sort
  faces so the **farther** face fills first; equal-depth ties are visually negligible under
  same-color alpha. (For ortho views the depth vector is a pure axis, so this is the true
  view-depth; for iso, `_iso_depth` is the cull direction, so the sort is **cull-consistent**, not
  a guaranteed perceptual z-order — acceptable for this viewer, whose job is to *show* stacking,
  not photoreal occlusion.)
The highlighted poly is filled with translucent **red** (`HI_ALPHA = 0.22`) **and** keeps its
**opaque red edges** (so it's unambiguous and the exact `HI=(220,0,0)` stays present for tests).

### 3. Dashed hidden lines (item: "lines behind polygons dashed")

Obscured edges (`_is_front` false) draw with a new **`_dashed_line`** (4px on / 3px off) instead
of solid grey. Keep the dash ink **exactly `BACK=(165,165,165)`** (same constant, now dashed) so
`test_front_black_back_grey` needs only to assert the back run is dashed, not a new colour. Front
edges stay solid black. Separates silhouette from occluded structure even where fills are faint.

### 4. Reduce index ambiguity for concentric faces (item: bigger poly puts its index outside the smaller ones)

When faces of different sizes share ~the same projected centroid, centroid-anchored labels pile
up. `_place_labels` gains an **optional** `faces: list[polygon] | None = None` arg (default None →
**exact current behavior**, so the three existing `_place_labels` tests pass unchanged). When
supplied:
- Process labels **smallest-projected-area first**, so a small face keeps its centroid and a
  larger face is pushed outward.
- For each face, try **deterministic** candidate anchors in fixed order: (1) the centroid, then
  (2) each edge midpoint **in vertex order**, then (3) each edge midpoint stepped 60% and 85%
  from centroid toward it. Pick the first candidate that lies inside **this** face
  (`_point_in_poly`) and **outside** every smaller already-placed face. If none clears, fall back
  to a point on this face's bounding-circle edge nearest open space (still better than the
  status-quo nudge), then the existing greedy ring de-collision as a last resort.
- **Leader rule (resolves the draft's contradiction):** draw a leader+dot **iff the anchor was
  moved off the true centroid**. The heuristic moves the *larger* face → it gets a leader; the
  small face keeps its centroid → no leader unless separately nudged. (No "always draw a leader."
  )
The area-sort and extent test apply only when `faces` is passed (the `brush preview` path);
callers that don't pass `faces` get today's ordering, so the ordinary multi-face de-collision is
unregressed.

### 5. Other improvements (the "any other ideas")

- **Depth cue on front edges:** since black is already darkest, the cue **lightens FAR** front
  edges (nearest stays pure `(0,0,0)`) via the `_face_depth` already computed, so parallel stacked
  faces separate pre-label — and the nearest front edge remains `(0,0,0)`, keeping
  `test_front_black_back_grey`'s black assertion valid.
- **Per-pane axis hint** in the caption strip (e.g. `TOP  X→ Y↑`) — direction without guessing;
  lives in the strip (item 1), never over geometry.
- **`--no-faces` flag** — wireframe escape hatch for dense scenes (see contract below).
- **Highlight label on top** — drawn last so it's never occluded by another label's knockout.

## Surface / params & threading

`faces: bool = True` is added to **three** sites (the existing kwargs are threaded explicitly, not
generically): `render_brushes_pgm` (does the fill pass), `render_quad_pgm` (accept + forward to
its internal `render_brushes_pgm` call, `preview.py:319`), and `_render_actors_to_out`
(`dispatch.py:228-233`, both the quad and single-view branches). The `brush preview` CLI gains
`--no-faces` (→ `faces=False`); `--view/--size/--no-label/--png` unchanged, all with real `help=`
strings (folds in `to-resolve.md` #12/#18; also give `--size` the help string it currently
lacks at `cli.py:71`). Module constants `FACE_ALPHA`, `HI_ALPHA`, `CAP_H`.

### `--no-faces` contract

`--no-faces` means **omit the translucent fills**; it does **not** promise byte-identity with the
pre-change renderer (items 3 dashed-edges and 5 depth-cue still apply — they're improvements, not
fill). Its regression guard asserts **no fill pixels are present** (the scene is wireframe), not
byte-equality.

## Architecture & file structure

All in **`uedcli/preview.py`** (330 lines; stdlib-only — keep it that way). New pure helpers:
`_fill_poly` (even-odd scanline + integer alpha; degenerate-safe), `_dashed_line`,
`_point_in_poly`, `_face_depth`. `render_brushes_pgm` gains a depth-sorted fill pass, dashed
hidden edges, the depth-cue, and passes per-face polygons to `_place_labels`. `render_quad_pgm`
moves captions into a reserved strip. `cli.py`/`dispatch.py` thread `faces` (3 sites above).

**Render order (back-to-front, later wins):** translucent face fills (far→near) → hidden dashed
edges → front solid edges (depth-cued) → highlighted edges (opaque red) → labels (knockout + text
+ leader-iff-moved + dot) → (quad only) caption strips + dividers.

## Testing

Offline, deterministic — assert on pixel samples, not eyeballing. **No golden PPMs exist**, so:

- **Existing tests to update (named so the implementer isn't surprised):**
  - `test_front_black_back_grey` — back edges are now **dashed** grey; reframe to assert the back
    edge is a dashed grey run (alternating ink/white) and the front edge a solid black run.
  - `test_highlight_poly_is_red` — still valid: the highlight keeps **opaque red edges**, so exact
    `(220,0,0)` remains present (the translucent red fill is additional). Keep as-is.
  - `test_poly_index_labels_add_pixels`, `test_multi_brush_render_overlays_both` — still pass
    (fills only add pixels); no change needed, but note they no longer isolate label/edge ink.
  - The three `_place_labels` tests — **unchanged**, because the new `faces` arg defaults to None
    (back-compat).
- **New tests:**
  - `test_it_keeps_captions_out_of_the_geometry_strip` — quad render: caption ink only in the top
    `CAP_H` rows of each pane; the geometry region below has none.
  - `test_it_darkens_where_faces_overlap` — 2-brush scene, one face behind another: the overlap
    region's mean RGB is lower than a single-face region; empty space stays `(255,255,255)`.
  - `test_it_dashes_hidden_edges` — an obscured edge alternates ink/white; a front edge is solid.
  - `test_it_labels_concentric_faces_without_leader_clutter` — two concentric different-size
    faces: their label boxes don't overlap; the **larger** face's label has a leader to its
    centroid, the **smaller** keeps its centroid (no leader).
  - `test_it_no_faces_flag_omits_fills` — `faces=False` → no interior fill pixels: sample an
    interior pixel known to be **off every projected edge** (or assert the fill-grey value is
    absent from the buffer), since dashed hidden edges/depth-cue lines still cross face interiors.
    Edges/labels still drawn. (NOT byte-equality.)
  - `test_point_in_poly`, `test_fill_poly_even_odd_and_alpha` — the new helpers (a concave test
    polygon for even-odd; half-alpha grey over white → ~128 with `int(round)`).

## Out of scope

- Anti-aliasing / sub-pixel edges (stdlib raster).
- True hidden-surface removal / z-buffer — the translucent painter's fill + dashed hidden edges
  intentionally **show** occluded structure; culling it would hide what the LLM must see.
- `--zoom-poly` and `level preview` (live editor) — unaffected; this is the offline viewer only.

## Review corrections (what the cold reviews fixed)

- No golden-PPM "re-bless" — there are none; the affected **property** tests are enumerated, and
  changes are made back-compatible where possible (`_place_labels` new arg optional; highlight
  keeps opaque red edges so `(220,0,0)` stays present).
- Captions are **quad-only**, leaving the single-view path (and its tests) untouched.
- `--no-faces` only omits fills (no byte-identity claim); its test asserts no fill pixels.
- Depth sort reuses `_DEPTH[view]`/`_iso_depth` via a dot product (`_face_depth`), not a loosely
  "dropped axis" with ambiguous sign.
- Fill is **even-odd** (no convexity assumption — imported brushes may project non-convex) and
  **degenerate-safe** (`<3` points / zero extent → no-op).
- The concentric-label candidate schedule is **deterministic** (fixed order + steps); the leader
  is drawn **iff the anchor moved** (resolving the draft's self-contradiction).
- `faces` threaded through **three** sites (corrected the "already forwards" claim).

## Decisions captured (for `decisions.md` on landing)

- **Translucent even-odd painter's fills + dashed hidden edges** (show, don't cull, occluded
  geometry) — an editor viewer must reason about faces behind faces; a z-buffer hides exactly
  what's needed. Rejected: opaque depth-sorted fills; pure wireframe (status quo #16 dislikes);
  convex-only span fill (breaks on non-convex imported brushes).
- **Smallest-face-first, deterministic extent-aware label placement, leader-iff-moved** — resolves
  concentric ambiguity reproducibly. Rejected: centroid-only + greedy nudge (the ambiguous
  status quo); "always draw a leader" (clutters the common case, self-contradictory).
- **Faces-on default, `--no-faces` omits fills only** — the translucency is the requested default;
  the flag is the dense-scene escape hatch, not a byte-for-byte classic mode.
