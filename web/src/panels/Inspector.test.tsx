import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { ScenePoly, SceneActor } from '../api'
import { Inspector } from './Inspector'
import { groupByCategory } from './groupByCategory'
import type { SurfaceSelection } from './Inspector'

function fixturePoly(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [4, 8],
    tex_index: 12,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: 'Room',
    i_brush_poly: 4,
    ...overrides,
  }
}

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
    csg_rank: 3,
    props: [
      ['CsgOper', 'CSG_Subtract'],
      ['PolyFlags', '2'],
    ],
    categories: ['Brush', 'Brush'], // real live-verified mapping for both props (see scene.py's plan)
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
    ...overrides,
  }
}

describe('Inspector', () => {
  it('renders "no selection" when nothing is selected (regression pin: prop-shape-only change)', () => {
    render(<Inspector selected={[]} />)
    expect(screen.getByTestId('inspector-empty').textContent).toBe('No selection')
  })

  it("renders a fixture actor's property rows for exactly one selected actor (regression pin)", () => {
    render(<Inspector selected={[fixtureActor()]} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()
    expect(screen.getByText('Engine.Brush')).toBeTruthy()
    expect(screen.getByText('10.00, 20.00, 30.00')).toBeTruthy() // location
    expect(screen.getByText('0, 16384, 0')).toBeTruthy() // rotation
    expect(screen.getByText('geo/rooms')).toBeTruthy()
    expect(screen.getByText('lighting')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy() // csg_rank, not the raw order_value string
    expect(screen.queryByText('m')).toBeNull()
    expect(screen.getByText('CsgOper')).toBeTruthy()
    expect(screen.getByText('CSG_Subtract')).toBeTruthy()
  })

  it('falls back to "(no folder)"/"(no label)" for an unset folder/labels', () => {
    render(<Inspector selected={[fixtureActor({ folder: null, labels: [] })]} />)
    expect(screen.getByText('(no folder)')).toBeTruthy()
    expect(screen.getByText('(no label)')).toBeTruthy()
  })

  it('re-renders for a newly selected actor (selection swap)', () => {
    const { rerender } = render(<Inspector selected={[fixtureActor({ name: 'Room' })]} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()

    rerender(<Inspector selected={[fixtureActor({ name: 'Door', cls: 'Engine.Mover' })]} />)
    expect(screen.getByRole('heading', { name: 'Door' })).toBeTruthy()
    expect(screen.getByText('Engine.Mover')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Room' })).toBeNull()
  })

  it('renders one collapsible section per distinct category', () => {
    render(
      <Inspector
        selected={[
          fixtureActor({
            props: [
              ['CsgOper', 'CSG_Subtract'],
              ['Mass', '100'],
            ],
            categories: ['Brush', 'Movement'],
          }),
        ]}
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
        selected={[
          fixtureActor({
            props: [['Brush', "Model'MyLevel.Model_Room'"]],
            categories: ['Uncategorized'],
          }),
        ]}
      />,
    )
    expect(screen.getByText('Uncategorized (1)')).toBeTruthy()
    expect(screen.getByText('Brush')).toBeTruthy()
  })

  // Part 3, Task 16: 2+ selected -> a lightweight summary, not the full single-actor detail view.
  it('renders a lightweight "N actors selected" summary for 2+ selected actors', () => {
    render(<Inspector selected={[fixtureActor({ name: 'A' }), fixtureActor({ name: 'B' }), fixtureActor({ name: 'C' })]} />)
    expect(screen.getByTestId('inspector-multi')).toBeTruthy()
    expect(screen.getByText('3 actors selected')).toBeTruthy()
    expect(screen.getByText('A')).toBeTruthy()
    expect(screen.getByText('B')).toBeTruthy()
    expect(screen.getByText('C')).toBeTruthy()
    // Not the single-actor detail view's own markup.
    expect(screen.queryByTestId('inspector')).toBeNull()
  })

  // Surface (single-polygon texture) selection -- a DISTINCT selection kind from a whole-actor
  // selection (GUI.md "Selection & the Inspector"), owner-answered as highlight+inspect only.
  it('renders a single surface\'s detail view when exactly one texture is selected and no actor is', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly() }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} />)
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Room:4' })).toBeTruthy()
    expect(screen.getByText('#12')).toBeTruthy() // tex_index
    expect(screen.getByText('4, 8')).toBeTruthy() // pan
    expect(screen.queryByTestId('inspector-empty')).toBeNull()
  })

  it('renders "(untextured)" for a surface with no texture', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 0, poly: fixturePoly({ tex_index: -1 }) }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} />)
    expect(screen.getByText('(untextured)')).toBeTruthy()
  })

  it('renders a lightweight "N surfaces selected" summary for 2+ selected surfaces', () => {
    const surfaces: SurfaceSelection[] = [
      { actorName: 'Room', polyIndex: 1, poly: fixturePoly() },
      { actorName: 'Room', polyIndex: 2, poly: fixturePoly() },
    ]
    render(<Inspector selected={[]} selectedSurfaces={surfaces} />)
    expect(screen.getByTestId('inspector-multi-surfaces')).toBeTruthy()
    expect(screen.getByText('2 surfaces selected')).toBeTruthy()
    expect(screen.queryByTestId('inspector-surface')).toBeNull()
  })

  it('defaults selectedSurfaces to empty -- an actor-only call site is unaffected', () => {
    render(<Inspector selected={[]} />)
    expect(screen.getByTestId('inspector-empty')).toBeTruthy()
  })

  // The two kinds COEXIST -- UED22 keeps `AActor.bSelected` and `PF_Selected` as independent state
  // (GUI-PARITY.md "Actor + surface selection coexist; only a plain click clears both"), so both
  // props can be non-empty at once and BOTH sections must render. Replaces an earlier test that
  // asserted the actor selection "takes priority over a (should-be-empty) stale surface selection".
  it('renders BOTH an actor section and a surface section when both kinds are selected', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly() }
    render(<Inspector selected={[fixtureActor()]} selectedSurfaces={[surface]} />)
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Room:4' })).toBeTruthy()
    expect(screen.queryByTestId('inspector-empty')).toBeNull()
  })

  it('renders both MULTI summaries when 2+ actors and 2+ surfaces are selected together', () => {
    const actors = [fixtureActor(), fixtureActor({ name: 'Hall' })]
    const surfaces: SurfaceSelection[] = [
      { actorName: 'Room', polyIndex: 1, poly: fixturePoly() },
      { actorName: 'Room', polyIndex: 2, poly: fixturePoly() },
    ]
    render(<Inspector selected={actors} selectedSurfaces={surfaces} />)
    expect(screen.getByTestId('inspector-multi')).toBeTruthy()
    expect(screen.getByTestId('inspector-multi-surfaces')).toBeTruthy()
    expect(screen.getByText('2 actors selected')).toBeTruthy()
    expect(screen.getByText('2 surfaces selected')).toBeTruthy()
  })

  it('renders only the actor section when no surface is selected (no stray wrapper)', () => {
    render(<Inspector selected={[fixtureActor()]} selectedSurfaces={[]} />)
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.queryByTestId('inspector-sections')).toBeNull()
    expect(screen.queryByTestId('inspector-surface')).toBeNull()
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
