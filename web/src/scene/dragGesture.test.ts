/// <reference types="node" />
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
afterEach(() => vi.unstubAllGlobals())

// `isAdditiveModifier` (`../platform.ts`) reads jsdom's own `navigator.platform`/`userAgent`, which
// report Linux by default (confirmed against a fresh jsdom instance) -- so every test below that
// doesn't call this runs as "non-Mac: only ctrlKey counts" for free, matching the suite's existing
// baseline. This stubs Mac specifically for the tests that need it.
function mockMac() {
  vi.stubGlobal('navigator', { platform: 'MacIntel', userAgent: 'Macintosh' })
}

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
    expect(onDrag).toHaveBeenCalledWith(1, -1, 1, false, false)
    const up = pointerEvent({ clientX: 10, clientY: 20 })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(up)
    expect(onTap).toHaveBeenCalledWith(10, 20, false, false)
  })

  it('threads ctrlKey into onTap\'s additive flag (non-Mac: metaKey alone does NOT count)', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ ctrlKey: true }))
    expect(onTap).toHaveBeenCalledWith(0, 0, true, false)

    const { handlers: h2, onTap: onTap2 } = setup()
    // @ts-expect-error -- synthetic event shape
    h2.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    h2.onPointerUp(pointerEvent({ metaKey: true }))
    expect(onTap2).toHaveBeenCalledWith(0, 0, false, false)
  })

  it('on a Mac, threads metaKey (not ctrlKey) into onTap\'s additive flag -- macOS remaps Ctrl+click to a right-click, so Ctrl never actually reaches a real gesture there', () => {
    mockMac()
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ metaKey: true }))
    expect(onTap).toHaveBeenCalledWith(0, 0, true, false)

    const { handlers: h2, onTap: onTap2 } = setup()
    // @ts-expect-error -- synthetic event shape
    h2.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    h2.onPointerUp(pointerEvent({ ctrlKey: true }))
    expect(onTap2).toHaveBeenCalledWith(0, 0, false, false)
  })

  it('threads shiftKey into onTap\'s 4th argument', () => {
    const { handlers, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ shiftKey: true }))
    expect(onTap).toHaveBeenCalledWith(0, 0, false, true)
  })

  it('threads ctrlKey into onDrag\'s additive flag', () => {
    const { handlers, onDrag } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ movementX: 1, movementY: 1, ctrlKey: true }))
    expect(onDrag).toHaveBeenCalledWith(1, 1, 1, false, true)
  })

  it('non-Mac: metaKey alone does NOT thread into onDrag\'s additive flag', () => {
    const { handlers, onDrag } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ movementX: 1, movementY: 1, metaKey: true }))
    expect(onDrag).toHaveBeenCalledWith(1, 1, 1, false, false)
  })

  it('on a Mac, threads metaKey (not ctrlKey) into onDrag\'s additive flag', () => {
    mockMac()
    const { handlers, onDrag } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ movementX: 1, movementY: 1, metaKey: true }))
    expect(onDrag).toHaveBeenCalledWith(1, 1, 1, false, true)

    const { handlers: h2, onDrag: onDrag2 } = setup()
    // @ts-expect-error -- synthetic event shape
    h2.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    h2.onPointerMove(pointerEvent({ movementX: 1, movementY: 1, ctrlKey: true }))
    expect(onDrag2).toHaveBeenCalledWith(1, 1, 1, false, false)
  })

  it('suppresses onTap when the accumulated movement exceeds the tap threshold (a real drag)', () => {
    const { handlers, onDrag, onTap } = setup()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent())
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ movementX: 50, movementY: 0 }))
    expect(onDrag).toHaveBeenCalledWith(50, 0, 1, false, false)
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

  it('discards the movementX/Y reported on the move event where pointer lock actually engages (Firefox bug 1255338)', () => {
    const { handlers, onDrag } = setup()
    const target = fakeCurrentTarget()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    // First real movement: not locked yet, so this delta is genuine and requests the lock.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 5, movementY: 2 }))
    expect(onDrag).toHaveBeenCalledWith(5, 2, 1, false, false)
    onDrag.mockClear()
    // The lock engages asynchronously; simulate the browser flipping pointerLockElement before the
    // next move event fires -- exactly the event whose movementX/Y is untrustworthy on real Firefox.
    Object.defineProperty(document, 'pointerLockElement', { value: target, writable: true, configurable: true })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: -510, movementY: -207 }))
    expect(onDrag).not.toHaveBeenCalled()
    // Movement resumes being trusted normally on the very next event.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 3, movementY: 1 }))
    expect(onDrag).toHaveBeenCalledWith(3, 1, 1, false, false)
  })

  it('does not accumulate the discarded lock-transition delta into the tap/drag distance total', () => {
    const { handlers, onDrag, onTap } = setup()
    const target = fakeCurrentTarget()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 1, movementY: 0 }))
    Object.defineProperty(document, 'pointerLockElement', { value: target, writable: true, configurable: true })
    // A huge discarded delta would otherwise easily exceed the tap threshold.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: -510, movementY: -207 }))
    expect(onDrag).toHaveBeenCalledTimes(1) // only the first, real, small move
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ currentTarget: target }))
    expect(onTap).toHaveBeenCalled() // small enough total movement still reads as a tap
  })

  it('clears drag state before the fallible release/exit calls, so a throwing releasePointerCapture cannot strand it', () => {
    const { handlers, onTap } = setup()
    const target = fakeCurrentTarget()
    target.releasePointerCapture = vi.fn(() => {
      throw new DOMException('already released by pointer lock engaging')
    })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ currentTarget: target, clientX: 10, clientY: 20 }))
    expect(onTap).toHaveBeenCalledWith(10, 20, false, false)
  })

  it('does not leave an unhandled rejection when requestPointerLock() rejects (e.g. "document is not focused"), and the drag keeps working', async () => {
    const onUnhandledRejection = vi.fn()
    process.on('unhandledRejection', onUnhandledRejection)
    try {
      const { handlers, onDrag } = setup()
      const target = fakeCurrentTarget()
      target.requestPointerLock = vi.fn(() =>
        Promise.reject(new DOMException('The document is not focused.', 'NotAllowedError')),
      )
      // @ts-expect-error -- synthetic event shape
      handlers.onPointerDown(pointerEvent({ currentTarget: target }))
      // @ts-expect-error -- synthetic event shape
      handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 5, movementY: 2 }))
      // The drag doesn't depend on the lock succeeding -- onDrag still fires from the raw
      // movementX/Y on the event that triggered the (still-pending) lock request.
      expect(onDrag).toHaveBeenCalledWith(5, 2, 1, false, false)
      // Let the rejected promise's microtask settle.
      await Promise.resolve()
      await Promise.resolve()
      expect(onUnhandledRejection).not.toHaveBeenCalled()
      // The drag keeps working (ordinary movementX/Y semantics) after the lock failure.
      onDrag.mockClear()
      // @ts-expect-error -- synthetic event shape
      handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 3, movementY: -1 }))
      expect(onDrag).toHaveBeenCalledWith(3, -1, 1, false, false)
    } finally {
      process.off('unhandledRejection', onUnhandledRejection)
    }
  })

  it('retries requestPointerLock() on a later move after an earlier attempt rejected', async () => {
    const { handlers, onDrag } = setup()
    const target = fakeCurrentTarget()
    let calls = 0
    target.requestPointerLock = vi.fn(() => {
      calls += 1
      return calls === 1
        ? Promise.reject(new DOMException('The document is not focused.', 'NotAllowedError'))
        : Promise.resolve()
    })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 5, movementY: 2 }))
    expect(calls).toBe(1)
    await Promise.resolve()
    await Promise.resolve()
    // Second move retries since the first attempt failed and isn't locked/pending any more.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 1, movementY: 1 }))
    expect(calls).toBe(2)
    expect(onDrag).toHaveBeenCalledTimes(2) // both real moves still drove the camera
  })

  it('keeps retrying every move (never gives up) when the lock keeps failing intermittently across one drag, and locks on once it finally succeeds', async () => {
    // Models a real-machine report: on SteamOS/gamescope, document focus can flicker
    // repeatedly during a single drag, not just fail once at page load.
    const { handlers, onDrag } = setup()
    const target = fakeCurrentTarget()
    let calls = 0
    target.requestPointerLock = vi.fn(() => {
      calls += 1
      return calls < 4
        ? Promise.reject(new DOMException('The document is not focused.', 'NotAllowedError'))
        : Promise.resolve()
    })
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    for (let i = 0; i < 3; i++) {
      // @ts-expect-error -- synthetic event shape
      handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 1, movementY: 0 }))
      // eslint-disable-next-line no-await-in-loop
      await Promise.resolve()
      // eslint-disable-next-line no-await-in-loop
      await Promise.resolve()
    }
    expect(calls).toBe(3) // retried on every move so far, none succeeded yet
    // The 4th attempt succeeds -- simulate the browser actually engaging the lock before the next move.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 1, movementY: 0 }))
    expect(calls).toBe(4)
    await Promise.resolve()
    await Promise.resolve()
    Object.defineProperty(document, 'pointerLockElement', { value: target, writable: true, configurable: true })
    onDrag.mockClear()
    // Post-lock-engage transition frame is still discarded as usual, then movement resumes trusted.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: -999, movementY: -999 }))
    expect(onDrag).not.toHaveBeenCalled()
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 2, movementY: 0 }))
    expect(onDrag).toHaveBeenCalledWith(2, 0, 1, false, false)
    expect(calls).toBe(4) // no further (unneeded) requests once actually locked
  })

  it('a setPointerCapture() throw on pointerdown does not propagate, and the drag still starts', () => {
    const { handlers, onDrag, onTap } = setup()
    const target = fakeCurrentTarget()
    target.setPointerCapture = vi.fn(() => {
      throw new DOMException('object is not, or is no longer, usable', 'InvalidStateError')
    })
    expect(() => {
      // @ts-expect-error -- synthetic event shape
      handlers.onPointerDown(pointerEvent({ currentTarget: target }))
    }).not.toThrow()
    // The new drag still works: movement drives onDrag, and a real drag still suppresses onTap.
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerMove(pointerEvent({ currentTarget: target, movementX: 50, movementY: 0 }))
    expect(onDrag).toHaveBeenCalledWith(50, 0, 1, false, false)
    // @ts-expect-error -- synthetic event shape
    handlers.onPointerUp(pointerEvent({ currentTarget: target, clientX: 5, clientY: 5 }))
    expect(onTap).not.toHaveBeenCalled() // moved past the tap threshold above
  })
})
