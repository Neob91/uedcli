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
  switchLevel: vi.fn(async (name: string) => ({ level: name })),
}))

afterEach(cleanup)

describe('LevelPicker', () => {
  it('picking a different level in the dropdown calls switchLevel with the right name', async () => {
    const { switchLevel } = await import('../api')
    const onLevelChanged = vi.fn()
    render(<LevelPicker currentLevel="Beta" onLevelChanged={onLevelChanged} />)

    await waitFor(() => expect(screen.getByText('Alpha')).toBeTruthy())

    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'Alpha' } })

    await waitFor(() => expect(switchLevel).toHaveBeenCalledWith('Alpha'))
    await waitFor(() => expect(onLevelChanged).toHaveBeenCalledWith('Alpha'))
  })

  it('does not call switchLevel when the selected value is unchanged', async () => {
    const { switchLevel } = await import('../api')
    vi.mocked(switchLevel).mockClear()
    render(<LevelPicker currentLevel="Beta" onLevelChanged={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Alpha')).toBeTruthy())
    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'Beta' } })

    expect(switchLevel).not.toHaveBeenCalled()
  })
})
