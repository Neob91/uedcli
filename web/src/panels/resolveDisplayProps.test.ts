import { expect, test } from 'vitest'

import type { ClassResolution } from '../api'
import { buildDisplayProps } from './resolveDisplayProps'

test('a stated scalar leaf renders explicit; an unstated one renders the class default', () => {
  const cr: ClassResolution = {
    class: {
      props: [
        { kind: 'int', name: 'Health', category: 'Uncategorized', default_value: '100' },
        { kind: 'string', name: 'Tag', category: 'Uncategorized', default_value: '' },
      ],
    },
    types: {},
  }
  const out = buildDisplayProps(cr, { Health: '42' })
  expect(out).toEqual([
    { kind: 'int', name: 'Health', category: 'Uncategorized', stored_value: '42', default_value: '100' },
    { kind: 'string', name: 'Tag', category: 'Uncategorized', stored_value: null, default_value: '' },
  ])
})

test('an enum leaf carries enum_type through, stored_value from the sparse map', () => {
  const cr: ClassResolution = {
    class: {
      props: [
        { kind: 'enum', name: 'LightType', category: 'Lighting', enum_type: 'Engine.Actor.ELightType', default_value: 'LT_Steady' },
      ],
    },
    types: { 'Engine.Actor.ELightType': { kind: 'enum', values: ['LT_None', 'LT_Steady', 'LT_Blink'] } },
  }
  const out = buildDisplayProps(cr, { LightType: 'LT_Blink' })
  expect(out).toEqual([
    { kind: 'enum', name: 'LightType', category: 'Lighting', enum_type: 'Engine.Actor.ELightType',
      stored_value: 'LT_Blink', default_value: 'LT_Steady' },
  ])
})

test('a struct leaf recurses through types for shape, overlaying the sparse map per member', () => {
  const cr: ClassResolution = {
    class: {
      props: [
        { kind: 'struct', name: 'RotationRate', category: 'Movement', struct_type: 'Core.Rotator',
          default_value: { Pitch: '4096', Yaw: '30000', Roll: '3072' } },
      ],
    },
    types: {
      'Core.Rotator': { kind: 'struct', members: [
        { kind: 'int', name: 'Pitch' }, { kind: 'int', name: 'Yaw' }, { kind: 'int', name: 'Roll' },
      ] },
    },
  }
  const out = buildDisplayProps(cr, { 'RotationRate.Yaw': '1234' })
  expect(out).toEqual([
    {
      kind: 'struct', name: 'RotationRate', category: 'Movement',
      members: [
        { kind: 'int', name: 'Pitch', category: 'Movement', stored_value: null, default_value: '4096' },
        { kind: 'int', name: 'Yaw', category: 'Movement', stored_value: '1234', default_value: '30000' },
        { kind: 'int', name: 'Roll', category: 'Movement', stored_value: null, default_value: '3072' },
      ],
    },
  ])
})

test('an array-of-struct leaf synthesizes one element per array_dim slot, positionally addressed', () => {
  const cr: ClassResolution = {
    class: {
      props: [
        { kind: 'array', name: 'Alliances', category: 'AllianceTrigger', array_dim: 2,
          element_type: 'DeusEx.AllianceTrigger.InitialAllianceInfo',
          default_value: [
            { AllianceName: 'None', AllianceLevel: '0', bPermanent: 'False' },
            { AllianceName: 'None', AllianceLevel: '0', bPermanent: 'False' },
          ] },
      ],
    },
    types: {
      'DeusEx.AllianceTrigger.InitialAllianceInfo': { kind: 'struct', members: [
        { kind: 'name', name: 'AllianceName' }, { kind: 'float', name: 'AllianceLevel' },
        { kind: 'bool', name: 'bPermanent' },
      ] },
    },
  }
  const out = buildDisplayProps(cr, { 'Alliances.0.AllianceName': 'Greasel' })
  expect(out).toHaveLength(1)
  const arr = out[0]
  if (arr.kind !== 'array') throw new Error('expected array')
  expect(arr.elements).toHaveLength(2)
  expect(arr.elements[0].kind).toBe('struct')
  if (arr.elements[0].kind !== 'struct') throw new Error('expected struct')
  const nameMember = arr.elements[0].members.find((m) => m.name === 'AllianceName')
  expect(nameMember).toEqual({ kind: 'name', name: 'AllianceName', category: 'AllianceTrigger',
    stored_value: 'Greasel', default_value: 'None' })
})

test('a plain scalar array leaf uses element_kind, one element per default_value index', () => {
  const cr: ClassResolution = {
    class: {
      props: [
        { kind: 'array', name: 'WeaponPriority', category: 'Uncategorized', array_dim: 3,
          element_kind: 'name', default_value: ['Airblast2', 'hellsaw', 'None'] },
      ],
    },
    types: {},
  }
  const out = buildDisplayProps(cr, { 'WeaponPriority.1': 'python' })
  const arr = out[0]
  if (arr.kind !== 'array') throw new Error('expected array')
  expect(arr.elements.map((e) => (e.kind === 'name' ? e.stored_value : undefined))).toEqual([
    null, 'python', null,
  ])
  expect(arr.elements.map((e) => (e.kind === 'name' ? e.default_value : undefined))).toEqual([
    'Airblast2', 'hellsaw', 'None',
  ])
})
