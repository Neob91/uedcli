import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { resolveMaterialState } from './Viewport3D'

// Pins the render-decision -> three.js material mapping (render.rs's cull + blend), the web's whole
// "how to draw this group" residual now that the attrs are server-resolved.
describe('resolveMaterialState', () => {
  it('backface-culls (FrontSide) a single-sided group; DoubleSide when two_sided', () => {
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'opaque' }).side).toBe(THREE.FrontSide)
    expect(resolveMaterialState({ masked: false, twoSided: true, blend: 'opaque' }).side).toBe(THREE.DoubleSide)
  })

  it('alpha-tests a masked group at 0.5, none otherwise', () => {
    expect(resolveMaterialState({ masked: true, twoSided: false, blend: 'opaque' }).alphaTest).toBe(0.5)
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'opaque' }).alphaTest).toBe(0)
  })

  it('leaves an opaque group opaque (no transparent/blending override)', () => {
    const s = resolveMaterialState({ masked: false, twoSided: false, blend: 'opaque' })
    expect(s.transparent).toBeUndefined()
    expect(s.blending).toBeUndefined()
  })

  it('maps translucent -> half-opacity NormalBlending, modulated -> MultiplyBlending', () => {
    const t = resolveMaterialState({ masked: false, twoSided: false, blend: 'translucent' })
    expect(t.transparent).toBe(true)
    expect(t.blending).toBe(THREE.NormalBlending)
    expect(t.opacity).toBe(0.5)
    const m = resolveMaterialState({ masked: false, twoSided: false, blend: 'modulated' })
    expect(m.transparent).toBe(true)
    expect(m.blending).toBe(THREE.MultiplyBlending)
  })
})
