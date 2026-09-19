// Shared mouse-only pointer-lock/capture/tap-vs-drag plumbing (quad-layout Part 0, Task 4):
// extracted out of Viewport3D.tsx so an ortho pane (OrthoViewport, Part 1) gets the SAME DOM-level
// mechanics -- setPointerCapture on down, lazy requestPointerLock on the first real drag movement
// (avoiding movementX/Y screen-edge clamping), accumulated total drag distance, isTap-gated
// tap-vs-drag on up with exitPointerLock -- with only what a drag/tap MEANS differing per pane
// (dolly+turn/look/pan/orbit for Perspective; pan/zoom for ortho). Multi-touch gestures stay
// per-viewport-local (Viewport3D.tsx and OrthoViewport.tsx each wrap this hook's mouse-only
// handlers with their own pointerType==='touch' branch) -- this hook itself is mouse-only.
import { useCallback, useEffect, useRef } from 'react'
import type {
  MouseEvent as ReactMouseEvent,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
} from 'react'

import { isTap } from './selection'

export interface DragGestureCallbacks {
  /** Fires on EVERY pointer move during a drag, regardless of whether the gesture turns out to be
   * a tap on release -- matches today's behavior (camera callbacks fire live, tap/drag is decided
   * only at pointerup). `buttons`/`altKey` are the raw `PointerEvent` fields, so the caller can pick
   * dolly+turn/look/pan/orbit (Perspective) or pan (ortho) exactly as it does today. */
  onDrag: (dx: number, dy: number, buttons: number, altKey: boolean) => void
  /** Fires on pointerup ONLY when the accumulated movement stayed within the tap threshold AND the
   * button/altKey gate below passed. `additive` is `ctrlKey || metaKey` at release, threaded through
   * for Part 3's Ctrl+click multi-select. `shiftKey` is the raw release-time Shift state, threaded
   * through for the 3D-perspective brush-selection gate (`selection.ts`'s `canSelectBrushTap`) --
   * callers may ignore either flag until they need it. */
  onTap: (clientX: number, clientY: number, additive: boolean, shiftKey: boolean) => void
  onWheel?: (deltaY: number) => void
}

export interface DragGestureHandlers {
  containerRef: MutableRefObject<HTMLDivElement | null>
  onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => void
  onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => void
  onPointerUp: (e: ReactPointerEvent<HTMLDivElement>) => void
  onContextMenu: (e: ReactMouseEvent<HTMLDivElement>) => void
}

interface DragTracker {
  // Accumulated movement since pointerdown, in screen pixels -- NOT a start/current position pair
  // (pointer-lock freezes clientX/clientY at wherever the cursor was when the lock engaged, so
  // distance can only be measured by summing each move event's movementX/movementY).
  totalDx: number
  totalDy: number
  // True from the moment requestPointerLock() is called until the first move event we see AFTER
  // document.pointerLockElement actually flips to this element. Firefox reports a garbage
  // recalibration movementX/movementY on that first post-lock move (live-confirmed against real
  // Firefox: a huge, wrong delta appears right as pointerlockchange/lostpointercapture fire --
  // matches Mozilla bug 1255338's documented "initial ... mousemove event right after the pointer
  // was locked" class of quirk). Applying it as a real drag delta is what makes a Firefox drag
  // jump/fling once and then read as frozen (the fling can throw the camera far enough that nothing
  // is visible any more, however correctly later deltas behave) -- so that one frame is discarded.
  awaitingLockSync: boolean
  // True from the moment requestPointerLock() is called until its returned Promise settles (either
  // way). Chrome/Firefox both reject that Promise when document.hasFocus() is false at call time
  // (spec-mandated -- observed for real right after a page load, before the document has fully
  // received focus) -- a real, expected failure mode, not a bug. Gates against firing a second
  // concurrent request while one is already in flight.
  lockRequestPending: boolean
}

