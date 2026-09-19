+++
priority = "p1"
kind = "debug"
summary = "mobile joystick doesn't move the camera; up/down buttons stay pressed forever once clicked"
+++

# Mobile joystick non-functional; up/down buttons stuck pressed

Owner report (2026-09-19), live testing of `mobile-3d-move-joystick-visual-design-pending`
(`aff6e8a4`): "the joystick is not functional, the up/down stays pressed forever once clicked."

## Root cause (one bug, both symptoms)

`MoveJoystick.tsx`'s pointer handlers (`onStickPointerDown`/`onStickPointerMove`/`endStickDrag`,
`onVerticalPointerDown`/`onVerticalPointerUp`) never called `stopPropagation()`. `Viewport3D.tsx`'s
own container div has a touch `onPointerDown`/`onPointerMove` handler (single-finger look-rotation,
two-finger pan/zoom) that unconditionally calls `e.currentTarget.setPointerCapture(e.pointerId)` on
ITSELF for any touch pointerdown. Since `MoveJoystick` is rendered as a DOM child of that same
container, a touch starting on the stick or a button still bubbles up into the container's handler
after the joystick element captures it -- and per the Pointer Events spec, calling
`setPointerCapture` on a different element TRANSFERS capture to it. So the container immediately
steals capture back from the joystick, and every subsequent move/up/cancel for that pointer routes
to the container instead:

- the stick never sees its own `pointermove` again -- the drag is instead read by the container as a
  one-finger camera look-rotation, which recomputes the whole pose from a drag-start snapshot each
  move and so also freezes `position` (masking the joystick's own `flyMove` translate, which also
  never got its own move events to react to). Symptom 1: "no camera movement."
- the up/down buttons never see their own `pointerup`/`pointercancel` -- so `onVerticalChange(0)` is
  never called, and the button (and the touch-fly vertical input) stays "pressed" forever. Symptom 2.

Fix: `stopPropagation()` at the top of all five handlers, so the touch never reaches the container.

## Verification

Real browser, not unit tests alone -- the previous implementation's report flagged exactly this gap
(jsdom's polyfilled `setPointerCapture` can't reproduce a capture-transfer/propagation bug like this
one). This session got a real Chromium running:

- `~/.cache/ms-playwright/chromium_headless_shell-1243` was already cached but missing 14 shared
  libraries (`libglib-2.0.so.0`, `libatk-1.0.so.0`, `libgbm.so.1`, etc. -- no root, `apt-get update`
  denied). Fetched their `.deb`s directly via a user-writable `apt-get -o Dir::State::lists=...`
  config (no root needed for `update`/`download`), extracted with `dpkg-deb -x` into a scratch
  prefix, and pointed `LD_LIBRARY_PATH` at it -- `ldd` then resolved cleanly.
- Installed `playwright-core` (no browser download) and drove the cached binary directly via
  `executablePath`, with `--use-angle=swiftshader --enable-unsafe-swiftshader` for real WebGL
  (`chrome-headless-shell` disables GPU raster by default; modern Chromium needs the explicit
  unsafe-swiftshader flag for software WebGL in headless mode).
- Rendered the REAL `Viewport3D` + `MoveJoystick` (not a reimplementation) via a temporary Vite entry
  (`hasTouch: true` context, hit-testable geometry so a camera move is observable), and drove it with
  real touch gestures via CDP `Input.dispatchTouchEvent` (touchStart/touchMove.../touchEnd or
  touchCancel) -- genuine browser-synthesized `PointerEvent`s, not `fireEvent`-mocked ones. A
  temporary `window.__debugPose` hook (removed before merge) exposed the live camera pose per frame.

Measured, unfixed code: dragging the stick left the camera `position` frozen at its start value while
`pitch`/`yaw` rotated instead (the hijacked look-gesture); pressing the up button and releasing via
either a real `touchend` OR a real `touchcancel` left `position.z` climbing forever, never stopping.
Measured, fixed code (same script, same gestures): the stick drag moves `position` (and leaves
pitch/yaw untouched); releasing (touchend) stops the movement immediately, confirmed stable across a
follow-up wait; the up button's vertical movement stops after both touchend AND touchcancel,
confirmed stable across a follow-up wait in both cases.

