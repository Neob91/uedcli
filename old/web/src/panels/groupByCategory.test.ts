import { describe, expect, it } from 'vitest'

import type { EffectiveProp } from '../api'
import { groupByCategory } from './groupByCategory'

function prop(name: string, category: string): EffectiveProp {
  return { kind: 'string', name, category, stored_value: '1', default_value: '' }
}

describe('groupByCategory', () => {
  it('groups props under their own category, preserving first-occurrence category order', () => {
    const props = [prop('CsgOper', 'Brush'), prop('Mass', 'Movement'), prop('PolyFlags', 'Brush')]
    const groups = groupByCategory(props)
    expect(Array.from(groups.keys())).toEqual(['Brush', 'Movement'])
    expect(groups.get('Brush')?.map((p) => p.name)).toEqual(['CsgOper', 'PolyFlags'])
    expect(groups.get('Movement')?.map((p) => p.name)).toEqual(['Mass'])
  })

  it('groups everything under one category when all props share it', () => {
    const props = [prop('CsgOper', 'Brush'), prop('PolyFlags', 'Brush')]
    const groups = groupByCategory(props)
    expect(Array.from(groups.keys())).toEqual(['Brush'])
    expect(groups.get('Brush')).toHaveLength(2)
  })

  it('returns an empty map for empty props', () => {
    expect(groupByCategory([])).toEqual(new Map())
  })
})
