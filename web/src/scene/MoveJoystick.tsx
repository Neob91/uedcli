// Touch-only virtual joystick + up/down buttons for the perspective pane's fly camera (board item
// mobile-3d-move-joystick-visual-design-pending): the owner-approved "Minimal HUD cluster" design --
// a thin ring + dot for the stick (not a solid filled base), compact button chips for up/down,
// grouped into one small low-profile corner cluster, styled with this app's own `--accent` token.
// Drives Viewport3D.tsx's EXISTING `flyMove`/`FLY_SPEED_UU_PER_SEC` fly mechanics as an alternate
// input source (via the `onStickChange`/`onVerticalChange` callbacks below, which feed a per-frame
// ref Viewport3D.tsx applies with `flyMove` -- see `TouchFlyInput` there) -- it emits the same
// `{forward,right,up}` shape the keyboard (`FlyKeys`) already produces, never a parallel movement
// system. Rendered only inside Viewport3D.tsx (the perspective pane), so it never appears in an
// ortho pane by construction; gated to touch-capable devices only (`touchCapability.ts`) -- a
// touch-capable laptop with a keyboard still sees it (the board item's own constraint), but a
// mouse-only desktop never does.
//
// Up/down icons: plain unicode chevrons (▲/▼), matching this app's existing toolbar icon
// convention (QuadLayout.tsx's sidebar-collapse toggle uses ◀/▶ the same way) rather than an SVG --
// the owner's one correction to the reviewed mockup (which showed +/-) was these arrows instead.
import { useCallback, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

import { joystickVector } from './joystick'
import type { JoystickVector } from './joystick'
import { isTouchCapableDevice } from './touchCapability'

// The ring's visual radius, in CSS px -- both the drawn ring size and the drag-clamp radius
// `joystickVector` normalizes against, so the dot never visually escapes its own ring.
const STICK_RADIUS_PX = 32

export interface MoveJoystickProps {
  /** Fires on every drag update with the current analog forward/right deflection, and once more
   * with `{forward:0,right:0}` on release -- mirrors `flyInput`'s shape (`camera.ts`) so the caller
   * can feed it straight into `flyMove`. */
  onStickChange: (input: JoystickVector) => void
  /** Fires `1` while the up button is held, `-1` while down is held, `0` the instant neither is --
   * mirrors `flyInput`'s `up` component (Q/E). */
  onVerticalChange: (up: number) => void
}

export function MoveJoystick({ onStickChange, onVerticalChange }: MoveJoystickProps) {
  // Computed once per mount, not per render -- a device's touch capability doesn't change mid-session.
  const [touchCapable] = useState(isTouchCapableDevice)
  const dragPointerId = useRef<number | null>(null)
  // The RAW (unclamped) accumulated drag offset -- accumulated via `movementX`/`movementY` (this
  // app's own pointer-drag convention, `dragGesture.ts`), not absolute screen coordinates, so no
  // `getBoundingClientRect` call is needed to find the stick's on-screen center.
  const rawOffset = useRef({ dx: 0, dy: 0 })
  // The CLAMPED vector, used both to report movement and to place the dot -- null while not dragging
  // (dot centered, no movement reported beyond the release's own zero).
  const [stickVector, setStickVector] = useState<JoystickVector | null>(null)

  const onStickPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    dragPointerId.current = e.pointerId
    rawOffset.current = { dx: 0, dy: 0 }
    setStickVector({ forward: 0, right: 0 })
  }, [])

  const onStickPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (dragPointerId.current !== e.pointerId) return
      rawOffset.current.dx += e.movementX
      rawOffset.current.dy += e.movementY
      const v = joystickVector(rawOffset.current.dx, rawOffset.current.dy, STICK_RADIUS_PX)
      setStickVector(v)
      onStickChange(v)
    },
    [onStickChange],
  )

  const endStickDrag = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (dragPointerId.current !== e.pointerId) return
      e.currentTarget.releasePointerCapture(e.pointerId)
      dragPointerId.current = null
      setStickVector(null)
      onStickChange({ forward: 0, right: 0 })
    },
    [onStickChange],
  )

  const onVerticalPointerDown = useCallback(
    (direction: 1 | -1) => (e: ReactPointerEvent<HTMLButtonElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      onVerticalChange(direction)
    },
    [onVerticalChange],
  )
  const onVerticalPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLButtonElement>) => {
      e.currentTarget.releasePointerCapture(e.pointerId)
      onVerticalChange(0)
    },
    [onVerticalChange],
  )

  if (!touchCapable) return null

  return (
    <div className="move-joystick-controls" data-testid="move-joystick-controls">
      <div
        className="move-joystick-base"
        data-testid="move-joystick-base"
        onPointerDown={onStickPointerDown}
        onPointerMove={onStickPointerMove}
        onPointerUp={endStickDrag}
        onPointerCancel={endStickDrag}
      >
        <div
          className="move-joystick-dot"
          style={
            stickVector
              ? {
                  transform: `translate(calc(-50% + ${stickVector.right * STICK_RADIUS_PX}px), calc(-50% + ${-stickVector.forward * STICK_RADIUS_PX}px))`,
                }
              : undefined
          }
        />
      </div>
      <div className="move-vertical-buttons">
        <button
          type="button"
          className="move-vertical-btn"
          aria-label="Move up"
          onPointerDown={onVerticalPointerDown(1)}
          onPointerUp={onVerticalPointerUp}
          onPointerCancel={onVerticalPointerUp}
        >
          ▲
        </button>
        <button
          type="button"
          className="move-vertical-btn"
          aria-label="Move down"
          onPointerDown={onVerticalPointerDown(-1)}
          onPointerUp={onVerticalPointerUp}
          onPointerCancel={onVerticalPointerUp}
        >
          ▼
        </button>
      </div>
    </div>
  )
}
