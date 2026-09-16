import { describe, expect, it } from 'vitest'

import { selectedSurfaceTriangleGroups } from './selectedTriangles'
import { surfaceKey } from './selectionSet'

// GUI.md "Selection & the Inspector": a texture (surface) selection highlights only the ONE
// selected polygon's triangles, not the whole brush's -- so membership is keyed on (owner,
// polyIndex), not owner alone.
describe('selectedSurfaceTriangleGroups', () => {
  it('returns the flat vertex-index triple for only the triangles of the selected POLY, not the whole owning actor', () => {
    // Actor 'A' owns triangles 0,1 (poly 4) and 2 (poly 5); only poly 4 is selected.
    const owners = ['A', 'A', 'A']
    const polyIndex = [4, 4, 5]
    const groups = [{ start: 0, count: 9, materialIndex: 0 }]
    expect(selectedSurfaceTriangleGroups(owners, polyIndex, new Set([surfaceKey('A', 4)]), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2, 3, 4, 5] },
    ])
  })

  it('includes triangles from every selected surface, across different actors', () => {
    const owners = ['A', 'B', 'A']
    const polyIndex = [1, 2, 3]
    const groups = [{ start: 0, count: 9, materialIndex: 0 }]
    const selected = new Set([surfaceKey('A', 1), surfaceKey('B', 2)])
    expect(selectedSurfaceTriangleGroups(owners, polyIndex, selected, groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2, 3, 4, 5] },
    ])
  })

  it('skips a triangle with no resolved owner or poly index', () => {
    const groups = [{ start: 0, count: 3, materialIndex: 0 }]
    expect(selectedSurfaceTriangleGroups([null], [0], new Set([surfaceKey('A', 0)]), groups)).toEqual([])
    expect(selectedSurfaceTriangleGroups(['A'], [null], new Set([surfaceKey('A', 0)]), groups)).toEqual([])
  })

  it('returns empty when nothing is selected', () => {
    const groups = [{ start: 0, count: 3, materialIndex: 0 }]
    expect(selectedSurfaceTriangleGroups(['A'], [0], new Set(), groups)).toEqual([])
  })

  it('does not match a same-actor triangle from a DIFFERENT poly (the whole point of surface selection)', () => {
    const owners = ['A', 'A']
    const polyIndex = [1, 2]
    const groups = [{ start: 0, count: 6, materialIndex: 0 }]
    expect(selectedSurfaceTriangleGroups(owners, polyIndex, new Set([surfaceKey('A', 1)]), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2] },
    ])
  })
})
