import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import {
  buildFolderTree,
  hasNoLabel,
  matchesFind,
  matchesFolderPattern,
  matchesLabelFacets,
} from './orgFilter'

function actor(overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name: 'Helper1',
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
    ...overrides,
  }
}

describe('matchesFind (name/class fnmatch-style glob)', () => {
  it("matches a '*' glob against the name, case-insensitively", () => {
    expect(matchesFind(actor({ name: 'Helper1' }), { name: 'Helper*' })).toBe(true)
    expect(matchesFind(actor({ name: 'helper1' }), { name: 'HELPER*' })).toBe(true)
    expect(matchesFind(actor({ name: 'Light1' }), { name: 'Helper*' })).toBe(false)
  })

  it('matches an exact class glob', () => {
    expect(matchesFind(actor({ cls: 'Engine.Light' }), { cls: 'Engine.Light' })).toBe(true)
    expect(matchesFind(actor({ cls: 'Engine.Brush' }), { cls: 'Engine.Light' })).toBe(false)
    expect(matchesFind(actor({ cls: 'Engine.Light' }), { cls: 'Engine.*' })).toBe(true)
  })

  it('an absent field imposes no constraint', () => {
    expect(matchesFind(actor({ name: 'Anything' }), {})).toBe(true)
  })

  it('every stated field must match (AND-combined)', () => {
    const a = actor({ name: 'Helper1', cls: 'Engine.Light' })
    expect(matchesFind(a, { name: 'Helper*', cls: 'Engine.Light' })).toBe(true)
    expect(matchesFind(a, { name: 'Helper*', cls: 'Engine.Brush' })).toBe(false)
  })
})

describe('matchesFolderPattern (folderlib.py port)', () => {
  it('a wildcard-free pattern matches the folder itself AND its whole subtree', () => {
    expect(matchesFolderPattern('castle', 'castle')).toBe(true)
    expect(matchesFolderPattern('castle', 'castle.tower')).toBe(true)
    expect(matchesFolderPattern('castle', 'castle.tower.roof')).toBe(true)
    expect(matchesFolderPattern('castle', 'cast')).toBe(false) // no segment-boundary prefix match
  })

  it("'**.roof' matches only top-level 'roof' nodes, not their contents (no subtree extension on a wildcarded pattern)", () => {
    expect(matchesFolderPattern('**.roof', 'castle.roof')).toBe(true)
    expect(matchesFolderPattern('**.roof', 'roof')).toBe(true)
    expect(matchesFolderPattern('**.roof', 'castle.roof.tiles')).toBe(false)
  })

  it("'*' matches exactly one segment", () => {
    expect(matchesFolderPattern('castle.*', 'castle.tower')).toBe(true)
    expect(matchesFolderPattern('castle.*', 'castle.tower.roof')).toBe(false)
  })

  it('folder === null matches no pattern -- the "(no folder)" bucket is reached only its own way', () => {
    expect(matchesFolderPattern('castle', null)).toBe(false)
    expect(matchesFolderPattern('**', null)).toBe(false)
    expect(matchesFolderPattern('*', null)).toBe(false)
  })

  it('is case-insensitive', () => {
    expect(matchesFolderPattern('Castle', 'castle.TOWER')).toBe(true)
  })
})

describe('matchesLabelFacets', () => {
  it('matches everything when no facet is active', () => {
    expect(matchesLabelFacets(actor({ labels: [] }), new Set())).toBe(true)
    expect(matchesLabelFacets(actor({ labels: ['lighting'] }), new Set())).toBe(true)
  })

  it('OR-combines active facets', () => {
    const a = actor({ labels: ['lighting'] })
    expect(matchesLabelFacets(a, new Set(['lighting']))).toBe(true)
    expect(matchesLabelFacets(a, new Set(['sound']))).toBe(false)
    expect(matchesLabelFacets(a, new Set(['sound', 'lighting']))).toBe(true)
  })
})

describe('hasNoLabel', () => {
  it('is the "(no label)" bucket predicate -- never reachable via matchesLabelFacets with an active facet', () => {
    expect(hasNoLabel(actor({ labels: [] }))).toBe(true)
    expect(hasNoLabel(actor({ labels: ['lighting'] }))).toBe(false)
    // A label-less actor never matches ANY active facet, mirroring folder's mutual exclusivity.
    expect(matchesLabelFacets(actor({ labels: [] }), new Set(['lighting']))).toBe(false)
  })
})

describe('buildFolderTree', () => {
  it('buckets folder===null actors at the root as the "(no folder)" set', () => {
    const a = actor({ name: 'A', folder: null })
    const tree = buildFolderTree([a])
    expect(tree.actors).toEqual([a])
    expect(tree.children).toHaveLength(0)
  })

  it('creates one node per distinct folder path, nested under its parent', () => {
    const a = actor({ name: 'A', folder: 'castle.tower' })
    const tree = buildFolderTree([a])
    expect(tree.children).toHaveLength(1)
    const castle = tree.children[0]
    expect(castle.path).toBe('castle')
    expect(castle.actors).toEqual([])
    expect(castle.children).toHaveLength(1)
    const tower = castle.children[0]
    expect(tower.path).toBe('castle.tower')
    expect(tower.actors).toEqual([a])
  })

  it('shares an intermediate ancestor node across two actors in different subfolders', () => {
    const a = actor({ name: 'A', folder: 'castle.tower' })
    const b = actor({ name: 'B', folder: 'castle.gate' })
    const tree = buildFolderTree([a, b])
    expect(tree.children).toHaveLength(1)
    const castle = tree.children[0]
    expect(castle.children.map((c) => c.path).sort()).toEqual(['castle.gate', 'castle.tower'])
  })
})
