import { describe, expect, it } from 'vitest'

import { selectedTriangleGroups } from './selectedTriangles'

describe('selectedTriangleGroups', () => {
  it('returns the flat vertex-index triple for every triangle owned by a selected actor', () => {
    const owners = ['A', 'A', 'B', null, 'A']
    const groups = [{ start: 0, count: 15, materialIndex: 0 }] // one group covering all 5 triangles
    expect(selectedTriangleGroups(owners, new Set(['A']), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2, 3, 4, 5, 12, 13, 14] },
    ])
  })

  it('includes triangles from every selected actor, not just the first', () => {
    const owners = ['A', 'B', 'C']
    const groups = [{ start: 0, count: 9, materialIndex: 0 }]
    expect(selectedTriangleGroups(owners, new Set(['A', 'C']), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2, 6, 7, 8] },
    ])
  })

  it('skips a triangle with no resolved owner', () => {
    const groups = [{ start: 0, count: 3, materialIndex: 0 }]
    expect(selectedTriangleGroups([null], new Set(['A']), groups)).toEqual([])
  })

  it('returns empty when nothing is selected', () => {
    const groups = [{ start: 0, count: 6, materialIndex: 0 }]
    expect(selectedTriangleGroups(['A', 'B'], new Set(), groups)).toEqual([])
  })

  it('returns empty when the selection matches no triangle owner', () => {
    const groups = [{ start: 0, count: 6, materialIndex: 0 }]
    expect(selectedTriangleGroups(['A', 'B'], new Set(['Ghost']), groups)).toEqual([])
  })

  it('keeps a selected actor\'s triangles split by draw group, each tagged with its own materialIndex', () => {
    // Triangle 0 in group 0 (e.g. an unmasked body material), triangle 1 in group 1 (e.g. a masked
    // hair-card material) -- both owned by the same selected actor, as a real NPC mesh actor's
    // triangles are (2026-09-15 mesh-actor selection-highlight fix).
    const owners = ['Npc', 'Npc']
    const groups = [
      { start: 0, count: 3, materialIndex: 0 },
      { start: 3, count: 3, materialIndex: 1 },
    ]
    expect(selectedTriangleGroups(owners, new Set(['Npc']), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2] },
      { materialIndex: 1, indices: [3, 4, 5] },
    ])
  })

  it('omits a group with no selected triangles, even when a sibling group has some', () => {
    const owners = ['Npc', 'Other']
    const groups = [
      { start: 0, count: 3, materialIndex: 0 },
      { start: 3, count: 3, materialIndex: 1 },
    ]
    expect(selectedTriangleGroups(owners, new Set(['Npc']), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2] },
    ])
  })

  it('defaults materialIndex to 0 when a group carries none (three.js addGroup default)', () => {
    const groups = [{ start: 0, count: 3 }]
    expect(selectedTriangleGroups(['A'], new Set(['A']), groups)).toEqual([
      { materialIndex: 0, indices: [0, 1, 2] },
    ])
  })
})
