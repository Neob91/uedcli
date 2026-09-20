+++
priority = "p?"
kind = "debug"
summary = "GUI actor-move: final-review-wave residual papercuts"
depends-on = ["gui-p2-actor-translate-ctrl-drag"]
+++

# GUI actor-move: final-review-wave residual papercuts

Five small, non-blocking findings from the scoped re-review of `gui-p2-actor-translate-ctrl-drag`'s
final fix wave (the wave that fixed the Ctrl-click-threshold and Discard-doesn't-revert Criticals).
None block merge; grouped here since they're all small and from the same review pass. Pick off
individually.

## 1. Perspective: a purely vertical Ctrl+LMB drag stages a no-op move

`web/src/scene/Viewport3D.tsx` sets `dragMovedRef` unconditionally once the tap-vs-drag threshold
is crossed (inside `if (frame)`), but `moveAlongAxis` only uses `dx` — so a clean vertical
drag (`hypot(dx,dy) > 4px` but `dx` sums to exactly 0 across the gesture) computes a `[0,0,0]`
delta, still counts as "moved," and POSTs a real no-op stage. Benign in effect (nothing actually
moves) but is the same "an unintended gesture stages something" class the Ctrl-click-jitter
Critical was about. Fix: also gate `dragMovedRef`/staging on the computed delta being non-zero, not
just on crossing the tap threshold.

## 2. Save-success snaps staged actors backward for the reload's duration

`web/src/App.tsx`'s `onSaved` clears `stagedOffsets` immediately, before the post-save `/load`
refetch lands — so a staged (moved) actor visibly jumps back to its pre-move trunk position, then
forward again once the reload completes. On a large level this could be a couple of seconds of
visible flicker. Fix: defer the `stagedOffsets` clear into `runBuildAction`'s success continuation
instead of clearing it eagerly.

## 3. `accept-load` on a Load conflict clears the visual offset but not the Save-bar's staged count

`web/src/App.tsx`'s Load-conflict `accept-load` path correctly clears the moved actor's visual
staged-offset, but doesn't also remove it from `stagedNames` — so the Save bar can keep showing "1
staged move" for an actor whose stage the backend already dropped. Fix: call `setStagedNames`
alongside the offset-clearing in that same handler.

## 4. A failed `postStage`'s revert can restore the wrong snapshot under rapid re-drag

`Viewport3D.tsx`/`OrthoViewport.tsx`'s `postStage(...).catch(...)` reverts to a `preGestureOffsetsRef`
snapshot taken at gesture-start — but if a SECOND drag gesture starts (same pane or a different one)
before the first gesture's failed `postStage` promise rejects, the revert restores a stale snapshot
instead of the failed gesture's own true prior state, silently no-op'ing the revert or clobbering a
different pane's freshly-staged, successfully-posted move. Narrow (needs a failing stage plus a fast
follow-up drag) and non-corrupting (nothing server-side is affected, only the client's visual
state can end up momentarily wrong). Fix shape not obvious without more design thought — a
generation counter per gesture, keyed revert, or similar.

## 5. Verify drag performance on a large level (not a confirmed bug — needs a real check)

Lifting `stagedOffsets` to `App.tsx` (fixing the Discard-doesn't-revert Critical, and enabling
cross-pane live preview as a bonus) means every pointer-move frame of a drag now re-renders `App`,
`QuadLayout`, and all four panes (each recomputing `applyStagedOffsets` over its whole actor list),
where before only the dragging pane's own local state updated. `applyStagedOffset` returns the same
object reference for an unmoved actor, so the per-actor cost should be small, but this hasn't been
verified against an actual large level's actor count — do a real in-app drag test on one of the
bigger fixture levels (e.g. UNATCO) before treating drag smoothness as settled.

## 6. Save can silently no-op its own post-save refresh if it lands during a Rebuild

`App.tsx`'s `onSaved` routes through `runBuildAction`, which silently no-ops if `busy` is already
true (e.g. a Rebuild is in flight) — a pre-existing guard, but the Save button isn't itself gated on
`busy`, so this window is reachable: Save completes trunk-side, the stale-view-prevention refresh
this whole fix wave was for doesn't fire, and the client keeps the pre-save view. Fix shape: either
gate the Save button on `busy` (matching how other build actions are presumably already gated,
worth checking), or don't let `onSaved`'s refresh silently no-op.

## Refs

Board item this was found reviewing: `gui-p2-actor-translate-ctrl-drag`.
