import { describe, it, expect } from 'vitest'
import { shownValue, isExplicit, searchMatch } from './effectiveProps'

describe('shownValue', () => {
  it('returns stored_value when present', () => {
    expect(shownValue({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: '5', default_value: '0' })).toBe('5')
  })
  it('falls back to default_value when stored_value is null', () => {
    expect(shownValue({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: null, default_value: '0' })).toBe('0')
  })
  it('returns null for a struct (no top-level text)', () => {
    expect(shownValue({ kind: 'struct', name: 'Rotation', category: 'Movement', members: [] }))
      .toBeNull()
  })
  it('an enum shown value is already a canonical name, no ordinal lookup needed', () => {
    expect(shownValue({ kind: 'enum', name: 'LightType', category: 'Lighting',
                        enum_type: 'Engine.Light.ELightType',
                        stored_value: 'LT_Steady', default_value: 'LT_None' })).toBe('LT_Steady')
  })
})

describe('isExplicit', () => {
  it('is true for a scalar prop with a stored_value', () => {
    expect(isExplicit({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: '5', default_value: '0' })).toBe(true)
  })
  it('is false for a scalar prop with a null stored_value', () => {
    expect(isExplicit({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: null, default_value: '0' })).toBe(false)
  })
  it('is true for a struct with at least one explicit member', () => {
    const rot = { kind: 'struct' as const, name: 'Rotation', category: 'Movement',
                  members: [
                    { kind: 'float' as const, name: 'Yaw', category: 'Movement',
                      stored_value: '100', default_value: '0' },
                    { kind: 'float' as const, name: 'Pitch', category: 'Movement',
                      stored_value: null, default_value: '0' },
                  ] }
    expect(isExplicit(rot)).toBe(true)
  })
  it('is false for a struct whose members are all defaulted', () => {
    const rot = { kind: 'struct' as const, name: 'Rotation', category: 'Movement',
                  members: [
                    { kind: 'float' as const, name: 'Yaw', category: 'Movement',
                      stored_value: null, default_value: '0' },
                    { kind: 'float' as const, name: 'Pitch', category: 'Movement',
                      stored_value: null, default_value: '0' },
                  ] }
    expect(isExplicit(rot)).toBe(false)
  })
  it('is true for an array with at least one explicit element', () => {
    const arr = { kind: 'array' as const, name: 'Slots', category: 'Movement',
                  element_kind: 'int' as const,
                  elements: [
                    { kind: 'int' as const, name: 'Slots.0', category: 'Movement',
                      stored_value: null, default_value: '0' },
                    { kind: 'int' as const, name: 'Slots.1', category: 'Movement',
                      stored_value: '3', default_value: '0' },
                  ] }
    expect(isExplicit(arr)).toBe(true)
  })
  it('is false for an array whose elements are all defaulted', () => {
    const arr = { kind: 'array' as const, name: 'Slots', category: 'Movement',
                  element_kind: 'int' as const,
                  elements: [
                    { kind: 'int' as const, name: 'Slots.0', category: 'Movement',
                      stored_value: null, default_value: '0' },
                    { kind: 'int' as const, name: 'Slots.1', category: 'Movement',
                      stored_value: null, default_value: '0' },
                  ] }
    expect(isExplicit(arr)).toBe(false)
  })
})

describe('searchMatch', () => {
  it('matches only the own name, never a descendant', () => {
    const rot = { kind: 'struct' as const, name: 'Rotation', category: 'Movement',
                  members: [{ kind: 'float' as const, name: 'Yaw', category: 'Movement',
                             stored_value: '100', default_value: '0' }] }
    expect(searchMatch(rot, 'yaw')).toBe(false)   // Yaw is a MEMBER's name, not Rotation's own
    expect(searchMatch(rot, 'rot')).toBe(true)
  })
})
