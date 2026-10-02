+++
priority = "p2"
kind = "implement"
summary = "done: UED22 draws ONE pivot cross, on the actor most recently the sole selection, shown when that actor has bEdShouldSnap (every brush does) -- GUI now matches"
+++

# Pivot cross visibility and anchor -- resolved and implemented (2026-09-18)

Root-caused against our own `uned/UED22/Editor.dll` and confirmed by a live UED22 capture. The full
trace -- all seven `SetPivot` call sites, the draw-site gate, the marker's measured shape and colour,
the live-capture table, and the two deliberate divergences -- lives in `GUI-PARITY.md` "Pivot-cross
multi-select rendering ... Part 4".

`GPivotShown = (SnapCount > 0) || (Count > 1)`, computed only inside `SetPivot` and latched between
calls; `SnapCount` counts selected actors with `bEdShouldSnap`, which `Engine.Brush`'s class defaults
set and no point actor's do. So a lone selected brush DOES show the cross (this item's original claim
that UED22 hides it for a single selection was wrong for brushes, right for point actors), there is
only ever one cross, and it sits on the actor most recently the sole selection.

Built in `web/src/scene/SelectionMarkers.tsx` + `selectionSet.ts`'s `pivotAnchor`; regressions in
`SelectionMarkers.test.tsx` and `selectionSet.test.ts`.
