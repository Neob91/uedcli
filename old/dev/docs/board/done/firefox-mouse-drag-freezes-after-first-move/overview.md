+++
priority = "p1"
kind = "debug"
summary = "Firefox mouse camera-drag jumps once then freezes; dragGesture.ts discards Firefox's post-pointer-lock recalibration delta"
+++

# Firefox mouse drag freezes after the first move

Owner report, real machine: on Firefox, with a mouse, camera-drag navigation breaks after the first
movement -- click to start a drag in the perspective pane, the view jumps once, then all further
mouse movement does nothing. Ortho panes: "moves weird, sometimes it does, sometimes not." Not a
regression -- reproduces on `5997b56d`, well before this session's other work.

## Mechanism (confirmed live, real Firefox)

`web/src/scene/dragGesture.ts`'s `onPointerMove` requests pointer lock LAZILY, on the first real
movement of a drag (`e.currentTarget.requestPointerLock()`), while the container already holds
pointer CAPTURE (`setPointerCapture`, called on `pointerdown`). Two real, documented Firefox
behaviors collide here, both reproduced live:

- **Firefox implicitly releases pointer capture the instant pointer lock engages** (spec-mandated,
  Mozilla bug 1399740, fixed in Firefox 58): a `lostpointercapture` event fires the moment
  `pointerlockchange` does.
- **Firefox reports an anomalous `movementX`/`movementY` on the move event immediately after lock
  engages** (Mozilla bug 1255338 documents this class of quirk directly: "there was an initial
  zero-movement mousemove event right after the pointer was locked" -- a lock-transition
  recalibration artifact). `dragGesture.ts` was applying this delta straight to `onDrag` like any
  other, unclamped.

That corrupted first-post-lock delta is the "jump": it can be large enough to fling the camera far
enough that nothing in the level is visible any more (`camera.ts`'s `dollyAndTurn`/`look`/`pan` have
no magnitude clamp on `dx`/`dy`), which then reads as "all further movement does nothing" even
though later deltas are correct -- there's simply nothing left in view to show the movement against.
Both viewports share this one hook (`Viewport3D.tsx` for perspective, `OrthoViewport.tsx` for ortho),
so the same root cause explains both reported symptoms.

## Fix

`dragGesture.ts`: track `awaitingLockSync` on the drag tracker, set `true` when
`requestPointerLock()` is called (it's async, so lock doesn't engage until a later move event).
On the first move event where `document.pointerLockElement` has actually become this element, drop
that ONE frame's `movementX`/`movementY` entirely -- don't accumulate it into the tap/drag distance
total, don't fire `onDrag` -- then resume trusting movement normally. No change to the lazy-lock/
no-lock-for-a-plain-tap UX (untouched code paths), and no effect on Chromium (which doesn't carry
this quirk; discarding one small legitimate frame there is imperceptible).

Also hardened `onPointerUp`: clear `drag.current` FIRST, before the now-possibly-redundant
`releasePointerCapture`/`exitPointerLock` calls (wrapped `releasePointerCapture` in try/catch too).
Firefox may have already implicitly released capture per the bug above; if that ever throws, the
drag-state cleanup must not be skipped, since a stuck non-null `drag.current` would itself silently
freeze every future `onPointerMove` for that gesture (its own `if (!d) return` guard).

## Verification

**Real Firefox, live, not a guess.** No cached Firefox build existed in this sandbox; downloaded one
via `playwright-core`'s `firefox` channel (`npx playwright install firefox`, revision 1543/Firefox
155), then resolved ~26 missing shared libraries (`libharfbuzz`, `libpango*`, `libepoxy`, Wayland/X11
libs, `libgraphite2`, `libatspi`, `libdatrie`, etc. -- more than the joystick campaign's Chromium
recipe needed) the same way: a user-writable `apt-get -o Dir::State::lists=...` config (no root) to
resolve/download `.deb`s, `dpkg-deb -x` into a scratch prefix, `LD_LIBRARY_PATH` pointed at it (with
Firefox's OWN directory listed FIRST, ahead of the extracted system libs -- otherwise the extracted
system `libnss3.so` shadows Firefox's bundled, newer one and it fails to launch with unresolved
`NSS_3.126`-class symbol versions). Firefox then launches headless and serves real pages.

