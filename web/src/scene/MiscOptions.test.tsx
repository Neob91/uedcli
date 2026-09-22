import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MiscOptions } from './MiscOptions'

afterEach(cleanup)

function renderMisc(overrides: Partial<Parameters<typeof MiscOptions>[0]> = {}) {
  const props = {
    showMoverSolid: false,
    onToggleMoverSolid: vi.fn(),
    showRadii: false,
    onToggleRadii: vi.fn(),
    showGrid: true,
    onToggleGrid: vi.fn(),
    baseGridSize: 16,
    onChangeGridSize: vi.fn(),
    activeTray: null,
    onActiveTrayChange: vi.fn(),
    ...overrides,
  }
  render(<MiscOptions {...props} />)
  return props
}

describe('MiscOptions', () => {
  it('the tray is closed by default', () => {
    renderMisc({ activeTray: null })
    expect(
      screen.getByLabelText('Movers').closest('.misc-options-flyout')?.classList.contains('open'),
    ).toBe(false)
  })

  it('clicking the trigger opens the tray by setting activeTray to "misc"', () => {
    const props = renderMisc({ activeTray: null })
    fireEvent.click(screen.getByRole('button', { name: 'Misc options' }))
    expect(props.onActiveTrayChange).toHaveBeenCalledWith('misc')
  })

  it('clicking the trigger again closes it', () => {
    const props = renderMisc({ activeTray: 'misc' })
    fireEvent.click(screen.getByRole('button', { name: 'Misc options' }))
    expect(props.onActiveTrayChange).toHaveBeenCalledWith(null)
  })

  it('the tray is visually open when activeTray is "misc"', () => {
    renderMisc({ activeTray: 'misc' })
    expect(
      screen.getByLabelText('Movers').closest('.misc-options-flyout')?.classList.contains('open'),
    ).toBe(true)
  })

  it('clicking the movers toggle calls onToggleMoverSolid and reflects state via aria-pressed', () => {
    const props = renderMisc({ showMoverSolid: false })
    const button = screen.getByLabelText('Movers')
    expect(button.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(button)
    expect(props.onToggleMoverSolid).toHaveBeenCalledTimes(1)
  })

  it('clicking the radii toggle calls onToggleRadii', () => {
    const props = renderMisc()
    fireEvent.click(screen.getByLabelText('Radii'))
    expect(props.onToggleRadii).toHaveBeenCalledTimes(1)
  })

  it('clicking the grid toggle calls onToggleGrid', () => {
    const props = renderMisc()
    fireEvent.click(screen.getByLabelText('Grid'))
    expect(props.onToggleGrid).toHaveBeenCalledTimes(1)
  })

  it('the grid-size select reflects baseGridSize and calls onChangeGridSize', () => {
    const props = renderMisc({ baseGridSize: 32 })
    const select = screen.getByLabelText('Grid size') as HTMLSelectElement
    expect(select.value).toBe('32')
    fireEvent.change(select, { target: { value: '64' } })
    expect(props.onChangeGridSize).toHaveBeenCalledWith(64)
  })

  it('the grid-size select stays visible but disabled when grid is off (no layout shift)', () => {
    renderMisc({ showGrid: false })
    const select = screen.getByLabelText('Grid size') as HTMLSelectElement
    expect(select).toBeTruthy()
    expect(select.disabled).toBe(true)
  })

  it('the grid-size select has no hold-tooltip data-tip attribute -- it uses the native title exception', () => {
    renderMisc()
    const select = screen.getByLabelText('Grid size')
    expect(select.hasAttribute('data-tip')).toBe(false)
    expect(select.closest('.misc-options-select-wrap')?.getAttribute('title')).toBe('Grid size')
  })

  it('a click outside the component while the tray is open dismisses it', () => {
    const props = renderMisc({ activeTray: 'misc' })
    fireEvent.pointerDown(document.body)
    expect(props.onActiveTrayChange).toHaveBeenCalledWith(null)
  })

  it('a click on one of its own toggles does not also fire the outside-dismiss path', () => {
    const props = renderMisc({ activeTray: 'misc' })
    fireEvent.pointerDown(screen.getByLabelText('Radii'))
    expect(props.onActiveTrayChange).not.toHaveBeenCalled()
  })
})
