+++
priority = "p1"
kind = "implement"
summary = "FIXED: Ctrl+LMB on an already actor-selected brush's poly deselects that one actor instead of toggling poly/surface selection"
+++

# ctrl-click-on-selected-brush-poly-should-deselect — FIXED

`resolveTapAction` (`web/src/scene/selection.ts`) gained a `selectedActorNames` param: a Ctrl+click
(no Shift) on a poly whose owning actor is already actor-selected now resolves to `select-actor`
(additive), the same deselect `toggleSelection` already does for Shift+click. Threaded through
`tapSelect.ts`'s `TapSelectParams`/`resolveTapSelect` and both call sites (`Viewport3D.tsx`,
`OrthoViewport.tsx`, both already had `selectedNames` as a prop). Unaffected: Ctrl+click on an
unselected actor's poly, plain click on any poly, Shift+click, wireframe mode, line/AABB-fallback
hits. Regression tests in `selection.test.ts`/`tapSelect.test.ts`.
