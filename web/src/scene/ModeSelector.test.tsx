import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ModeSelector } from './ModeSelector'

afterEach(cleanup)

describe('ModeSelector', () => {
  it('shows exactly the three in-scope modes, labeling unlit "Fullbright"', () => {
    render(<ModeSelector mode="wireframe" buildSolved={true} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'Wireframe' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Fullbright' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Lit' })).toBeTruthy()
    expect(screen.queryByText('Flat')).toBeNull()
    expect(screen.queryByText('Unlit')).toBeNull()
  })

  it('marks the current mode pressed and no other', () => {
    render(<ModeSelector mode="lit" buildSolved={true} onSelect={() => {}} />)
    expect(screen.getByTestId('mode-btn-lit').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('mode-btn-wireframe').getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByTestId('mode-btn-unlit').getAttribute('aria-pressed')).toBe('false')
  })

  it('disables unlit/lit (not wireframe) when the build is not solved', () => {
    render(<ModeSelector mode="wireframe" buildSolved={false} onSelect={() => {}} />)
    expect(screen.getByTestId('mode-btn-wireframe').hasAttribute('disabled')).toBe(false)
    expect(screen.getByTestId('mode-btn-unlit').hasAttribute('disabled')).toBe(true)
    expect(screen.getByTestId('mode-btn-lit').hasAttribute('disabled')).toBe(true)
  })

  it('clicking an available mode calls onSelect with that mode', () => {
    const onSelect = vi.fn()
    render(<ModeSelector mode="wireframe" buildSolved={true} onSelect={onSelect} />)
    fireEvent.click(screen.getByTestId('mode-btn-lit'))
    expect(onSelect).toHaveBeenCalledWith('lit')
  })

  it('a disabled button cannot fire onSelect', () => {
    const onSelect = vi.fn()
    render(<ModeSelector mode="wireframe" buildSolved={false} onSelect={onSelect} />)
    fireEvent.click(screen.getByTestId('mode-btn-lit'))
    expect(onSelect).not.toHaveBeenCalled()
  })
})
