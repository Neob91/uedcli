+++
priority = "p2"
kind = "debug"
summary = "the brush local-origin (PrePivot) vertex dot only draws on the primary selected brush, not every selected brush"
+++

# vertex-local-origin-dot-only-shows-on-primary

Owner report: selecting multiple brushes, only the LAST selected brush shows the small
brush-colored vertex-like square dot (not the red pivot cross — the PrePivot/local-origin dot).

## Root cause

`web/src/scene/SelectionMarkers.tsx`'s `SelectionMarkers` component:

- Per-poly-vertex dots correctly loop over EVERY selected brush (`selectedBrushes.map(...)`).
- The local-origin dot is gated `actor.name === primaryName` — drawn for at most one actor, the
  most-recently-selected (`selectionSet.ts`'s `primarySelection`).

The component's own doc comment justifies this by pointing at the separate GLOBAL pivot CROSS
work (GUI-PARITY.md "Pivot-cross ... Part 4"), but that finding is about a DIFFERENT marker — the
one red crosshair from `GPivotLocation`, which real UED22 genuinely draws only once per selection.
The local-origin square dot is a different thing: UED22's `DrawLevelBrush` draws it once PER
SELECTED BRUSH, in that brush's own `WireColor`, alongside that brush's own vertex dots — this
project's own reference implementation already encodes that distinction correctly:
`uedcli/preview.py`'s `_scene_geometry` (~line 1866-1874) draws the "origin" dot for every
`is_hi_actor` (every highlighted/selected brush), inside the same per-actor loop as the vertex
dots, with an explicit comment: "UED22's 'origin' draw (`DrawLevelBrush`): the world position of
the brush's LOCAL coordinate origin ... NOT the true pivot (see below)". `hi_pivot_dots` (the true
`GPivotShown` single pivot) is a SEPARATE accumulator.

So `primaryName`-gating the local-origin dot was a mistake — conflating the per-brush origin
marker with the single global pivot cross it sits next to.

## Fix

Owner confirmed (2026-09-19): drop the `actor.name === primaryName` gate; render the local-origin
dot for every selected brush, same as the per-vertex dots. The global `PivotMarker` (the one red
cross, `pivotAnchor`-anchored) is untouched — it's a genuinely different marker and stays as is.

No RE needed — this is an internal-consistency bug against this project's own already-verified
`preview.py` convention, not a new UED22 claim.
