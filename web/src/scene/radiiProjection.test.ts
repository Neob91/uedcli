import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { collisionOrthoShape, selectedRadiiActors, sphereOrthoShape } from './radiiProjection'

describe('collisionOrthoShape', () => {
  it('is a circle of the collision radius when looking down the cylinder axis (top)', () => {
    expect(collisionOrthoShape('top', 50, 80)).toEqual({ kind: 'circle', radius: 50 })
  })

  it('is a 2*radius x 2*halfHeight rect edge-on (front/side)', () => {
    expect(collisionOrthoShape('front', 50, 80)).toEqual({ kind: 'rect', halfWidth: 50, halfHeight: 80 })
    expect(collisionOrthoShape('side', 50, 80)).toEqual({ kind: 'rect', halfWidth: 50, halfHeight: 80 })
  })

  it('front and side project identically -- both see the cylinder edge-on the same way', () => {
    expect(collisionOrthoShape('front', 12, 34)).toEqual(collisionOrthoShape('side', 12, 34))
  })
})

describe('sphereOrthoShape', () => {
  it('is a circle of the sphere radius, the same in every axis', () => {
    const expected = { kind: 'circle', radius: 225 }
    expect(sphereOrthoShape(225)).toEqual(expected)
  })
})

function actorWithRadii(name: string, radii: SceneActor['radii']): SceneActor {
  return {
    name,
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [0, 0, 0],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii,
    is_mover: false,
  }
}

describe('selectedRadiiActors', () => {
  const a = actorWithRadii('A', { collision_radius: 50, collision_height: 80, light_radius: null })
  const b = actorWithRadii('B', { collision_radius: null, collision_height: null, light_radius: 200 })
  const noRadii = actorWithRadii('C', null)
  const neitherGate = actorWithRadii('D', { collision_radius: null, collision_height: null, light_radius: null })

  it('is empty when nothing is selected, even if every actor has radii', () => {
    expect(selectedRadiiActors([a, b], new Set())).toEqual([])
  })

  it('returns only the selected actor(s) that also carry a resolved radius', () => {
    expect(selectedRadiiActors([a, b, noRadii], new Set(['A', 'C']))).toEqual([a])
  })

  it('supports a multi-actor selection', () => {
    expect(selectedRadiiActors([a, b, noRadii], new Set(['A', 'B']))).toEqual([a, b])
  })

  it('excludes a selected actor with radii resolved but both fields null (clears neither gate)', () => {
    expect(selectedRadiiActors([neitherGate], new Set(['D']))).toEqual([])
  })

  it('excludes a selected actor with no radii at all (a brush, or one clearing no gate)', () => {
    expect(selectedRadiiActors([noRadii], new Set(['C']))).toEqual([])
  })
})
