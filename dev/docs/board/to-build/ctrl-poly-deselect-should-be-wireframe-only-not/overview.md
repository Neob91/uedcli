+++
priority = "p1"
kind = "implement"
summary = "revert the ctrl-click-on-selected-brush-poly-should-deselect fix: Ctrl on a poly must never deselect, only Shift does"
depends-on = ["ctrl-click-on-selected-brush-poly-should-deselect"]
+++

# ctrl-poly-deselect-should-be-wireframe-only-not

## Correction to a just-merged fix

`ctrl-click-on-selected-brush-poly-should-deselect` (merged to master `11a1f357`, same day) added:
in a non-wireframe (solid/textured) shading mode, a Ctrl+click (no Shift) on a poly whose owning
actor is already actor-selected now resolves to a deselect of that actor, instead of the existing
surface/texture-select behavior.

The owner has now corrected that: **Ctrl+LMB must never deselect a brush by clicking its POLY, in
any mode. Selecting/deselecting a brush via a poly click is Shift+LMB only.** Ctrl+LMB deselect is
permitted only by clicking the brush's WIREFRAME — which, for an ordinary (non-Mover) brush, only
exists as a click target in wireframe shading mode at all (`tapSelect.ts`'s `brushObjects` is `[]`
outside wireframe mode, an earlier, unrelated owner ruling — "never AABB/interior-select a brush in
wireframe/ortho views, only its own outline lines"). In wireframe mode, a plain/Ctrl+click on a
brush's own outline line already resolves through `resolveTapAction`'s `isLineHit` branch
(`{ kind: 'select-actor', name: actor.name, additive }`) — Ctrl held there already toggles
(deselects if already selected) via `toggleSelection`'s additive branch. That path is untouched by
either fix and needs no change — it already does exactly what the owner wants, and always has.

So the fix that landed as `ctrl-click-on-selected-brush-poly-should-deselect` was the wrong shape:
it created a SECOND way to Ctrl-deselect a brush (via its poly) that must not exist. The correction
is a straight revert of that change, not a redesign.

## Exact revert

`git diff` of `master`'s `aa2e4287..11a1f357` (or `git log -p` on that commit) is the full scope. In
short:

- `web/src/scene/selection.ts`'s `resolveTapAction`: remove the line
  `if (additive && selectedActorNames.has(actor.name)) return { kind: 'select-actor', name: actor.name, additive: true }`
  (and the `selectedActorNames` parameter, and the doc-comment paragraph describing this third
  fork) — restoring the poly branch to exactly: `shiftKey` -> actor-select (additive); else ->
  surface-select, with NO dependency on current selection state or Ctrl.
- `web/src/scene/tapSelect.ts`: remove `TapSelectParams.selectedNames` and its use in the
  `resolveTapAction(...)` call — restore the prior 4-arg call.
- `web/src/scene/Viewport3D.tsx` / `web/src/scene/OrthoViewport.tsx`: remove the `selectedNames`
  argument threaded into their `resolveTapSelect({...})` calls and its now-unneeded appearance in
  the `useCallback` dependency arrays (both already received `selectedNames` as a prop before this
  fix, for other reasons — do NOT remove the prop itself, only the newly-added use of it in the
  `resolveTapSelect` call).
- `web/src/scene/selection.test.ts` / `web/src/scene/tapSelect.test.ts`: remove the 4-5 test cases
  added for the reverted behavior. ADD a regression test locking in the CORRECTED rule instead:
  Ctrl+click (additive=true, no shift) on a poly whose actor IS already in the actor-selection set
  must still resolve to `select-surface` (NOT `select-actor`) — this is the exact scenario the
  reverted fix changed, and it must now assert the OPPOSITE of what it asserted before. Also add/
  confirm a test that a wireframe-mode Ctrl+click on an already-selected brush's outline line DOES
  resolve to an actor deselect (`isLineHit` branch, additive toggle) — this path was never broken,
  but pin it explicitly so a future change doesn't accidentally couple the two decisions again.

## Board bookkeeping

`ctrl-click-on-selected-brush-poly-should-deselect` in `done/` should get a short follow-up note
(not rewritten wholesale — CLAUDE.md's "keep it short" + the board's own "trim to a one-line record"
convention) pointing at this item, so a reader of `done/` doesn't think that fix is still live.
