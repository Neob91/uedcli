+++
priority = "p2"
kind = "implement"
summary = "DONE -- touch-only joystick + up/down buttons for mobile 3D move, Minimal HUD cluster design"
depends-on = ["mobile-and-touchpad-zoom-pan-support"]
+++

# Mobile 3D move joystick — implemented

Built after the owner reviewed 4 visual-design mockup options and picked "Minimal HUD cluster"
(option 4): a thin ring + dot for the stick (not a solid filled base), compact button chips for
up/down, grouped into one small low-profile corner cluster, `--accent` purple. **One change from the
reviewed mockup**: the owner asked for up/down CHEVRON icons (▲/▼) instead of the mockup's +/-
symbols, matching the plain-unicode-glyph convention this app's toolbar already uses (QuadLayout's
sidebar-collapse toggle: ◀/▶).

- `web/src/scene/touchCapability.ts` — `isTouchCapableDevice()`/`resolveTouchCapable()`, a capability
  check (not a viewport-width breakpoint like `useCollapsiblePanel.ts`'s) so a touch-capable laptop
  with a keyboard still gets the control.
- `web/src/scene/joystick.ts` — `joystickVector(dx, dy, maxRadius)`, pure drag-offset-to-analog-
  forward/right math, clamped to the ring radius.
- `web/src/scene/MoveJoystick.tsx` — the DOM overlay (ring+dot, two button chips), touch-gated,
  reporting `{forward,right}`/`up` via callbacks.
- `web/src/scene/Viewport3D.tsx` — a new `TouchFlyInput` component (mirrors the existing `FlyKeys`
  exactly: same `flyMove`/`FLY_SPEED_UU_PER_SEC`, same per-frame `useFrame` application), fed by a
  separate ref the joystick's callbacks write into — fully independent of `FlyKeys`' own `held` key
  set, so touch input can never interfere with keyboard input. Rendered only in the perspective pane
  (`MoveJoystick` is never mounted in `OrthoViewport.tsx`), positioned bottom-left of the pane — the
  one corner none of `QuadLayout`'s other per-pane overlays uses.
- `web/src/index.css` — `.move-joystick-controls`/`.move-joystick-base`/`.move-joystick-dot`/
  `.move-vertical-buttons`/`.move-vertical-btn`.

Verification: 24 new unit/component tests (`joystick.test.ts`, `touchCapability.test.ts`,
`MoveJoystick.test.tsx` — touch gating via a mocked `touchCapability` module, drag-to-vector math via
real `fireEvent.pointerDown/Move/Up` sequences with jsdom's missing `setPointerCapture` polyfilled,
up/down button hold/release). Full frontend suite green (410 tests, 46 files) and `tsc -b` unchanged
(same 7 pre-existing errors, none touching the new/edited files). No live-browser screenshot: this
sandbox has no runnable Chromium (same documented gap `GUI-PARITY.md` hits repeatedly) — verified via
unit tests + code review instead, per the task's own fallback instruction.
