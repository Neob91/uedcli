+++
priority = "p1"
kind = "implement"
summary = "Ctrl+LMB on an already actor-selected brush's poly should deselect that one actor, not toggle poly/surface selection"
+++

# ctrl-click-on-selected-brush-poly-should-deselect

Owner report: with multiple brushes selected (in a non-wireframe/solid shading mode), Ctrl+LMB on
one of the already-selected brushes' polys does not deselect it — it toggles a poly/surface
highlight instead, leaving the brush actor selected.

## Current behavior (by design, not a regression)

`web/src/scene/selection.ts`'s `resolveTapAction`, for a genuine poly hit in a non-wireframe mode:

```ts
if (polyIndex != null && mode !== 'wireframe') {
  if (shiftKey) return { kind: 'select-actor', name: actor.name, additive: true }
  return { kind: 'select-surface', actor: actor.name, polyIndex, additive }
}
```

Shift+click on a poly = whole-actor select, always additive (so Shift-clicking an ALREADY
actor-selected brush does toggle it off — `toggleSelection`'s additive branch removes if present).
Plain/Ctrl+click on a poly = surface/texture select, with `additive` (Ctrl) toggling POLY
membership, never actor membership — this is the owner-ruled convention from
`shift-modifier-convention-broken-for-poly-and` (2026-09-17): "Shift is only to select BRUSHES ...
by clicking on its VISIBLE POLY."

So today, deselecting one of several selected brushes via a poly click needs Shift+LMB, not
Ctrl+LMB — Ctrl+LMB on a poly never touches actor selection at all, regardless of whether that
actor is already selected.

## Owner ruling (2026-09-19) — this changes

The owner considers this unintuitive and wants a fix: **Ctrl+LMB clicking on a brush that is
CURRENTLY actor-selected must deselect just that one brush**, even when clicking lands on a poly
(non-wireframe mode) and even with several other brushes still selected. Exact words: "I thought
it's obvious that ctrl+LMB on a selected brush should deselect it. With multiple selected brushes,
only the one clicked should be deselected."

Scope: this only changes behavior when the clicked poly's OWNING ACTOR is already in the actor
selection set. Ctrl+click on a poly of an actor that is NOT actor-selected keeps today's behavior
(toggle poly/surface selection — texture multiselect). Plain click (no Ctrl, no Shift) on a poly
is unaffected either way (still surface-select, replacing). Shift+click keeps its existing
always-additive actor-select behavior, untouched.

## Implementation note

`resolveTapAction` (`selection.ts`) is a pure function with no access to the current selection
state — it takes `rawHit`/`mode`/`shiftKey`/`additive` only. This fix needs the current set of
actor-selected names threaded in (a new parameter), so it can check "is `actor.name` already in
the selection" before falling into the surface-select branch on a Ctrl+click. Thread it through
`tapSelect.ts`'s `resolveTapSelect`/`TapSelectParams` and both call sites (`Viewport3D.tsx`,
`OrthoViewport.tsx`), from `App.tsx`'s existing `selectedNames` state.

No RE needed — this is a UX/convention ruling, not a UED22-parity claim.
