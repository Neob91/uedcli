import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useHoldTooltip } from './useHoldTooltip'

afterEach(cleanup)

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

function TestButton({ onAction }: { onAction: () => void }) {
  const tip = useHoldTooltip('Test label')
  return (
    <button type="button" onClick={onAction} {...tip}>
      Btn
    </button>
  )
}

describe('useHoldTooltip', () => {
  it('sets data-tip to the given label immediately', () => {
    render(<TestButton onAction={() => {}} />)
    expect(screen.getByRole('button').getAttribute('data-tip')).toBe('Test label')
    expect(screen.getByRole('button').getAttribute('data-tip-active')).toBeNull()
  })

  it('a mouse click is unaffected -- no pointerdown/pointerup means no hold timer ever starts', () => {
    const onAction = vi.fn()
    render(<TestButton onAction={onAction} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('a short touch press (released before 500ms) still performs the action, tooltip never activates', () => {
    const onAction = vi.fn()
    render(<TestButton onAction={onAction} />)
    const button = screen.getByRole('button')
    fireEvent.pointerDown(button, { pointerType: 'touch' })
    vi.advanceTimersByTime(200)
    fireEvent.pointerUp(button, { pointerType: 'touch' })
    expect(button.getAttribute('data-tip-active')).toBeNull()
    fireEvent.click(button)
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('a touch press held past 500ms activates the tooltip and suppresses the next click', () => {
    const onAction = vi.fn()
    render(<TestButton onAction={onAction} />)
    const button = screen.getByRole('button')
    fireEvent.pointerDown(button, { pointerType: 'touch' })
    // React 18 doesn't flush a state update from a bare (non-React-scheduled) setTimeout callback
    // synchronously -- wrap the timer advance in act() so the resulting re-render is observable
    // before the assertion below, exactly as it would be for a real timer in a real browser.
    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(button.getAttribute('data-tip-active')).toBe('true')
    fireEvent.pointerUp(button, { pointerType: 'touch' })
    fireEvent.click(button)
    expect(onAction).not.toHaveBeenCalled()
  })

  it('releasing after a long hold clears data-tip-active, and the NEXT plain tap works normally', () => {
    const onAction = vi.fn()
    render(<TestButton onAction={onAction} />)
    const button = screen.getByRole('button')
    fireEvent.pointerDown(button, { pointerType: 'touch' })
    vi.advanceTimersByTime(600)
    fireEvent.pointerUp(button, { pointerType: 'touch' })
    fireEvent.click(button) // the suppressed click from the hold
    expect(button.getAttribute('data-tip-active')).toBeNull()

    fireEvent.pointerDown(button, { pointerType: 'touch' })
    vi.advanceTimersByTime(100)
    fireEvent.pointerUp(button, { pointerType: 'touch' })
    fireEvent.click(button)
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('pointercancel clears a pending hold the same way pointerup does', () => {
    const onAction = vi.fn()
    render(<TestButton onAction={onAction} />)
    const button = screen.getByRole('button')
    fireEvent.pointerDown(button, { pointerType: 'touch' })
    vi.advanceTimersByTime(200)
    fireEvent.pointerCancel(button, { pointerType: 'touch' })
    vi.advanceTimersByTime(600) // the timer must actually be cleared, not just ignored past this point
    expect(button.getAttribute('data-tip-active')).toBeNull()
  })
})
