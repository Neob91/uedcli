+++
priority = "p1"
kind = "debug"
summary = "mobile joystick doesn't move the camera; up/down buttons stay pressed forever once clicked"
+++

# Mobile joystick non-functional; up/down buttons stuck pressed

Owner report (2026-09-19), live testing of `mobile-3d-move-joystick-visual-design-pending`
(`aff6e8a4`): "the joystick is not functional, the up/down stays pressed forever once clicked."

Two distinct symptoms:

1. **The joystick drag doesn't move the camera at all.** Dragging the stick produces no perspective
   camera movement.
2. **The up/down buttons never release.** Clicking once leaves the button in a held-down state
   permanently, presumably continuously triggering the up/down move as if held, until something
   (reload?) clears it.

## Likely area

`web/src/scene/MoveJoystick.tsx` (the DOM overlay, pointer event handling) and
`web/src/scene/Viewport3D.tsx`'s new `TouchFlyInput` (the ref-based movement sink the joystick is
supposed to write into, sibling to the existing `FlyKeys`/keyboard path). The done writeup for the
original implementation
(`dev/docs/board/done/mobile-3d-move-joystick-visual-design-pending/overview.md`) notes its own
pointer-capture test coverage had to POLYFILL jsdom's missing `setPointerCapture`/
`releasePointerCapture` — a real, documented gap between what the unit tests exercised and a real
browser's actual pointer-event behavior. A stuck-pressed button is a classic symptom of a
`pointerup`/`pointercancel` handler never firing (e.g. missed because the pointer left the button's
bounds before release, or a capture that wasn't actually released in the real DOM the way the
polyfill assumed).

Also worth checking: whether `TouchFlyInput`'s ref is actually being read by the animation loop at
all, or whether it's wired but the joystick's own callback never writes to it (would explain
symptom 1 in isolation from symptom 2).

## Note

The implementation's own report was explicit that **no live browser verification was possible** in
that session (no runnable Chromium) — verified via unit tests and code review only. This bug is
likely exactly the kind of gap that gap leaves: real pointer-event edge cases a polyfilled jsdom test
can't catch. Fix needs real live testing (whether via a working sandbox browser, or the owner's own
live testing loop) before being called done, not another code-review-only pass.

## Repro

1. Load the app on a touch-capable device/emulated touch environment, perspective pane.
2. Drag the on-screen joystick — camera does not move.
3. Tap an up/down button once — it visually stays pressed indefinitely.
