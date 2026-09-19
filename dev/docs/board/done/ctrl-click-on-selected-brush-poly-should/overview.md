+++
priority = "p1"
kind = "implement"
summary = "REVERTED same-day: owner clarified Ctrl+LMB must never deselect via a poly click, only Shift+LMB does — see ctrl-poly-deselect-should-be-wireframe-only-not"
+++

# ctrl-click-on-selected-brush-poly-should-deselect — REVERTED

Landed as described below, then reverted the same day (2026-09-19) once the owner clarified: Ctrl
deselect is wireframe-outline-click only, never a poly click — poly-click select/deselect is
Shift+LMB only. See `ctrl-poly-deselect-should-be-wireframe-only-not` for the revert and the
corrected rule.

Original (reverted) change: `resolveTapAction` (`web/src/scene/selection.ts`) gained a
`selectedActorNames` param: a Ctrl+click (no Shift) on a poly whose owning actor is already
actor-selected resolved to `select-actor` (additive) instead of surface-select. Threaded through
`tapSelect.ts`'s `TapSelectParams`/`resolveTapSelect` and both call sites.
