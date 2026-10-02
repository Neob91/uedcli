+++
priority = "p1"
kind = "debug"
summary = "DONE -- fixed a real per-frame cost in RadiiOverlays' camera-facing circles (doubled by sound radius); CSS overflow fix and a per-frame React re-render both ruled out"
+++

# 2D/3D mouse nav jitter

Owner report (2026-09-19): "2D mouse nav is broken too - jittery as hell" (ortho panes). A related
report came in during triage: in the perspective pane, "I click the view, and it jumps ONCE, and
then nothing." Two commits landed shortly before both reports: `68fb02ed` (sidebar/page CSS
overflow-x fix) and `0eba38c4` (sound-radius overlay, reusing the light-radius camera-facing-circle
mechanism).

## What was checked, and the result

**CSS resize-loop (candidate 1): ruled out.** Instrumented a `ResizeObserver` on every pane's
`<canvas>` and watched for repeated fire during idle time and during a drag. It fires once (a small
burst, all near-simultaneous) at mount and never again -- no scrollbar-driven resize loop found.
Also ran the exact same drag-timing test against a checkout of the commit before both suspect
commits (`1f3be0a4`) with nothing selected/radii untouched (true default state) -- frame times were
comparably noisy before and after, no consistent regression attributable to the CSS change.

**RadiiOverlays per-frame recompute (candidate 2): confirmed real, fixed.** `RadiiOverlays.tsx`'s
camera-facing light/sound circles (`RadiusCircle3D`, since renamed `RadiusCircleGroup3D`) ran their
own `useFrame` PER SELECTED ACTOR PER RADIUS TYPE -- N actors with both a light and sound radius
meant 2N independent per-frame camera-basis recomputes and 2N separate draw calls, continuously, in
EVERY mounted `<Canvas>` (react-three-fiber's default "always" frameloop re-renders all 4
quad-layout panes every animation frame regardless of interaction). Because all 4 canvases share one
JS main thread, this cost degrades responsiveness in every pane at once, not just the one being
dragged. Measured directly: with 40 selected radii-carrying actors and Radii view on, idle (zero
interaction) frame time averaged ~104ms/frame vs ~79ms with Radii off; after the fix, ~24ms vs
~20ms -- the radii-on idle overhead dropped from ~80ms/frame to ~4ms/frame. The sound-radius commit
exactly doubled an inefficiency that already existed for light radius alone (landed 2026-09-18,
`e81f6618`) -- fixed the underlying mechanism, not just sound radius's added share of it.

Fix (`web/src/scene/RadiiOverlays.tsx`): every selected actor's light circle (and, separately, every
sound circle) is now batched into ONE shared `<lineSegments>` geometry with ONE `useFrame` per radius
type per pane -- one camera-basis computation and one draw call regardless of how many actors are
selected, instead of one of each per actor. Collision cylinders are untouched (already static, no
`useFrame`). Regression tests added to `RadiiOverlays.test.tsx` asserting N selected actors with a
light radius produce exactly one `lineSegments` object (not N), and that light/sound still batch into
two SEPARATE draw calls (their colors never mix). All 9 pre-existing tests plus the 2 new ones pass
unchanged; full frontend suite (48 files / 424 tests) green.

**This does NOT explain the plain-default-state jitter** (radii off, nothing selected) -- in that
state `RadiiOverlays` returns `null` and never runs at all. The relative "radii on vs off" scaling
regression is real and worth having fixed regardless, but if the owner's original report reproduces
with Radii off and nothing selected, this fix does not touch that case.

## The "jump once, then nothing" perspective-pane report -- investigated, NOT this component

The coordinator asked whether `RadiiOverlays`' `useFrame` calls a React state setter (which could
tear down the drag handler mid-gesture via a parent re-render) -- checked directly:

- **No `useState`/`useReducer`/context-setter call exists anywhere in `RadiiOverlays.tsx`, before or
  after this fix.** The `useFrame` body is a pure imperative typed-array mutation
  (`geometry.attributes.position.array[...] = ...; needsUpdate = true`) -- no allocation, no state.
- `useThree()` (used to read `camera`) is a zustand-store subscription
  (`node_modules/@react-three/fiber/dist/events-*.esm.js`'s `useThree`/`useStore`) that only
  re-renders a consumer when the R3F store itself calls `set()` (e.g. a real resize) -- not on every
  animation frame merely because `useFrame` callbacks are running elsewhere. Confirmed by reading
  the library source directly, not assumed.
- Structurally, even a hypothetical per-frame re-render INSIDE `<Canvas>`'s children could not reach
  the DOM-level container `<div>`/pointer-capture refs `useDragGesture` (`dragGesture.ts`) owns --
  react-three-fiber's `<Canvas>` maintains its own separate React reconciler root, decoupled from the
  outer DOM tree. A state change inside the 3D scene graph cannot remount or reset the outer
  component's refs.

**Empirically ruled out too**: a synthetic-drag probe (headless Chromium via CDP,
`page.mouse.move`/`down`/`up`) against the perspective pane in the app's TRUE DEFAULT state (nothing
selected, Radii toggle never touched -- `RadiiOverlays` returns `null`, never mounts) still showed a
suspicious pattern worth flagging: under `requestPointerLock()` (`dragGesture.ts`'s lazy-lock-on-
first-move mechanic), each simulated mouse move produced TWO `pointermove` events with large
(hundreds-of-pixels), exactly-opposite `movementX`/`movementY` values that net to zero. If a real
browser under real hardware behaves the same way, this would look exactly like "jump once (the first
huge delta rotates the camera), then nothing" (the immediately-following opposite delta snaps it
back, and every subsequent pair keeps cancelling). This reproduces with RadiiOverlays never mounted
at all, so it is NOT caused by radii, and it predates both suspect commits (`dragGesture.ts` untouched
by either) -- a different, likely pre-existing mechanism in the pointer-lock request path.

**Not confirmed as a real-browser bug** -- headless Chromium's synthetic pointer-lock event dispatch
under CDP is a known-unreliable substrate for this exact question (a real physical mouse under real
pointer lock does not, as far as documented behavior goes, report compensating-opposite deltas like
this), so this could equally be a pure artifact of the test harness rather than of the app. Flagged
honestly rather than claimed as a fix: this needs a real browser + real mouse (or at minimum a
non-headless environment) to confirm before touching `dragGesture.ts`. Filing as a new lead for
whoever picks up the separate "3D perspective pane mouse navigation unusable" report -- not fixed
here, out of this item's scope (this item was scoped to the ortho jitter + the two named CSS/radii
candidates).

## Verification

Real headless Chromium was made to run in this sandbox (the cached
`chromium_headless_shell-1243` binary was missing shared libraries; fetched them as user-writable
`.deb` extracts via a user-writable `apt-get download` + `dpkg-deb -x`, no root needed -- same
recipe `dev/docs/board/done/mobile-joystick-non-functional-updown-stuck/overview.md` used). Drove the
real `App`/`QuadLayout`/`OrthoViewport`/`Viewport3D`/`RadiiOverlays` code (not a reimplementation) via
a throwaway Vite entry with a mocked `fetch`/`WebSocket` (no backend needed) -- deleted before this
commit, not part of the change. Full frontend suite (vitest, `--no-file-parallelism`): 48 files / 424
tests green, including the 2 new `RadiiOverlays.test.tsx` regressions.

## Files

- `web/src/scene/RadiiOverlays.tsx` -- the fix (`RadiusCircle3D` -> `RadiusCircleGroup3D`, batched
  per radius type instead of per actor).
- `web/src/scene/RadiiOverlays.test.tsx` -- new regression tests for the batching.
