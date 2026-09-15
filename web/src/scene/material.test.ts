import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { CANVAS_COLOR_MANAGEMENT, resolveMaterialState } from './Viewport3D'

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

  it('sets premultipliedAlpha for modulated (three.js requires it for MultiplyBlending)', () => {
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'modulated' }).premultipliedAlpha).toBe(true)
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'translucent' }).premultipliedAlpha).toBeUndefined()
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'opaque' }).premultipliedAlpha).toBeUndefined()
  })

  it('disables depthWrite for translucent/modulated so they never occlude geometry drawn after them', () => {
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'translucent' }).depthWrite).toBe(false)
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'modulated' }).depthWrite).toBe(false)
    expect(resolveMaterialState({ masked: false, twoSided: false, blend: 'opaque' }).depthWrite).toBeUndefined()
  })
})

// render.rs shades by multiplying raw 0-255 texel bytes directly (no sRGB decode/encode anywhere).
// R3F's Canvas defaults still ENCODE the output (outputColorSpace = SRGBColorSpace) and
// auto-DECODE hex/THREE.Color literals, with nothing decoding the textures to match -- a
// decode-less-but-still-encoded round trip that moves every displayed value away from its exact
// source byte (brighter for textures, darker for literals like UNTEXTURED_GREY/MARKER_COLOR).
// `linear` + `legacy` (alongside the existing `flat`, which only disables tone mapping) turn all of
// that off, so a fullbright sprite (no vertex color, no lightmap) displays its exact source pixel.
describe('CANVAS_COLOR_MANAGEMENT', () => {
  it('disables tone mapping, output re-encoding, and literal color auto-decoding', () => {
    expect(CANVAS_COLOR_MANAGEMENT).toEqual({ flat: true, linear: true, legacy: true })
  })
})
