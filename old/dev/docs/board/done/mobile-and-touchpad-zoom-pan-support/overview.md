+++
priority = "p1"
kind = "implement"
summary = "DONE -- mobile/touchpad nav, collapsible sidebars, toolbar overlap, Grid consolidation; joystick deferred separately"
+++

# Mobile and touchpad support for viewport navigation

Shipped on `gui-staging-20260918`: `b805e7d8`, `226a7ca3` (a review-found toolbar-wrap follow-up).
Five of six symptoms landed, live-verified with real headless-Chromium interaction (touch events via
CDP, synthetic ctrl+wheel events, sidebar toggling across fresh browser contexts, toolbar
bounding-box checks) by both the implementer and an independent review pass:

1. Ortho pinch-zoom/pan — `OrthoViewport.tsx` now handles touch the same way `Viewport3D.tsx` did.
2. **Not done** — the mobile 3D move joystick. Deferred mid-implementation: the owner wants to
   review visual-design options before any code for it (including input handling) is written.
   Tracked separately: `mobile-3d-move-joystick-visual-design-pending`.
3. Collapsible sidebars — `web/src/layout/useCollapsiblePanel.ts`, 768px responsive default,
   localStorage override once manually toggled.
4. Trackpad ctrl+scroll — `dragGesture.ts`'s wheel handler moved to a native non-passive listener
   (React's synthetic `onWheel` is passive; `preventDefault()` inside it was a silent no-op).
5. Toolbar overlap — Movers/Radii/Grid moved into `.quad-toolbar`, a child of `.quad-layout` instead
   of individually `position: absolute` against `.quad-layout-root` (which spans the org panel).
   Review found `.quad-toolbar` itself overflowed off-screen in a ~768-865px width band; fixed with
   `flex-wrap` in `226a7ca3`.
6. Grid consolidation — `Grid: on/off` + `Grid Size` merged into one checkbox+dropdown, dropdown
   stays visible-but-disabled when off.

`web/`'s vitest suite (40 files / 354 tests) green throughout.
