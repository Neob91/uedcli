import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionLabel } from './SessionLabel'

const renameSession = vi.fn()
const navigate = vi.fn()

vi.mock('../api', () => ({ renameSession: (...args: unknown[]) => renameSession(...args) }))
vi.mock('./route', () => ({ navigate: (...args: unknown[]) => navigate(...args) }))

afterEach(() => {
  cleanup()
  renameSession.mockReset()
  navigate.mockReset()
})

describe('SessionLabel', () => {
  it('shows name-or-level with the raw id on hover', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name="My Session" onRenamed={vi.fn()} />)
    const label = screen.getByText('My Session')
    expect(label.title).toBe('s1')
  })

  it('falls back to the level when unnamed', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name={null} onRenamed={vi.fn()} />)
    expect(screen.getByText('TestLevel')).toBeTruthy()
  })

  it('clicking the label, editing, and confirming calls renameSession(sessionId, newName) and onRenamed', async () => {
    renameSession.mockResolvedValue({ id: 's1', level: 'TestLevel', created_at: 'c', last_active_at: 'a', name: 'New Name' })
    const onRenamed = vi.fn()
    render(<SessionLabel sessionId="s1" level="TestLevel" name="My Session" onRenamed={onRenamed} />)

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(renameSession).toHaveBeenCalledWith('s1', 'New Name'))
    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith('New Name'))
  })

  it('the back-to-picker link navigates to "/" with no confirmation', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name={null} onRenamed={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /sessions|picker|back/i }))
    expect(navigate).toHaveBeenCalledWith('/')
  })

  // Regression: a failed rename used to only console.error, with nothing shown on screen -- a
  // real 409 (a claim race) produced no visible change at all. Assert the message actually renders.
  it('a failed rename shows the error message on screen', async () => {
    renameSession.mockRejectedValue(new Error('session claimed by another connection'))
    const onRenamed = vi.fn()
    render(<SessionLabel sessionId="s1" level="TestLevel" name="My Session" onRenamed={onRenamed} />)

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(screen.getByText(/session claimed by another connection/i)).toBeTruthy())
    expect(onRenamed).not.toHaveBeenCalled()
  })
})
