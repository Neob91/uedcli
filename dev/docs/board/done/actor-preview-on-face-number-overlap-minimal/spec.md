# Spec: reposition on-face number decals to reduce screen-space overlap

Status: draft (2026-07-23). Ephemeral — fold the durable outcome into `architecture.md` /
`unrealed/*.md` and record the decision in `decisions.md` once built.

## Problem

Each on-face poly-index decal is planned **independently** (`_plan_onface_texture` →
`_max_inscribed_box`): it lands at the single roomiest spot inside its own face, sized to
`_ONFACE_FILL` (0.75) of the largest glyph-box that fits there. No decal knows about any other. So
when two faces project close together on screen — including **two faces of the SAME brush**, which
`--breakdown` does NOT separate (a breakdown pane still shows every one of that brush's faces) —
their number boxes can land on top of each other and neither reads.

## Goal

An **always-on**, deterministic layout pass that nudges each decal WITHIN ITS OWN FACE (never onto
another face) to reduce screen-space overlap with (a) other number decals and (b) point-actor
marker footprints. Levers, in preference order: **move** (slide to a roomier-of-overlap spot at full
0.75 size), **rotate** the glyph a multiple of 90° when that lets a bigger box fit, and **shrink**
below 0.75 down to — never past — the on-screen readability floor (`_ONFACE_MIN_TEXEL_PX`). A decal
that cannot reach the floor at any candidate is omitted, exactly as today.

Non-goals: cross-face moves; **rotating/upsizing/moving a decal that has NO overlap** (a
zero-overlap decal stays exactly where it is today — see the candidate-0 guard); **rescuing a face
that is omitted today** (if today's placement is unreadable → still omitted; rotation is an
anti-overlap lever, not a way to add numbers); moving point-actor labels (they already flee decals
via `occupied`).

"Overlap set = point-actor markers": the obstacle is each point actor's fixed on-scene **marker
footprint** (the rect seeded into `occupied` at `preview.py:1459`) — the point actor's only on-scene
glyph in hybrid mode (its name lives in the legend). Legacy on-geometry point NAMES are placed after
decals (`_place_labels`, `:1499`) and already flee decal boxes via `occupied`, so mutual avoidance is
covered from that side; they are not separately added as decal obstacles.

The legend rect is present in the obstacle snapshot too (it is in `occupied`, `:1470`), but that is
harmless, not a goal: the framed scene sits BELOW the reserved legend band, so a decal's overlap with
it is always 0. We do not special-case removing it.

## Decisions captured (from the user, 2026-07-23)

- Overlap set = **other number decals + point-actor markers**. Legend excluded (reserved area).
- **Shrink to separate**, down to the readability floor (below it → omit, as today).
- **Allow 90° rotation** when it fits a bigger box.
- **Always-on** (no flag).

## Design

### Where it plugs in

The change is contained to the `painted_draws` planning loop in `render_brushes_pgm`
(`preview.py:1483`). Today that loop plans one decal per `poly_labels` entry and appends its bbox to
`occupied`. Replace it with: generate candidates per entry → resolve jointly against `occupied` →
commit one plan per entry → seed `occupied` with the committed bboxes (unchanged downstream: name
leaders still avoid decals).

The obstacle set is the **`occupied` list as it stands when the loop begins** — it already contains
point-actor marker footprints (`preview.py:1459`) and the legend rect (`:1470`). No new plumbing for
obstacles. Opacity is unchanged: `_decal_opacity(_occluder_count(c, dep, …))` uses the face centroid
`c`, independent of where the decal sits on the face.

### Candidate generation — `_onface_candidates(v3, world_to_pxf, text, *, min_texel_px) -> list[_DecalPlan]`

For a face, produce an ordered list of placements. **Candidate 0 is, by construction, today's exact
placement**; the rest are the extra options the resolver may reach for ONLY when candidate 0
overlaps (the guard below enforces "only when").

Helpers, factored out of the current code so there is one implementation each:

- `_max_inscribed_box(poly_uv, cols, rows)` — unchanged; returns `(center_uv, max_cell)` = the
  max-box centre and largest cell for that glyph aspect.
- `_decal_plan_at(basis, center_uv, cell, bitmap, cols, rows, world_to_pxf, *, min_texel_px)` — the
  tl/ex/ey math currently inline in `_plan_onface_texture` (lines 1020-1034), extracted verbatim
  INCLUDING the readability gate: returns a `_DecalPlan`, or **`None` when the projected texel is
  below `min_texel_px`**. `_plan_onface_texture` becomes a thin wrapper:
  `_decal_plan_at(basis, *_max_inscribed_box(...)-scaled-by-fill, ...)`.
- **New** `_feasible_centers(poly_uv, hw, hh) -> list[tuple[float,float]]` — a UNIFORM list (not two
  shapes) of centres at which an axis-aligned box of half-extents `(hw, hh)` fits inside `poly_uv`.
  Convex (Minkowski erosion): erode each edge inward by its support `hw·|nx| + hh·|ny|` via the
  existing `_clip_ge` and intersect → an eroded polygon; return its centroid + each vertex nudged 5%
  toward the centroid (empty list if the erosion collapses). This is the erosion already inline in
  `_max_inscribed_box`'s convex path — that path is refactored to call this helper. Concave: the
  feasible subset (`_box_fits_2d`) of the existing bounded grid + vertex/edge-midpoint seeds.

**Candidate 0 (always first):** `center_uv, max_cell = _max_inscribed_box(poly_uv, cols, rows)`
(0° aspect); `_decal_plan_at(basis, center_uv, _ONFACE_FILL·max_cell, bitmap0, cols, rows, …)`. This
is byte-identical to `_plan_onface_texture` — SAME max-box centre, SAME 0.75 size — so a kept
candidate-0 leaves goldens unchanged. If it is `None` (unreadable today), the face is **omitted** and
NO further candidates are generated (omitted-today stays omitted; no rotate-to-rescue).

**Extra candidates** (only consumed when candidate 0 overlaps — see resolver), over these axes:

- **Orientation** ∈ {0°, 90°}. 0° uses `(cols, rows)`; 90° swaps the aspect to `(rows, cols)` and
  rotates the bitmap a quarter turn (`_rotate_bitmap_90` — new; rotates the 2-D boolean grid, swaps
  dims). 180°/270° give the same box aspect as 0°/90° so add no fit options — omitted. A 90° number
  reads sideways and its baseline UNDERLINE bar (the 6/9 cue, `_text_bitmap:768`) rotates with it into
  a side bar; the user accepted sideways reading as the price of a bigger fit, but the cue is weaker —
  noted so the docs/tests record it.
- **Size** — a geometric ladder from `_ONFACE_FILL·max_cell` DOWN toward the readability floor:
  `_ONFACE_FILL·max_cell · 0.8**k` for k = 0,1,2,… , keeping only sizes whose `_decal_plan_at`
  passes the `min_texel_px` gate (stop at the first that fails). This actually reaches the floor
  (fixing "shrink to separate down to the readability floor") instead of stopping at an arbitrary
  fraction. Per orientation and aspect-max.
- **Centre** — for each (orientation, size), `_feasible_centers(poly_uv, hw, hh)` with the box's
  half-extents. The eroded region at the 0.75 box is small, so these give a MODEST slide ("reposition
  slightly"); smaller sizes give a larger region (more dodge room).

Every candidate carries its `_DecalPlan` and `size_rank` = its cell (bigger better). Below-floor
candidates never appear (gate is in `_decal_plan_at`). Order: candidate 0, then the extras.

### Resolver — greedy, deterministic

```
obstacles = occupied snapshot            # point-actor markers (+ harmless legend rect), fixed
committed = []                           # bboxes of decals placed so far
order entries by (−primary_max_cell, brush_name, idx_str)   # biggest, hardest-to-move first; keys are real fields
for entry in order:
    cands = _onface_candidates(...)      # candidate 0 first; empty → omit (as today)
    if not cands: continue
    c0 = cands[0]
    if overlap_area(c0.bbox, obstacles + committed) == 0:
        pick = c0                         # GUARD: zero-overlap ⇒ keep today's placement verbatim
    else:
        pick argmin over cands of key(c):
            key = (overlap_area(c.bbox, obstacles + committed),   # 1: least screen overlap
                   −c.size_rank,                                  # 2: then biggest
                   candidate_index)                               # 3: stable
    commit pick.bbox; record (pick.plan, tint, opacity)
```

The explicit **candidate-0 guard** is what makes golden stability true: rotation/shrink/move are
reached ONLY when candidate 0 overlaps. `overlap_area` = summed axis-aligned rectangle-intersection
area in px² (with a bbox-disjoint early-out). Greedy, not global: bigger decals placed first claim
their spot; smaller ones dodge committed boxes. No randomness.

The lever **preference order (move → rotate → shrink) is EMERGENT from the key**, not a staged
try-move-else-rotate ladder: when a full-size move and a shrink both reach lower overlap, the
`−size_rank` tie-break keeps the larger (the move/rotate at full size); a smaller box wins only when
it yields STRICTLY less overlap. Implement the single argmin, not a fallback cascade — they differ.

Complexity O(N·C·M) (entries × candidates × obstacles). N is small on a full scene (the readability
gate drops most faces) but can grow when zoomed in; the bbox-disjoint early-out keeps the constant
low. If it ever bites, cap obstacles spatially — not needed for v1.

## Testing

Deterministic, stdlib-only — unit tests on the helpers + resolver, plus golden coverage.

- `_feasible_centers`: square/rectangle → non-empty, a returned centre lets the box fit
  (`_box_fits_2d`); triangle → off-centre; box larger than the face → empty list.
- `_rotate_bitmap_90`: a known asymmetric bitmap rotates correctly; `cols`/`rows` swap.
- Candidate generation — rotation fits bigger: a WIDE number on a TALL-narrow face → a 90° candidate
  has a strictly larger `size_rank` than any 0° candidate.
- Candidate 0 == today: `_onface_candidates(...)[0]` is byte-identical to `_plan_onface_texture(...)`
  for the same inputs (same tl/ex/ey/bitmap) — locks the golden-stability invariant.
- **Guard — no-overlap ⇒ unchanged:** an isolated decal (empty obstacle set) resolves to candidate 0
  EVEN WHEN a larger 90° candidate exists — asserts the guard beats the `−size_rank` tie-break.
- **Omitted-today stays omitted:** a face whose candidate 0 is `None` (below floor) yields no decal,
  even though a 90° upsized candidate would pass the floor.
- Resolver reduces decal-vs-decal overlap: two faces whose candidate-0 boxes overlap and a free spot
  exists → final total overlap **0**, both keep full `_ONFACE_FILL` size (moved, not shrunk).
- **Resolver dodges a point-actor MARKER:** seed a marker footprint into the obstacle set overlapping
  a decal's candidate-0 box → the committed decal moves/shrinks off it (final overlap < candidate-0).
- Resolver shrinks when it must: geometry where only a smaller box separates → chosen size <
  `_ONFACE_FILL`×max and final overlap < candidate-0; still readable (≥ floor).
- Shrink reaches the FLOOR: the size ladder produces a candidate whose projected texel is at/just
  above `min_texel_px` (not stopping at a fixed 0.45), and none below it.
- Determinism: resolving the same input twice is byte-identical.
- Goldens: only overlapping-decal fixtures change; re-baseline those and confirm (by eye + reviewer)
  the diff is decal shifts/rotations only. Isolated-decal goldens stay byte-identical.

## Docs to update on build

`usage.md` (decal behaviour: now nudges/rotates/shrinks to avoid overlap), `architecture.md` (THE ONE
RULE block + the new resolver), `decisions.md` (append the choice + rejected alternatives: global
optimizer, per-face-only shrink w/o move, cross-face moves), `board/done.md`.

## Amendments during build (2026-07-23, from Andrzej)

Folded into the code + `decisions.md` (2026-07-23 15:22 UTC) + `architecture.md`:

- **Rotation is floor/ceiling/cap-only** (`_is_horizontal_face`), not any tall/narrow face. A wall/slope
  number hangs by gravity and must not read sideways; a cap number is world-axis aligned (no up) so a
  quarter turn is orientation-neutral. (The spec above said "0° AND 90° on any face" — superseded.)
- **Same edge padding everywhere.** Every candidate keeps candidate 0's `_ONFACE_FILL` margin
  (≈16.666%/side): `_feasible_centers` is called with the PADDED box (`cell/fill`), so a slid/shrunk
  number is never flush. The full-size step is edge-tangent → single centre (the max centroid).
- **20% overlap tolerance, summed per layer.** `_DECAL_OVERLAP_TOLERANCE` = 0.20 of a decal's own area
  is left alone (guard keeps candidate 0 within tolerance → goldens stable, small overlaps read fine).
  `_rect_overlap_area` sums per obstacle, so N stacked decals count N× (dense pile-ups separated first).
  Applies uniformly to point-actor markers too (provisional reading of "between decals").
