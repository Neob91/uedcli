import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SelectionKeys } from './SelectionKeys'

afterEach(cleanup)

describe('SelectionKeys', () => {
  it('pressing F elsewhere calls onFrame with the current selectedNames', () => {
    const onFrame = vi.fn()
    const onDeselect = vi.fn()
    const selectedNames = new Set(['A', 'B'])
    render(<SelectionKeys selectedNames={selectedNames} onFrame={onFrame} onDeselect={onDeselect} />)

    fireEvent.keyDown(window, { key: 'f' })

    expect(onFrame).toHaveBeenCalledWith(selectedNames)
    expect(onDeselect).not.toHaveBeenCalled()
  })

  it('pressing F while a text input has focus is a no-op', () => {
    const onFrame = vi.fn()
    const { container } = render(
      <>
        <input data-testid="text-input" />
        <SelectionKeys selectedNames={new Set(['A'])} onFrame={onFrame} onDeselect={vi.fn()} />
      </>,
    )
    const input = container.querySelector('input') as HTMLInputElement
    input.focus()

    fireEvent.keyDown(input, { key: 'f' })

    expect(onFrame).not.toHaveBeenCalled()
  })

  it('Esc calls onDeselect unconditionally, even while a text input has focus', () => {
    const onDeselect = vi.fn()
    const { container } = render(
      <>
        <input data-testid="text-input" />
        <SelectionKeys selectedNames={new Set()} onFrame={vi.fn()} onDeselect={onDeselect} />
      </>,
    )
    const input = container.querySelector('input') as HTMLInputElement
    input.focus()

    fireEvent.keyDown(input, { key: 'Escape' })

    expect(onDeselect).toHaveBeenCalledTimes(1)
  })
})
