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

// `useInputMode` reads real global `pointerdown`/`keydown` listeners + `localStorage` (`inputMode.ts`'s
// own impure half) -- mocked here the same way QuadLayout.test.tsx mocks a sibling module, so each
// test controls gating directly instead of dispatching real global events.
vi.mock('./inputMode', () => ({
  useInputMode: vi.fn(),
}))
import { useInputMode } from './inputMode'

function setInputMode(mode: 'touch' | 'desktop') {
  vi.mocked(useInputMode).mockReturnValue(mode)
}

describe('MoveJoystick input-mode gating', () => {
  it('renders nothing in desktop mode', () => {
    setInputMode('desktop')
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.queryByTestId('move-joystick-controls')).toBeNull()
  })

  it('renders the cluster in touch mode', () => {
    setInputMode('touch')
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.getByTestId('move-joystick-controls')).toBeTruthy()
    expect(screen.getByLabelText('Move up')).toBeTruthy()
    expect(screen.getByLabelText('Move down')).toBeTruthy()
  })

  it('mounts and unmounts as the reported input mode changes', () => {
    setInputMode('desktop')
    const { rerender } = render(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.queryByTestId('move-joystick-controls')).toBeNull()

    setInputMode('touch')
    rerender(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.getByTestId('move-joystick-controls')).toBeTruthy()

    setInputMode('desktop')
    rerender(<MoveJoystick onStickChange={() => {}} onVerticalChange={() => {}} />)
    expect(screen.queryByTestId('move-joystick-controls')).toBeNull()
  })
})

describe('MoveJoystick stick drag', () => {
  beforeAll(() => setInputMode('touch'))

  it('reports zero on pointerdown before any movement', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    // onStickChange isn't called on pointerdown itself (only on move/release) -- the dot state is
    // set directly, verified via the drag-then-release round trip below instead.
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('a straight-up drag reports full forward, no strafe', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 0, movementY: -32 })
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 1, right: 0 })
  })

  it('accumulates movement across multiple move events, clamped to the ring radius', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 100, movementY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 100, movementY: 0 })
    const last = onStickChange.mock.calls.at(-1)![0]
    expect(last.right).toBeCloseTo(1) // clamped -- far past the ring's radius
    expect(last.forward).toBeCloseTo(0)
  })

  it('a move event with a mismatched pointerId is ignored (not the dragging finger)', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 2, pointerType: 'touch', movementX: 50, movementY: 0 })
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('releasing reports zero and a later move (no active drag) is ignored', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 0, movementY: -32 })
    fireEvent.pointerUp(base, { pointerId: 1, pointerType: 'touch' })
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 0, right: 0 })
    onStickChange.mockClear()
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 100, movementY: 0 })
    expect(onStickChange).not.toHaveBeenCalled()
  })

  it('pointercancel also releases the drag and reports zero', () => {
    const onStickChange = vi.fn()
    render(<MoveJoystick onStickChange={onStickChange} onVerticalChange={() => {}} />)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 0, movementY: -32 })
    fireEvent(base, new window.PointerEvent('pointercancel', { pointerId: 1, pointerType: 'touch', bubbles: true }))
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 0, right: 0 })
  })
})

// mobile-joystick-mouse-nav-regression: the cluster can be showing (mode is `'touch'`, mocked here)
// on a hybrid touchscreen+mouse device while the CURRENT event is a mouse pointer -- e.g. the same
// click that will switch `inputMode` back to `'desktop'` still has to land here first. Before the
// `pointerType` gate, a MOUSE event landing on the stick/buttons still unconditionally called
// `stopPropagation()`/`setPointerCapture`,
// swallowing normal camera-navigation clicks/drags in that corner -- reproduced live (see
// `dev/docs/board/done/mobile-joystick-non-functional-updown-stuck/overview.md`'s follow-on note).
// These tests prove a mouse pointer is a complete no-op: it reaches the ancestor container
// untouched, is never captured, and never changes the joystick's own reported state.
describe('MoveJoystick ignores non-touch pointers entirely', () => {
  beforeAll(() => setInputMode('touch'))

  it('a mouse drag on the stick reaches the ancestor container and reports nothing', () => {
    const onStickChange = vi.fn()
    const { containerPointerDown, containerPointerMove } = renderInsideCapturingContainer(onStickChange)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'mouse', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'mouse', movementX: 0, movementY: -32 })
    fireEvent.pointerUp(base, { pointerId: 1, pointerType: 'mouse' })
    expect(containerPointerDown).toHaveBeenCalledTimes(1)
    expect(containerPointerMove).toHaveBeenCalledTimes(1)
    expect(onStickChange).not.toHaveBeenCalled()
    expect(Element.prototype.setPointerCapture).not.toHaveBeenCalled()
  })

  it('a mouse press on the up button reaches the ancestor container and reports nothing', () => {
    const onVerticalChange = vi.fn()
    const { containerPointerDown } = renderInsideCapturingContainer(vi.fn(), onVerticalChange)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 9, pointerType: 'mouse' })
    expect(containerPointerDown).toHaveBeenCalledTimes(1)
    expect(onVerticalChange).not.toHaveBeenCalled()
    fireEvent.pointerUp(up, { pointerId: 9, pointerType: 'mouse' })
    expect(onVerticalChange).not.toHaveBeenCalled()
    expect(Element.prototype.setPointerCapture).not.toHaveBeenCalled()
  })
})