Built a minimal HTML harness transcribing `dragGesture.ts`'s exact pre-fix algorithm (plain DOM, no
React) onto a real `<div>`, instrumented every `pointerdown`/`pointermove`/`pointerup`/
`pointercancel`/`lostpointercapture`/`gotpointercapture`/`pointerlockchange` event, and drove it with
Playwright's `page.mouse.down()`/`move()`/`up()` (genuine, `isTrusted: true` Firefox-synthesized
events, not `fireEvent`-mocked ones). Measured, unfixed code:

```
pointerdown -> gotpointercapture -> pointermove(movementX=15) -> requestPointerLock()
  -> pointerlockchange -> lostpointercapture
  -> pointermove(movementX=-510, movementY=-207)   <-- the garbage transition delta
```

Confirmed the transition delta appears ONLY at the lock-engage transition, not throughout the drag:
a follow-up run that triggers the lock then holds the synthetic pointer perfectly still (no further
`mouse.move()` calls) shows no further spurious `pointermove` at all while locked -- the next event
is the real `pointerup`. A second run that keeps calling `mouse.move()` with growing absolute targets
after lock engages showed several more frames of similarly-large, monotonically-shrinking garbage
values; this is very likely an artifact of Playwright's `page.mouse.move` being an ABSOLUTE-position
API being used to drive what should be genuinely relative post-lock motion (real hardware has no
"absolute position" concept for raw pointer-lock deltas at all) rather than a preview of real
multi-frame behavior -- flagged honestly rather than smoothed over, since it could not be confirmed
against real hardware in this sandbox. The single-frame fix matches Mozilla bug 1255338's own
documented language of one "initial" bad event.

Re-ran the same harness with the FIXED algorithm transcribed in: confirmed the `-510,-207` frame is
now dropped (`DISCARDED-lock-transition-frame`, no `onDrag` call), and the run's later frames apply
normally through to release.

Also wrote a unit regression (`dragGesture.test.ts`, jsdom, run via `bin/test`-equivalent `vitest
run`) using these exact live-observed values: requests lock on the first real move, discards the
`movementX=-510` frame that arrives once `document.pointerLockElement` flips to the container,
resumes trusting movement on the next frame, and confirms the discarded frame doesn't count toward
the tap/drag distance threshold. A third test confirms drag state is still cleared on `pointerup`
even when `releasePointerCapture` throws.

**Not verified**: the exact "then all further mouse movement does nothing" wording against a real
physical mouse on a real desktop Firefox (no GUI display / real hardware available in this sandbox).
The mechanism above (implicit capture loss + anomalous transition delta) is confirmed live against
real Firefox code; the THEORY of why it reads as a full freeze (camera flung out of view, not an
actual code-level stop) is reasoned from `camera.ts`'s unclamped `dx`/`dy` math, not itself
live-observed inside the real app (headless WebGL rendering has its own known issues in this sandbox,
see `dev/docs/board/inbox/front-side-ortho-panes-render-blank-in-headless/`, so running the full
`Viewport3D` scene headless was not attempted). If the owner's re-test still shows any residual issue,
the next step is a live capture of the OWNER's exact machine's post-lock `movementX`/`movementY`
sequence, not more headless-sandbox guessing.

Full frontend suite (`vitest run` in `web/`): 429/429 passing, no regressions. `tsc -b`/`oxlint` clean
on the touched files (the tree's existing `@types/node` `tsc` errors are pre-existing environment
gaps, unrelated to this change).

## Second, distinct robustness gap: unhandled pointer-lock rejection (2026-09-19)

