import { describe, expect, it } from 'vitest'

import { collisionOrthoShape, sphereOrthoShape } from './radiiProjection'

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
