import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LevelPicker } from './LevelPicker'

vi.mock('../api', () => ({
  fetchLevels: vi.fn(async () => ({
    levels: [
      { name: 'Alpha', active: false },
      { name: 'Beta', active: true },
    ],
    current: 'Beta',
  })),
}))

afterEach(cleanup)

describe('LevelPicker', () => {
  it('picking a different level in the dropdown calls onSwitchLevel with the right name', async () => {
    const onSwitchLevel = vi.fn()
    render(<LevelPicker currentLevel="Beta" disabled={false} error={null} onSwitchLevel={onSwitchLevel} />)

    await waitFor(() => expect(screen.getByText('Alpha')).toBeTruthy())

    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'Alpha' } })

    expect(onSwitchLevel).toHaveBeenCalledWith('Alpha')
  })

  it('does not call onSwitchLevel when the selected value is unchanged', async () => {
    const onSwitchLevel = vi.fn()
    render(<LevelPicker currentLevel="Beta" disabled={false} error={null} onSwitchLevel={onSwitchLevel} />)

    await waitFor(() => expect(screen.getByText('Alpha')).toBeTruthy())
    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'Beta' } })

    expect(onSwitchLevel).not.toHaveBeenCalled()
  })

  it('disables the select while a switch is in flight', async () => {
    render(<LevelPicker currentLevel="Beta" disabled={true} error={null} onSwitchLevel={vi.fn()} />)

    await waitFor(() => expect(screen.getByTestId('level-picker-select')).toBeTruthy())
    expect(screen.getByTestId('level-picker-select').hasAttribute('disabled')).toBe(true)
  })

  it('shows the switch-failure message when App hands one back', async () => {
    render(<LevelPicker currentLevel="Beta" disabled={false} error="level switch failed: boom" onSwitchLevel={vi.fn()} />)

    await waitFor(() => expect(screen.getByText(/level switch failed/)).toBeTruthy())
  })
})
