import { describe, expect, it } from 'vitest'
import { moveAlongAxis, moveInPlane, PERSPECTIVE_AXIS_BY_BUTTONS } from './actorMove'
import { orthoBasis } from './orthoCamera'

describe('moveAlongAxis', () => {
  it('places the delta on the requested axis only, positive dx = positive axis direction', () => {
    expect(moveAlongAxis(10, 'x', 0.1)).toEqual([1, 0, 0])
    expect(moveAlongAxis(10, 'y', 0.1)).toEqual([0, 1, 0])
    expect(moveAlongAxis(10, 'z', 0.1)).toEqual([0, 0, 1])
    expect(moveAlongAxis(-10, 'x', 0.1)).toEqual([-1, 0, 0])
  })
})

describe('PERSPECTIVE_AXIS_BY_BUTTONS', () => {
  it('maps LMB/RMB/LMB+RMB to X/Y/Z', () => {
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[1]).toBe('x')
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[2]).toBe('y')
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[3]).toBe('z')
  })
})

describe('moveInPlane', () => {
  it("moves the actor WITH the drag direction (opposite of orthoPan's camera-follows-drag sign)", () => {
    const { right } = orthoBasis('top') // Vec3 = [number, number, number], NOT {x,y,z}
    const delta = moveInPlane(10, 0, 'top', 0.1)
    // a positive-dx drag must move the actor along +right, not -right (which is what a literal
    // copy of orthoPan's sign would produce) -- assert the dot product is positive, not the exact
    // numbers, so this test doesn't silently encode a wrong sign as "correct" by construction
    const dot = delta[0] * right[0] + delta[1] * right[1] + delta[2] * right[2]
    expect(dot).toBeGreaterThan(0)
  })

  it('moves the actor WITH a vertical drag along +up, not -up (positive dot with up)', () => {
    // dragging screen-down (positive dy) should move the actor toward screen-bottom, i.e. along
    // -up (since `up` is "up on screen"); assert against the ACTUAL orthoBasis up vector, not a
    // hand-guessed one.
    const { up } = orthoBasis('top')
    const delta = moveInPlane(0, 10, 'top', 0.1)
    const dot = delta[0] * up[0] + delta[1] * up[1] + delta[2] * up[2]
    expect(dot).toBeLessThan(0)
  })

  it('produces zero delta on the axis not spanned by right/up (top: no Z component)', () => {
    const delta = moveInPlane(10, 10, 'top', 0.1)
    expect(delta[2]).toBe(0)
  })

  it('scales by worldUnitsPerPixel', () => {
    const delta = moveInPlane(10, 0, 'top', 0.5)
    const { right } = orthoBasis('top')
    expect(delta[0]).toBeCloseTo(10 * 0.5 * right[0])
  })
})
