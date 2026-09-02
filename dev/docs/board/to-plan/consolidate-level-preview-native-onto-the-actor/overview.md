+++
priority = "p2"
kind = "implement"
summary = "Consolidate `level photo --native` onto the `actor diagram` renderer"
+++

# Consolidate `level photo --native` onto the `actor diagram` renderer

Owner intent (2026-08-05): the two offline renderers should become one. **Keep `actor diagram`'s
logic (`preview.py` + the faithful `build_geometry_bspcsg` CSG core); retire `level photo
--native`'s logic (`preview_native.py`'s Rust `render.rs` rasterizer + the default `build_geometry`
core), which is buggy.** Full spec written (`spec.md`), all owner rulings folded (offline flag = `--offline`); the spike
`2026-08-05-perspective-in-preview-py` resolved both gated points (perspective fits `preview.py` as a
localized addition; whole-level pure-Python raster is low single-digit seconds). No open questions —
ready to plan.

## The catch the spec has to resolve

The two renderers are not the same shape:

- `actor diagram` (`preview.py`) is an **orthographic schematic** — top/front/side/iso panes, no
  camera. It uses the faithful CSG core.
- `level photo --native` (`preview_native.py`) renders **freely-posed PERSPECTIVE** whole-level
  stills from the shared SHOT grammar (`at:/rot:/look:/orbit:`, `--fov`). It uses the default CSG
  core (the buggy one) and the Rust rasterizer.

So "keep actor diagram's logic" cannot be a straight swap: `preview.py` has no perspective camera and
no SHOT-pose projection. **Owner decision (2026-08-05): add a perspective camera to `preview.py` and
wire `level photo --native` to the same render path `actor diagram` uses — one shared renderer.**
Ship pure-Python (a Rust rasterizer is a planned follow-on); a missing texture batch-reports then
exits 2. See `spec.md` "Decisions".

## Why this is wanted

Every `--native` render bug is in the retired-candidate code, and several are already *fixed* on the
`actor diagram` side (concave fill, missing-texture refusal, the faithful doorway CSG). Consolidating
closes the divergence and the maintenance of a second rasterizer/CSG core.

## Bug items this would subsume or moot (verify each on build)

- `native-preview-mis-renders-overlapping` (p1) — doorway magenta; the default core's defect that
  `build_geometry_bspcsg` already avoids.
- `level-preview-native-fills-polygons-by-triangle` (p2) — triangle-fan bleed on concave;
  `preview.py`'s scanline already handles concave.
- `level-preview-native-checkerboards` (p2) — missing-texture warn-and-continue; `preview.py` exits 2
  per `conventions.md`.
- `level-preview-native-renders-no-revolve-brush` (p2) — revolve brushes absent under `--native`.
- `native-preview-black-speckles-on-tower-roof` (p3) — coplanar z-fight in the Rust rasterizer.
- `native-preview-post-build-review-findings` (p2) — the render.rs/preview_native crash + unwrapped-
  error findings; most are mooted if that code is retired.
- `native-preview-perf-an-8-shot-castle-batch` (p3) — perf is dominated by the CSG carve, not the
  rasterizer; note whether consolidation helps or is orthogonal.

## Related, not subsumed

- `actor-preview-parity-direction-home` (owner-question) — the `direction/` home for actor-preview
  render rules; a consolidation would extend it to cover the offline `level photo` tier.
- `actor-preview-faces-textured-does-not-sort-the` — CSG-order sorting; applies to any shared solve.
- `actor-preview-bspcsg-starts-from-an-empty-world` — the shared core's empty-vs-solid seed.

## Note on the home

Searched the board for a pre-existing owner-filed consolidation item and found none; this item is the
home. If the owner had another in mind, fold this into it (`git mv`, merge the text).