export function useDragGesture(callbacks: DragGestureCallbacks): DragGestureHandlers {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const drag = useRef<DragTracker | null>(null)

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // A prior gesture can leave the pointer/capture state inconsistent (e.g. a failed
      // requestPointerLock() below never re-established capture the browser auto-released) --
      // don't let that throw here too and brick this NEW drag before it even starts. Losing
      // capture only means the drag won't keep tracking if the cursor leaves the element bounds,
      // the same tradeoff an already-lock-losing gesture has anyway.
    }
    drag.current = { totalDx: 0, totalDy: 0, awaitingLockSync: false, lockRequestPending: false }
    // Pointer lock is requested lazily, on the first real MOVEMENT of a drag (onPointerMove below),
    // not here on plain pointerdown -- a tap that never moves (a selection click) never locks at
    // all, so the cursor stays visible and the browser's "has control of your pointer" banner never
    // fires for a plain click.
  }, [])

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const d = drag.current
      if (!d) return
      const dx = e.movementX
      const dy = e.movementY
      const isLocked = document.pointerLockElement === e.currentTarget
      const isRealMovement = dx !== 0 || dy !== 0
      if (!isLocked && !d.lockRequestPending && isRealMovement) {
        // Lock is requested lazily, on real MOVEMENT rather than on pointerdown (see
        // onPointerDown's comment) -- first tried on this drag's first move, and retried on EVERY
        // later move where it's still not locked and no request is already in flight (see the
        // .catch below). This is deliberately not a one-shot attempt: "document is not focused" can
        // recur repeatedly on the same drag, not just once at page load -- reported live on
        // SteamOS/gamescope (a full-screen compositor with non-standard window-focus semantics
        // built around cursor warping and controller input, not ordinary browser focus timing),
        // where Firefox's document focus can flicker independently of user action. A one-shot
        // attempt would strand the user in the degraded (unlocked, screen-edge-clamped) mode for
        // the rest of that drag even after focus recovers a moment later; retrying every move costs
        // nothing extra once locked (isLocked short-circuits this branch). requestPointerLock() is
        // async, so the lock doesn't actually engage until a later move event -- flag that so the
        // transition frame below can be caught and discarded.
        const target = e.currentTarget
        d.lockRequestPending = true
        d.awaitingLockSync = true
        const lockResult = target.requestPointerLock?.()
        if (lockResult && typeof lockResult.then === 'function') {
          lockResult.then(
            () => {
              d.lockRequestPending = false
            },
            () => {
              // A genuine, documented browser restriction (e.g. the document isn't focused yet) --
              // not a bug here. The drag itself doesn't depend on the lock succeeding: dx/dy below
              // always come from the PointerEvent's own movementX/movementY regardless of
              // pointerLockElement, so a failed lock just means this drag keeps the ordinary
              // screen-edge-clamped semantics the lazy-lock design was trying to avoid, rather than
              // going dead. onPointerMove retries on the next real movement (above).
              d.lockRequestPending = false
              d.awaitingLockSync = false
            },
          )
        } else {
          // No Promise returned (older/non-conforming implementation) -- nothing to await or catch.
          d.lockRequestPending = false
        }
      } else if (isLocked && d.awaitingLockSync) {
        // The lock just engaged (see DragTracker.awaitingLockSync's doc comment for why this one
        // frame's movementX/Y is untrustworthy on Firefox): drop it entirely, neither accumulating
        // it into totalDx/totalDy nor firing onDrag, then resume trusting movement normally.
        d.awaitingLockSync = false
        return
      }
      d.totalDx += dx
      d.totalDy += dy
      if (dx === 0 && dy === 0) return
      callbacks.onDrag(dx, dy, e.buttons, e.altKey)
    },
    [callbacks],
  )

  const onPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      // Clear drag state FIRST, before the fallible release/exit calls below -- Firefox already
      // auto-releases pointer capture the moment pointer lock engages (spec-mandated: see
      // DragTracker.awaitingLockSync's doc comment), so releasePointerCapture here is frequently a
      // redundant no-op. Ordering it after the state clear means a browser quirk throwing out of
      // either call can never leave drag.current stuck non-null, which would otherwise silently
      // freeze every future onPointerMove for this gesture (onPointerMove's own `if (!d) return`).
      const d = drag.current
      drag.current = null
      try {
        e.currentTarget.releasePointerCapture(e.pointerId)
      } catch {
        // already released (e.g. implicitly, by pointer lock engaging) -- nothing to do
      }
      document.exitPointerLock?.()
      // Tap-suppression gate, replicated INTERNALLY (never delegated to the caller): an RMB release
      // or an Alt+LMB release never taps, even under the movement threshold.
      if (!d || e.button !== 0 || e.altKey) return
      if (!isTap(0, 0, d.totalDx, d.totalDy)) return // a real drag, not a selection tap
      callbacks.onTap(e.clientX, e.clientY, e.ctrlKey || e.metaKey, e.shiftKey)
    },
    [callbacks],
  )

  const onContextMenu = useCallback((e: ReactMouseEvent<HTMLDivElement>) => e.preventDefault(), [])

  // A NATIVE (non-passive) `wheel` listener, not a JSX `onWheel` prop: React attaches its own
  // synthetic `wheel`/`touchstart` listeners passively by default (a perf default since React 17),
  // so `e.preventDefault()` inside a JSX `onWheel` handler is silently ignored by the browser. That
  // left ctrl+wheel (a laptop trackpad's pinch-zoom gesture) falling through to the browser's own
  // page-zoom instead of this viewport's own zoom (owner report, "laptop trackpad: can't zoom in 2D
  // views without zooming the whole browser page"). This callback holds the latest `callbacks` via a
  // ref so the listener itself is only attached/removed once per mount, not re-subscribed on every
  // render.
  const callbacksRef = useRef(callbacks)
  useEffect(() => {
    callbacksRef.current = callbacks
  })
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onNativeWheel = (e: WheelEvent) => {
      e.preventDefault()
      callbacksRef.current.onWheel?.(e.deltaY)
    }
    el.addEventListener('wheel', onNativeWheel, { passive: false })
    return () => el.removeEventListener('wheel', onNativeWheel)
  }, [])

  return { containerRef, onPointerDown, onPointerMove, onPointerUp, onContextMenu }
}