// mobile-joystick-non-functional-updown-stuck: Viewport3D.tsx's OWN container div has a touch
// pointerdown/pointermove handler (single-finger look-rotation) that unconditionally calls
// `setPointerCapture` on itself for ANY touch pointerdown -- reproduced here as `onPointerDown` on
// the wrapper below. Before the fix, a touch starting on the stick/buttons bubbled into this
// handler too (since MoveJoystick never called `stopPropagation()`), which stole pointer capture
// away from the joystick element that had just captured it -- confirmed live in a real Chromium
// (root-caused for this board item): the drag was read as a camera rotation instead of a
// translation, and the up/down buttons' own pointerup/pointercancel never fired (stuck "pressed").
// This test proves the wrapper's handler is never invoked for a joystick touch, which is what
// keeps pointer capture (and so all move/up/cancel delivery) with the joystick element itself.
function renderInsideCapturingContainer(onStickChange = vi.fn(), onVerticalChange = vi.fn()) {
  const containerPointerDown = vi.fn()
  const containerPointerMove = vi.fn()
  render(
    <div onPointerDown={containerPointerDown} onPointerMove={containerPointerMove}>
      <MoveJoystick onStickChange={onStickChange} onVerticalChange={onVerticalChange} />
    </div>,
  )
  return { containerPointerDown, containerPointerMove }
}

describe('MoveJoystick stops propagation (does not leak touches to an ancestor container)', () => {
  beforeAll(() => setInputMode('touch'))

  it('a stick drag never reaches the ancestor container, and still reports the drag correctly', () => {
    const onStickChange = vi.fn()
    const { containerPointerDown, containerPointerMove } = renderInsideCapturingContainer(onStickChange)
    const base = screen.getByTestId('move-joystick-base')
    fireEvent.pointerDown(base, { pointerId: 1, pointerType: 'touch', clientX: 0, clientY: 0 })
    fireEvent.pointerMove(base, { pointerId: 1, pointerType: 'touch', movementX: 0, movementY: -32 })
    fireEvent.pointerUp(base, { pointerId: 1, pointerType: 'touch' })
    expect(containerPointerDown).not.toHaveBeenCalled()
    expect(containerPointerMove).not.toHaveBeenCalled()
    expect(onStickChange).toHaveBeenCalledWith({ forward: 1, right: 0 })
    expect(onStickChange).toHaveBeenLastCalledWith({ forward: 0, right: 0 })
  })

  it('an up-button press never reaches the ancestor container, and still reports up/release', () => {
    const onVerticalChange = vi.fn()
    const { containerPointerDown } = renderInsideCapturingContainer(vi.fn(), onVerticalChange)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 9, pointerType: 'touch' })
    expect(containerPointerDown).not.toHaveBeenCalled()
    expect(onVerticalChange).toHaveBeenLastCalledWith(1)
    fireEvent.pointerUp(up, { pointerId: 9, pointerType: 'touch' })
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })
})

describe('MoveJoystick up/down buttons', () => {
  beforeAll(() => setInputMode('touch'))

  it('pressing up reports 1, releasing reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 5, pointerType: 'touch' })
    expect(onVerticalChange).toHaveBeenLastCalledWith(1)
    fireEvent.pointerUp(up, { pointerId: 5, pointerType: 'touch' })
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })

  it('pressing down reports -1, releasing reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const down = screen.getByLabelText('Move down')
    fireEvent.pointerDown(down, { pointerId: 6, pointerType: 'touch' })
    expect(onVerticalChange).toHaveBeenLastCalledWith(-1)
    fireEvent.pointerUp(down, { pointerId: 6, pointerType: 'touch' })
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })

  it('pointercancel on a held button also reports 0', () => {
    const onVerticalChange = vi.fn()
    render(<MoveJoystick onStickChange={() => {}} onVerticalChange={onVerticalChange} />)
    const up = screen.getByLabelText('Move up')
    fireEvent.pointerDown(up, { pointerId: 7, pointerType: 'touch' })
    fireEvent(up, new window.PointerEvent('pointercancel', { pointerId: 7, pointerType: 'touch', bubbles: true }))
    expect(onVerticalChange).toHaveBeenLastCalledWith(0)
  })
})
