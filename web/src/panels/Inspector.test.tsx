import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { Inspector } from './Inspector'

afterEach(cleanup)

function fixtureActor(overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name: 'Room',
    cls: 'Engine.Brush',
    bbox_lo: [-256, -256, -128],
    bbox_hi: [256, 256, 128],
    location: [10, 20, 30],
    rotation: [0, 16384, 0],
    folder: 'geo/rooms',
    labels: ['lighting'],
    order_value: 'm',
    props: [
      ['CsgOper', 'CSG_Subtract'],
      ['PolyFlags', '2'],
    ],
    brush: null,
    sprite: null,
    ...overrides,
  }
}

describe('Inspector', () => {
  it('renders "no selection" when nothing is selected', () => {
    render(<Inspector actor={null} />)
    expect(screen.getByTestId('inspector-empty').textContent).toBe('No selection')
  })

  it("renders a fixture actor's property rows", () => {
    render(<Inspector actor={fixtureActor()} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()
    expect(screen.getByText('Engine.Brush')).toBeTruthy()
    expect(screen.getByText('10.00, 20.00, 30.00')).toBeTruthy() // location
    expect(screen.getByText('0, 16384, 0')).toBeTruthy() // rotation
    expect(screen.getByText('geo/rooms')).toBeTruthy()
    expect(screen.getByText('lighting')).toBeTruthy()
    expect(screen.getByText('m')).toBeTruthy()
    expect(screen.getByText('CsgOper')).toBeTruthy()
    expect(screen.getByText('CSG_Subtract')).toBeTruthy()
  })

  it('falls back to "(no folder)"/"(no label)" for an unset folder/labels', () => {
    render(<Inspector actor={fixtureActor({ folder: null, labels: [] })} />)
    expect(screen.getByText('(no folder)')).toBeTruthy()
    expect(screen.getByText('(no label)')).toBeTruthy()
  })

  it('re-renders for a newly selected actor (selection swap)', () => {
    const { rerender } = render(<Inspector actor={fixtureActor({ name: 'Room' })} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()

    rerender(<Inspector actor={fixtureActor({ name: 'Door', cls: 'Engine.Mover' })} />)
    expect(screen.getByRole('heading', { name: 'Door' })).toBeTruthy()
    expect(screen.getByText('Engine.Mover')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Room' })).toBeNull()
  })
})
