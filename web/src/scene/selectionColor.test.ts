import { describe, expect, it } from 'vitest'

import { CSG_WIRE_COLOR, resolveWireColor, scaleColor } from './selectionColor'

describe('CSG_WIRE_COLOR.semisolid', () => {
  it('matches preview.py\'s own established coral, not the banned third-party green', () => {
    expect(CSG_WIRE_COLOR.semisolid).toEqual([235, 120, 80])
  })

  it('stays visually distinct from mover at both the selected and dimmed shades', () => {
    const semisolid = resolveWireColor('semisolid', [0, 0, 0])
    const mover = resolveWireColor('mover', [0, 0, 0])
    expect(semisolid).not.toEqual(mover)
    expect(scaleColor(semisolid, 0.5)).not.toEqual(scaleColor(mover, 0.5))
  })
})
