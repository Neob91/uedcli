import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useDragGesture } from './dragGesture'
import type { DragGestureCallbacks } from './dragGesture'

// jsdom doesn't implement Pointer Lock -- stub the pieces the hook touches as no-ops/getters, the
// same technique any DOM test in this repo needs for a browser API jsdom lacks.
function fakeCurrentTarget() {
  return {
    setPointerCapture: vi.fn(),
    releasePointerCapture: vi.fn(),
    requestPointerLock: vi.fn(),
  }
}

function pointerEvent(overrides: Record<string, unknown> = {}) {
  return {
    currentTarget: fakeCurrentTarget(),
    pointerId: 1,
    movementX: 0,
    movementY: 0,
    buttons: 1,
    button: 0,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    clientX: 0,
    clientY: 0,
    ...overrides,
  }
}

beforeEach(() => {
  Object.defineProperty(document, 'pointerLockElement', { value: null, writable: true, configurable: true })
  document.exitPointerLock = vi.fn()
})

function setup(overrides: Partial<DragGestureCallbacks> = {}) {
  const onDrag = vi.fn()
  const onTap = vi.fn()
  const callbacks: DragGestureCallbacks = { onDrag, onTap, ...overrides }
  const { result } = renderHook(() => useDragGesture(callbacks))
  return { handlers: result.current, onDrag, onTap }
}

describe('useDragGesture', () => {
  it('calls onDrag on every move, and onTap(x, y, false, false) on a release within the tap threshold', () => {
    const { handlers, onDrag, onTap } = setup()
    const down = pointerEvent()
    // @ts-expect-error -- synthetic event shape, sufficient for the handler's own field reads
    handlers.onPointerDown(down)
    const move = pointerEvent({ movementX: 1, movementY: -1 })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(move)
    expect(onDrag).toHaveBeenCalledWith(1, -1, 1, false)
    const up = pointerEvent({ clientX: 10, clientY: 20 })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(up)
    expect(onTap).toHaveBeenCalledWith(10, 20, false, false)
  })

  it('threads ctrlKey/metaKey into onTap\'s additive flag', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ ctrlKey: true }))
    expect(onTap).toHaveBeenCalledWith(0, 0, true, false)
  })

  it('threads shiftKey into onTap\'s 4th argument', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ shiftKey: true }))
    expect(onTap).toHaveBeenCalledWith(0, 0, false, true)
  })

  it('suppresses onTap when the accumulated movement exceeds the tap threshold (a real drag)', () => {
    const { handlers, onDrag, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ movementX: 50, movementY: 0 }))
    expect(onDrag).toHaveBeenCalledWith(50, 0, 1, false)
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent())
    expect(onTap).not.toHaveBeenCalled()
  })

  it('never taps on a right-button (button 2) release within the tap threshold', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ button: 2 }))
    expect(onTap).not.toHaveBeenCalled()
  })

  it('never taps on an Alt+left-button release within the tap threshold', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ altKey: true }))
    expect(onTap).not.toHaveBeenCalled()
  })
})
