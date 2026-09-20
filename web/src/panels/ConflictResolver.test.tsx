import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ConflictPayload } from '../api'
import { ConflictResolver } from './ConflictResolver'

afterEach(cleanup)

const CONFLICTS: ConflictPayload[] = [
  { name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] },
  { name: 'Light1', staged_location: [1, 2, 3], trunk_location: [4, 5, 6] },
]

const LABELS = { mine: 'Keep my move', theirs: 'Keep trunk value' }

describe('ConflictResolver', () => {
  it('renders null for an empty conflicts array', () => {
    const { container } = render(
      <ConflictResolver conflicts={[]} resolutionLabels={LABELS} onResolve={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders one row per conflict with both locations shown', () => {
    render(<ConflictResolver conflicts={CONFLICTS} resolutionLabels={LABELS} onResolve={vi.fn()} />)

    expect(screen.getByText('Light0')).toBeTruthy()
    expect(screen.getByText('Light1')).toBeTruthy()
    expect(screen.getByText(/10\.00, 0\.00, 0\.00/)).toBeTruthy()
    expect(screen.getByText(/20\.00, 0\.00, 0\.00/)).toBeTruthy()
    expect(screen.getAllByText('Keep my move').length).toBe(2)
    expect(screen.getAllByText('Keep trunk value').length).toBe(2)
  })

  it('does not let Confirm be clicked until every row has a pick', () => {
    const onResolve = vi.fn()
    render(<ConflictResolver conflicts={CONFLICTS} resolutionLabels={LABELS} onResolve={onResolve} />)

    const confirm = screen.getByRole('button', { name: /apply/i })
    expect(confirm.hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getAllByLabelText('Keep my move')[0])
    expect(confirm.hasAttribute('disabled')).toBe(true) // Light1 still unpicked

    fireEvent.click(screen.getAllByLabelText('Keep trunk value')[1])
    expect(confirm.hasAttribute('disabled')).toBe(false)

    expect(onResolve).not.toHaveBeenCalled() // picking alone never calls onResolve
  })

  it('confirming calls onResolve with the right map once every row is picked', () => {
    const onResolve = vi.fn()
    render(<ConflictResolver conflicts={CONFLICTS} resolutionLabels={LABELS} onResolve={onResolve} />)

    fireEvent.click(screen.getAllByLabelText('Keep my move')[0]) // Light0 -> mine
    fireEvent.click(screen.getAllByLabelText('Keep trunk value')[1]) // Light1 -> theirs

    fireEvent.click(screen.getByRole('button', { name: /apply/i }))

    expect(onResolve).toHaveBeenCalledWith({ Light0: 'mine', Light1: 'theirs' })
  })

  it('there is no dismiss/close action that bypasses per-row resolution', () => {
    render(<ConflictResolver conflicts={CONFLICTS} resolutionLabels={LABELS} onResolve={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /close|dismiss|cancel/i })).toBeNull()
  })
})
