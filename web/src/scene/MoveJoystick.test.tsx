import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { MoveJoystick } from './MoveJoystick'

// jsdom doesn't implement `Element.setPointerCapture`/`releasePointerCapture` (confirmed: both are
// `undefined` on a real jsdom element) -- the same class of gap `dragGesture.test.ts` already notes
// for Pointer Lock. Patched on the prototype (not per-call) since this test drives real DOM elements
// via `fireEvent`/`render`, unlike `dragGesture.test.ts`'s direct-handler-call style, which sidesteps
// the need for a real element at all.
beforeAll(() => {
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
})

afterEach(cleanup)

// `isTouchCapableDevice` reads real browser globals (`touchCapability.ts`'s own impure half) --
// mocked here the same way QuadLayout.test.tsx mocks a sibling module, so each test controls
// gating directly instead of poking jsdom's `navigator`/`window`.
vi.mock('./touchCapability', () => ({
  isTouchCapableDevice: vi.fn(),
}))
import { isTouchCapableDevice } from './touchCapability'

function setTouchCapable(capable: boolean) {
  vi.mocked(isTouchCapableDevice).mockReturnValue(capable)
}

describe('MoveJoystick touch gating', () => {
  it('renders nothing on a non-touch-capable device', () => {
    setTouchCapable(false)
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.queryByTestId('move-joystick-controls')).toBeNull()
  })

  it('renders the cluster on a touch-capable device', () => {
    setTouchCapable(true)
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.getByTestId('move-joystick-controls')).toBeTruthy()
    expect(screen.getByLabelText('Move up')).toBeTruthy()
    expect(screen.getByLabelText('Move down')).toBeTruthy()
  })
})

describe('MoveJoystick stick drag', () => {
  beforeAll(() => setTouchCapable(true))

  it('reports zero on pointerdown before any movement', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    // onStickChange isn't called on pointerdown itself (only on move/release) -- the dot state is
    // set directly, verified via the drag-then-release round trip below instead.
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('a straight-up drag reports full forward, no strafe', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 0, movementY: -32 })
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 1, right: 0 })
  })

  it('accumulates movement across multiple move events, clamped to the ring radius', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 100, movementY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 100, movementY: 0 })
    const last = onStickChange.mock.calls.at(-1)![0]
    expect(last.right).toBeCloseTo(1) // clamped -- far past the ring's radius
    expect(last.forward).toBeCloseTo(0)
  })

  it('a move event with a mismatched pointerId is ignored (not the dragging finger)', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 2, movementX: 50, movementY: 0 })
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('releasing reports zero and a later move (no active drag) is ignored', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 0, movementY: -32 })
    fireEvent.pointerUp(base, { pointerId: 1 })
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 0, right: 0 })
    onStickChange.mockClear()
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 100, movementY: 0 })
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('pointercancel also releases the drag and reports zero', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, movementX: 0, movementY: -32 })
    fireEvent(base, new window.PointerEvent('pointercancel', { pointerId: 1, bubbles: true }))
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 0, right: 0 })
  })
})

describe('MoveJoystick up/down buttons', () => {
  beforeAll(() => setTouchCapable(true))

  it('pressing up reports 1, releasing reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 5 })
    expect(onVerticalChange).toHaveBeenLastCalledWith(1)
    fireEvent.pointerUp(up, { pointerId: 5 })
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })

  it('pressing down reports -1, releasing reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const down = screen.getByLabelText('Move down')
    fireEvent.pointerDown(down, { pointerId: 6 })
    expect(onVerticalChange).toHaveBeenLastCalledWith(-1)
    fireEvent.pointerUp(down, { pointerId: 6 })
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })

  it('pointercancel on a held button also reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 7 })
    fireEvent(up, new window.PointerEvent('pointercancel', { pointerId: 7, bubbles: true }))
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })
})
