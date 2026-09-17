+++
priority = "p1"
kind = "debug"
summary = "selecting Brush116:0 or Brush111:0 shows selected in the inspector but the poly draws no visible highlight"
+++

# poly highlight not visible for Brush116:0 / Brush111:0

Selecting poly `Brush116:0` or `Brush111:0` updates the inspector (it shows as selected there), but
the viewport draws no visible highlight on the poly itself — no way to tell by looking at the scene
that anything is selected.

## Repro

1. Select poly `Brush116:0` (or `Brush111:0`) by any means (click, or however the inspector allows).
2. Inspector shows it selected.
3. Viewport shows no highlight on that poly.

## Where to look

Whatever renders the per-poly selection highlight in `web/src/scene/` (surface highlight overlay,
likely near `SelectionHighlight.tsx`/`selectionBoxes.ts` per `GUI-PARITY.md`'s inventory). Suspect
something about these two specific polys — a degenerate/thin geometry case, a texture/material state
the highlight overlay doesn't handle, or a z-fighting/depth issue hiding the highlight underneath
other geometry. Check whether other polys on the same two brushes highlight fine, to narrow whether
it's poly-specific or brush-specific.

This is an implementation bug (state says selected, render doesn't show it) — no RE needed, straight
to build.
