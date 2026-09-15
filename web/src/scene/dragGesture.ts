// Shared mouse-only pointer-lock/capture/tap-vs-drag plumbing (quad-layout Part 0, Task 4):
// extracted out of Viewport3D.tsx so an ortho pane (OrthoViewport, Part 1) gets the SAME DOM-level
// mechanics -- setPointerCapture on down, lazy requestPointerLock on the first real drag movement
// (avoiding movementX/Y screen-edge clamping), accumulated total drag distance, isTap-gated
// tap-vs-drag on up with exitPointerLock -- with only what a drag/tap MEANS differing per pane
// (dolly+turn/look/pan/orbit for Perspective; pan/zoom for ortho). Touch handling stays
// Viewport3D-local (ortho touch parity is explicitly deferred, desktop-first) -- this hook is
// mouse-only.
import { useCallback, useRef } from 'react'
import type {
  MouseEvent as ReactMouseEvent,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
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
   * for Part 3's Ctrl+click multi-select -- callers may ignore it until then. */
  onTap: (clientX: number, clientY: number, additive: boolean) => void
  onWheel?: (deltaY: number) => void
}

export interface DragGestureHandlers {
  containerRef: MutableRefObject<HTMLDivElement | null>
  onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => void
  onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => void
  onPointerUp: (e: ReactPointerEvent<HTMLDivElement>) => void
  onWheel: (e: ReactWheelEvent<HTMLDivElement>) => void
  onContextMenu: (e: ReactMouseEvent<HTMLDivElement>) => void
}

interface DragTracker {
  // Accumulated movement since pointerdown, in screen pixels -- NOT a start/current position pair
  // (pointer-lock freezes clientX/clientY at wherever the cursor was when the lock engaged, so
  // distance can only be measured by summing each move event's movementX/movementY).
  totalDx: number
  totalDy: number
}

export function useDragGesture(callbacks: DragGestureCallbacks): DragGestureHandlers {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const drag = useRef<DragTracker | null>(null)

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { totalDx: 0, totalDy: 0 }
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
      if (d.totalDx === 0 && d.totalDy === 0 && (dx !== 0 || dy !== 0) && !document.pointerLockElement) {
        // First real movement of this drag: lock now (hides the cursor for the rest of the drag,
        // with no screen-edge clamp on movementX/Y).
        e.currentTarget.requestPointerLock?.()
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
      e.currentTarget.releasePointerCapture(e.pointerId)
      document.exitPointerLock?.()
      const d = drag.current
      drag.current = null
      // Tap-suppression gate, replicated INTERNALLY (never delegated to the caller): an RMB release
      // or an Alt+LMB release never taps, even under the movement threshold.
      if (!d || e.button !== 0 || e.altKey) return
      if (!isTap(0, 0, d.totalDx, d.totalDy)) return // a real drag, not a selection tap
      callbacks.onTap(e.clientX, e.clientY, e.ctrlKey || e.metaKey)
    },
    [callbacks],
  )

  const onWheel = useCallback(
    (e: ReactWheelEvent<HTMLDivElement>) => {
      callbacks.onWheel?.(e.deltaY)
    },
    [callbacks],
  )

  const onContextMenu = useCallback((e: ReactMouseEvent<HTMLDivElement>) => e.preventDefault(), [])

  return { containerRef, onPointerDown, onPointerMove, onPointerUp, onWheel, onContextMenu }
}