Also added a committed regression, `MoveJoystick.test.tsx`: renders `MoveJoystick` inside a wrapper
`div` that mimics `Viewport3D`'s own capturing touch handler, and asserts the wrapper's handler is
never invoked for a stick drag or a button press (this needs no real browser -- it tests event
propagation, which jsdom implements correctly, unlike pointer-capture semantics). Confirmed this test
fails against the pre-fix code and passes with the fix.

Full frontend suite (`vitest run`): 416/416 passing, no regressions.

## Files

- `web/src/scene/MoveJoystick.tsx` -- the fix (`stopPropagation()` in all five pointer handlers).
- `web/src/scene/MoveJoystick.test.tsx` -- new regression tests (propagation to an ancestor
  container).

## Follow-on (2026-09-19): the fix above broke mouse navigation

Owner report: "did the joystick fix break normal mouse navigation in the 3d view?" Yes. The
`stopPropagation()` fix above had no `pointerType` check -- it fired for ANY pointer, mouse
included. `touchCapability.ts`'s `isTouchCapableDevice` (which gates whether the joystick renders at
all) is a feature-detection check (`'ontouchstart' in window` / `navigator.maxTouchPoints > 0`) that
false-positives on a hybrid touchscreen laptop that also has a mouse -- an explicit, intentional
design constraint from the original board item (`mobile-3d-move-joystick-visual-design-pending`), not
a bug on its own. But once the cluster renders there, a MOUSE click/drag landing in its corner of the
perspective pane got fully swallowed: `stopPropagation()` stopped it from reaching
`Viewport3D.tsx`'s own `onPointerDown`/`onPointerMove`/`onPointerUp`, which already correctly gates
its OWN touch-specific capture-stealing logic on `e.pointerType === 'touch'` and falls through to
normal `mouseDrag` handling for everything else -- so a mouse event was never reaching that fall-through at all.

Fix: every one of `MoveJoystick.tsx`'s five pointer handlers now starts with
`if (e.pointerType !== 'touch') return`, mirroring `Viewport3D.tsx`'s existing convention exactly.
A non-touch pointer is now a complete no-op -- no `stopPropagation`, no `setPointerCapture`, no
state change -- so it passes through untouched to the container's own mouse-drag handling. The
`stopPropagation()` calls themselves are unchanged and still fire for real touch input.

Verified with the same real-Chromium recipe as the original fix (`chromium_headless_shell-1243`, its
14 missing shared libraries fetched as user-writable `.deb` extracts via a scratch `apt.conf` +
`dpkg-deb -x`, no root), via a temporary Vite entry (`verifyJoystick.tsx`, not committed) mounting
the REAL `MoveJoystick` inside a container mimicking `Viewport3D.tsx`'s own capturing handler, forcing
`navigator.maxTouchPoints` so the cluster renders on a hybrid device. Real CDP-dispatched events, both
pointer types, before pushing:

| Gesture | Container saw it? | Joystick reacted? |
|---|---|---|
| real TOUCH drag on stick | no (0 calls) | yes -- `{forward:1,right:0}` then `{forward:0,right:0}` |
| real TOUCH press+release on up button | no (0 calls) | yes -- `[1, 0]` |
| real MOUSE drag on stick | yes (down/move/up all fired) | no -- empty, joystick ignored it |
| real MOUSE press+release on up button | yes (down/up fired) | no -- empty, joystick ignored it |

Touch behavior is unchanged (matches the original fix's own verification table); mouse now passes
through fully, confirming the regression is closed. Unit tests updated
(`MoveJoystick.test.tsx`): every existing touch-behavior test now passes `pointerType: 'touch'`
explicitly (jsdom's synthetic `PointerEvent` defaults `pointerType` to `''`, not `'mouse'`, so this
was needed to keep exercising the touch path); two new tests
(`MoveJoystick ignores non-touch pointers entirely`) drive `pointerType: 'mouse'` and assert the
event reaches an ancestor container and `setPointerCapture` is never called. Full frontend suite:
424/424 passing.

### Files (follow-on)

- `web/src/scene/MoveJoystick.tsx` -- the `pointerType` gate on all five handlers.
- `web/src/scene/MoveJoystick.test.tsx` -- `pointerType: 'touch'` added to existing tests; new
  `MoveJoystick ignores non-touch pointers entirely` describe block.
