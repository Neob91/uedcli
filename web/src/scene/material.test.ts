import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { CANVAS_COLOR_MANAGEMENT } from './viewportRender'
import { resolveMaterialState } from './sceneResources'

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

  it('maps translucent -> true additive blend (dest+src), matching render.rs exactly', () => {
    const t = resolveMaterialState({ masked: false, twoSided: false, blend: 'translucent' })
    expect(t.transparent).toBe(true)
    expect(t.blending).toBe(THREE.AdditiveBlending)
    expect(t.opacity).toBeUndefined() // full opacity -- a half-opacity src would darken a black texel
  })

  it('maps modulated -> MultiplyBlending with the material color doubled (2x, approximating D3D modulate-2x)', () => {
    const m = resolveMaterialState({ masked: false, twoSided: false, blend: 'modulated' })
    expect(m.transparent).toBe(true)
    expect(m.blending).toBe(THREE.MultiplyBlending)
    expect(m.color).toEqual(new THREE.Color(2, 2, 2))
  })

  // "Sunglasses" bug regression (2026-09-15): a stock NPC's "no glasses" placeholder is flat
  // 50%-grey under a Modulated material and flat black under a Translucent one -- both must blend
  // to NO visible change, or every NPC renders a dark glasses-shaped patch by default.
  it('leaves a 50%-grey modulated placeholder neutral once shaded (the "no glasses frames" case)', () => {
    const m = resolveMaterialState({ masked: false, twoSided: false, blend: 'modulated' })
    const color = m.color as THREE.Color
    // MultiplyBlending's src is (material.color * texel), clamped to [0,1] before the blend stage;
    // a 50%-grey texel (0.5) doubled by this material's color is 1.0 -- multiplying the destination
    // by 1.0 is a true no-op, matching UE1's real `dest*128/128=dest`.
    const texel = 0.5
    expect(Math.min(1, color.r * texel)).toBe(1)
  })

  it('leaves a black translucent placeholder invisible (the "no glasses lenses" case)', () => {
    // AdditiveBlending's result is dest + src*opacity; opacity is full (1) and src (black) is 0, so
    // the destination is exactly unchanged -- matching UE1's real `dest+0=dest`.
    const t = resolveMaterialState({ masked: false, twoSided: false, blend: 'translucent' })
    expect(t.opacity ?? 1).toBe(1)
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
