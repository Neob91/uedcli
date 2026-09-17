+++
priority = "p1"
kind = "debug"
summary = "clicking a selected poly does not deselect it; should toggle off when it's the sole selection"
+++

# click on a selected poly does not deselect it

Clicking a poly that is already selected (no modifier keys) should deselect it. Today it stays
selected — clicking does nothing.

When multiple polys are selected and one of the selected ones is clicked, the existing behavior is
correct: it becomes the sole selection (the others drop out). Only the single-selected-poly-stays-
selected case is the bug — a plain click on the ONE currently-selected poly must clear the selection
entirely, not leave it selected.

## Repro

1. Click a poly (e.g. a surface on any brush) to select it.
2. Click the same poly again, no modifiers.
3. Expected: nothing selected. Actual: the poly stays selected.

## Where to look

`web/src/scene/` — `tapSelect.ts`/`selection.ts` own the click-to-select logic this campaign
(`GUI-PARITY.md`) already tracks. This is a pure web-editor interaction convention (click-to-toggle),
not a UED22-fidelity question — no RE needed, straight to build.
