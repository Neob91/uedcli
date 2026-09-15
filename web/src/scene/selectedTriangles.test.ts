import { describe, expect, it } from 'vitest'

import { selectedTriangleIndices } from './selectedTriangles'

describe('selectedTriangleIndices', () => {
  it('returns the flat vertex-index triple for every triangle owned by a selected actor', () => {
    const owners = ['A', 'A', 'B', null, 'A']
    expect(selectedTriangleIndices(owners, new Set(['A']))).toEqual([0, 1, 2, 3, 4, 5, 12, 13, 14])
  })

  it('includes triangles from every selected actor, not just the first', () => {
    const owners = ['A', 'B', 'C']
    expect(selectedTriangleIndices(owners, new Set(['A', 'C']))).toEqual([0, 1, 2, 6, 7, 8])
  })

  it('skips a triangle with no resolved owner', () => {
    expect(selectedTriangleIndices([null], new Set(['A']))).toEqual([])
  })

  it('returns empty when nothing is selected', () => {
    expect(selectedTriangleIndices(['A', 'B'], new Set())).toEqual([])
  })

  it('returns empty when the selection matches no triangle owner', () => {
    expect(selectedTriangleIndices(['A', 'B'], new Set(['Ghost']))).toEqual([])
  })
})
