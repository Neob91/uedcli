import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { groupByCategory, Inspector } from './Inspector'

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
    categories: ['Brush', 'Brush'], // real live-verified mapping for both props (see scene.py's plan)
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

  it('renders one collapsible section per distinct category', () => {
    render(
      <Inspector
        actor={fixtureActor({
          props: [
            ['CsgOper', 'CSG_Subtract'],
            ['Mass', '100'],
          ],
          categories: ['Brush', 'Movement'],
        })}
      />,
    )
    expect(screen.getByText('Brush (1)')).toBeTruthy()
    expect(screen.getByText('Movement (1)')).toBeTruthy()
    expect(screen.getByText('CsgOper')).toBeTruthy()
    expect(screen.getByText('Mass')).toBeTruthy()
  })

  it('renders a single "Uncategorized" section when every prop falls back', () => {
    render(
      <Inspector
        actor={fixtureActor({
          props: [
            ['Brush', "Model'MyLevel.Model_Room'"],
          ],
          categories: ['Uncategorized'],
        })}
      />,
    )
    expect(screen.getByText('Uncategorized (1)')).toBeTruthy()
    expect(screen.getByText('Brush')).toBeTruthy()
  })
})

describe('groupByCategory', () => {
  it('groups props under their categories, preserving first-occurrence category order', () => {
    const props: [string, string][] = [
      ['CsgOper', 'CSG_Subtract'],
      ['Mass', '100'],
      ['PolyFlags', '2'],
    ]
    const categories = ['Brush', 'Movement', 'Brush']
    const groups = groupByCategory(props, categories)
    expect(Array.from(groups.keys())).toEqual(['Brush', 'Movement'])
    expect(groups.get('Brush')).toEqual([
      ['CsgOper', 'CSG_Subtract'],
      ['PolyFlags', '2'],
    ])
    expect(groups.get('Movement')).toEqual([['Mass', '100']])
  })

  it('groups everything under one category when all props share it', () => {
    const props: [string, string][] = [
      ['CsgOper', 'CSG_Subtract'],
      ['PolyFlags', '2'],
    ]
    const groups = groupByCategory(props, ['Brush', 'Brush'])
    expect(Array.from(groups.keys())).toEqual(['Brush'])
    expect(groups.get('Brush')).toHaveLength(2)
  })

  it('returns an empty map for empty props', () => {
    expect(groupByCategory([], [])).toEqual(new Map())
  })

  it('throws on a props/categories length mismatch', () => {
    expect(() => groupByCategory([['A', '1']], [])).toThrow()
  })
})
