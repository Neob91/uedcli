+++
priority = "p2"
kind = "implement"
summary = "Brush selection click modifier fixed: VIEWPORT-gated (3D always Shift+LMB, 2D never), correcting this item's own mode-gated guess; surface highlight (part 1) also shipped"
+++

# Brush selection click modifier fixed: VIEWPORT-gated (3D always Shift+LMB, 2D never), correcting this item's own mode-gated guess; surface highlight (part 1) also shipped

Part 2 (pivot/vertex markers, thicker outline) shipped earlier this session. This closes part 1.

Owner ruling (2026-09-15) corrected this item's own mode-gated guess: the real rule is
**viewport-gated**, not shading-mode-gated. The 3D perspective pane needs Shift+LMB to select a
brush in EVERY mode (wireframe included) because plain LMB-drag there is camera-fly; the 2D ortho
panes need no modifier in any mode (plain LMB-drag there is select/marquee) — confirmed by
`dev/docs/unrealed/leveldesign/kb/editor-ui.md`'s existing "2D/3D navigation" entry. Point actors are
unaffected (always plain-tap-selectable). Implemented as `canSelectBrushTap(isPerspectivePane,
shiftKey)` in `web/src/scene/selection.ts`, wired into `Viewport3D.tsx`/`OrthoViewport.tsx`'s
`performTapSelect`; `dragGesture.ts`'s `onTap` now threads `shiftKey` end to end.

Also shipped a selected brush's surface "lighting up" (a separate live-tested finding, folded into
the same change): `SelectionHighlight.tsx` + `selectedTriangles.ts` draw an additive-white overlay
over just the selected brush's own triangles, in both panes.
