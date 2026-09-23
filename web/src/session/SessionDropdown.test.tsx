import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionDropdown } from './SessionDropdown'

vi.mock('../api', () => ({
  fetchSessions: vi.fn(async () => ({
    sessions: [
      { id: 'sess-a1', level: 'Alpha', created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:01Z' },
      { id: 'sess-a2', level: 'Alpha', created_at: '2026-09-22T00:00:02Z', last_active_at: '2026-09-22T00:00:03Z' },
      { id: 'sess-b1', level: 'Beta', created_at: '2026-09-22T00:00:04Z', last_active_at: '2026-09-22T00:00:05Z' },
    ],
  })),
}))

afterEach(cleanup)

describe('SessionDropdown', () => {
  it('renders every session grouped by level', async () => {
    render(<SessionDropdown currentSessionId="sess-a1" onSwitchSession={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('sess-a2')).toBeTruthy())

    const select = screen.getByTestId('session-dropdown-select') as HTMLSelectElement
    const groupLabels = [...select.querySelectorAll('optgroup')].map((g) => g.getAttribute('label'))
    expect(groupLabels).toEqual(['Alpha', 'Beta'])

    const alphaGroup = select.querySelector('optgroup[label="Alpha"]')!
    expect([...alphaGroup.querySelectorAll('option')].map((o) => o.getAttribute('value'))).toEqual(['sess-a1', 'sess-a2'])

    const betaGroup = select.querySelector('optgroup[label="Beta"]')!
    expect([...betaGroup.querySelectorAll('option')].map((o) => o.getAttribute('value'))).toEqual(['sess-b1'])
  })

  it('picking a different session calls onSwitchSession with its id', async () => {
    const onSwitchSession = vi.fn()
    render(<SessionDropdown currentSessionId="sess-a1" onSwitchSession={onSwitchSession} />)

    await waitFor(() => expect(screen.getByText('sess-b1')).toBeTruthy())

    fireEvent.change(screen.getByTestId('session-dropdown-select'), { target: { value: 'sess-b1' } })

    expect(onSwitchSession).toHaveBeenCalledWith('sess-b1')
  })

  it('does not call onSwitchSession when the selected value is unchanged', async () => {
    const onSwitchSession = vi.fn()
    render(<SessionDropdown currentSessionId="sess-a1" onSwitchSession={onSwitchSession} />)

    await waitFor(() => expect(screen.getByText('sess-a2')).toBeTruthy())
    fireEvent.change(screen.getByTestId('session-dropdown-select'), { target: { value: 'sess-a1' } })

    expect(onSwitchSession).not.toHaveBeenCalled()
  })

  it('adds a synthetic option for a current session id the fetched list does not (yet) know', async () => {
    render(<SessionDropdown currentSessionId="sess-unknown" onSwitchSession={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('sess-a1')).toBeTruthy())
    expect(screen.getByText('sess-unknown')).toBeTruthy()
  })
})
