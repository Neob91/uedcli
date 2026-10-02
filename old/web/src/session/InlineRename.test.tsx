import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InlineRename } from './InlineRename'

afterEach(cleanup)

describe('InlineRename', () => {
  it('shows the current value as plain text, with an edit trigger', () => {
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={vi.fn()} />)
    expect(screen.getByText('My Session')).toBeTruthy()
  })

  it('falls back to the placeholder when value is null', () => {
    render(<InlineRename value={null} placeholder="TestLevel" onRename={vi.fn()} />)
    expect(screen.getByText('TestLevel')).toBeTruthy()
  })

  it('clicking the display text enters edit mode with the current value pre-filled', () => {
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={vi.fn()} />)
    fireEvent.click(screen.getByText('My Session'))
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('My Session')
  })

  it('confirming (the tick button) calls onRename with the edited value and exits edit mode', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))
    expect(onRename).toHaveBeenCalledWith('New Name')
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('confirming via Enter has the same effect as clicking the tick button', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('New Name')
  })

  it('canceling (the X button) discards the edit and calls onRename never', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Discarded' } })
    fireEvent.click(screen.getByRole('button', { name: /cancel|✗/i }))
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('My Session')).toBeTruthy()
  })

  it('canceling via Escape has the same effect as clicking the X button', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Discarded' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('My Session')).toBeTruthy()
  })
})