The fix above addressed a Firefox recalibration-delta bug on a lock that DOES engage. A second,
separate report (real console capture) showed a lock that FAILS to engage at all:
`requestPointerLock()`'s returned Promise rejecting with `DOMException: The document is not
focused.`, uncaught -- followed on the next `pointerdown` by `setPointerCapture()` throwing
`An attempt was made to use an object that is not, or is no longer, usable`. This is a real, spec-
documented restriction (Pointer Lock refuses to engage when `document.hasFocus()` is false), not a
bug in this code -- the bug was `dragGesture.ts` never handling that rejection, or the pointer/
capture inconsistency it leaves behind.

Follow-up owner report: this reproduces on Firefox on a Steam Deck (SteamOS) but not on Firefox on a
Mac. SteamOS's compositor (gamescope) has documented non-standard window-focus behavior (e.g.
ValveSoftware/gamescope#398 "Incorrect focus with windows inside gamescope", #636 "gamescope
unfocused yet receiving gamepad input") -- consistent with `document.hasFocus()` flickering
repeatedly during a session rather than failing once at page load. The fix below was designed for
that: it retries on every subsequent move, not once.

### Fix (`web/src/scene/dragGesture.ts`)

- `onPointerDown`'s `setPointerCapture()` call is wrapped in try/catch. A prior drag's failed lock
  can leave the pointer/capture state inconsistent; without this, that throw was uncaught and (since
  it happened before `drag.current` was assigned) left the NEXT drag permanently dead until reload.
- `onPointerMove`'s lock request is no longer gated to "only the first move of the drag" -- it now
  fires on ANY move where the target isn't locked yet and no request is already in flight
  (`DragTracker.lockRequestPending`, new field), so a failure doesn't strand the drag: it retries on
  the very next real movement, and again after that, for as long as the drag continues without ever
  locking. The returned Promise's rejection branch resets `lockRequestPending`/`awaitingLockSync` and
  does nothing else -- the drag doesn't depend on the lock succeeding at all (`dx`/`dy` always come
  straight off the `PointerEvent`'s own `movementX`/`movementY`), so a failed lock just means this
  drag keeps the ordinary screen-edge-clamped semantics the lazy-lock design exists to avoid, not a
  dead drag. Once the lock does engage (on this drag or, worst case, starting fresh on the next
  pointerdown), the existing Firefox recalibration-frame handling above still applies unchanged.

### Verification

**Real browser, live.** Resolved the same missing-shared-library gap the prior fix's Firefox recipe
hit, this time for the cached `chromium-1243` Playwright build already in this sandbox
(`libglib-2.0`, `libnss3`, `libatk*`, `libdbus-1`, `libharfbuzz0b`, and ~20 others) via the same
no-root recipe: a user-writable `apt-get -o Dir::State::lists=...` config to download `.deb`s,
`dpkg-deb -x` into a scratch prefix, `LD_LIBRARY_PATH` pointed at it. Built a minimal DOM harness
transcribing `dragGesture.ts`'s exact algorithm (both pre- and post-fix) onto a plain `<div>`, drove
it with Playwright's `page.mouse` (genuine `isTrusted` events) against a real two-tab browser context
(a background tab reliably triggers a real Pointer Lock rejection in this Chromium build --
`WrongDocumentError`, not literally `NotFocusedError`, but the same code path: any rejected
`requestPointerLock()` Promise). Confirmed:

- **Pre-fix code, same environment**: `requestPointerLock()` with no `.catch` -- rejections were not
  reliably observed as `unhandledrejection` in this exact harness/timing (Chromium's own microtask
  timing didn't always surface it as unhandled in a plain non-React DOM harness), so this pass leans
  on the fixed-code side for the definitive real-browser evidence and on the pre-existing regression
  suite's mocked-rejection tests (below) for the precise "was it swallowed" assertion the live harness
  couldn't pin down reliably.
- **Fixed code, same environment, repeated runs**: every `requestPointerLock()` rejection was caught
  (`lock rejected (handled): ...` logged, zero entries in `window.__unhandled`), `onDrag` kept firing
  from ordinary `movementX`/`movementY` on every move despite the lock never engaging, and a second,
  independent pointerdown/move/pointerup cycle right after the first also worked cleanly with no
  thrown exception -- the exact "next click still works" property the report asked for.

**Unit regressions** (`dragGesture.test.ts`, jsdom + mocked `requestPointerLock`, `vitest run`):
a rejected lock Promise produces no unhandled rejection and the drag keeps calling `onDrag`; a
SECOND move after a first rejection retries the lock (proves the no-give-up property, not just a
single catch); a run of THREE consecutive rejections across one drag keeps retrying on every move
with no cap, then locks cleanly on the fourth attempt and resumes the existing post-lock-transition
handling unchanged; a throwing `setPointerCapture()` on `pointerdown` doesn't propagate and the new
drag still starts and still drags/taps correctly. Full frontend suite: 433/433 passing (was
429 before this fix's own +4 tests), `tsc -b`/`oxlint` clean on the touched files.

**Not verified**: the literal `NotFocusedError` rejection reason, or gamescope/SteamOS itself --
no SteamOS/gamescope environment was available in this sandbox. What's verified is the generic
mechanism this fix targets (any `requestPointerLock()` rejection, any reason, handled without an
unhandled rejection or a stuck subsequent drag) against a REAL browser's REAL Pointer Lock API, not
a mock -- which is reason-agnostic by construction, so this should hold for `NotFocusedError` too
without needing device-specific confirmation.

## Files

- `web/src/scene/dragGesture.ts` -- both fixes.
- `web/src/scene/dragGesture.test.ts` -- three new regression tests.
