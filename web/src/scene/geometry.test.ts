import { describe, expect, it } from 'vitest'

import type { AtlasPayload, ScenePoly } from '../api'
import { buildGeometryData } from './geometry'

function quad(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], // a unit square, 4 verts
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: -1,
    masked: false,
    flags: 0,
    lightmap: null,
    ...overrides,
  }
}

const EMPTY_ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

describe('buildGeometryData', () => {
  it('fan-triangulates a quad into 2 triangles (6 verts) in one group', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(got.positions.length).toBe(6 * 3)
    expect(got.uvs.length).toBe(6 * 2)
    expect(got.groups).toEqual([{ texIndex: -1, masked: false, start: 0, count: 6 }])
  })

  it('groups by (texture, masked) pair -- one group per distinct texture', () => {
    const got = buildGeometryData(
      [quad({ tex_index: 0 }), quad({ tex_index: 1 }), quad({ tex_index: 0, masked: true })],
      { width: 16, height: 16, manifest: { '0': { x: 0, y: 0, w: 8, h: 8 }, '1': { x: 8, y: 0, w: 8, h: 8 } }, png_base64: '' },
    )
    // three distinct (texIndex, masked) buckets, in first-seen order, each 6 verts.
    expect(got.groups).toEqual([
      { texIndex: 0, masked: false, start: 0, count: 6 },
      { texIndex: 1, masked: false, start: 6, count: 6 },
      { texIndex: 0, masked: true, start: 12, count: 6 },
    ])
    expect(got.positions.length).toBe(18 * 3)
  })

  it('splits masked and non-masked polys of one texture into separate groups', () => {
    const atlas: AtlasPayload = { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8 } }, png_base64: '' }
    const got = buildGeometryData([quad({ tex_index: 0 }), quad({ tex_index: 0, masked: true })], atlas)
    expect(got.groups).toEqual([
      { texIndex: 0, masked: false, start: 0, count: 6 },
      { texIndex: 0, masked: true, start: 6, count: 6 },
    ])
  })

  it('skips a degenerate poly (fewer than 3 verts) without crashing', () => {
    const got = buildGeometryData([quad({ verts: [0, 0, 0, 1, 0, 0] })], EMPTY_ATLAS)
    expect(got.positions.length).toBe(0)
    expect(got.groups).toEqual([])
  })

  it('tiles UVs raw over the texture size -- a surface spanning 8 tiles goes 0..8 in U, not collapsed', () => {
    // A floor quad 64 units wide over an 8x8 texture spans 8 tiles: U runs 0..8, never a single
    // repeated texel (the atlas-mod bug that collapsed every corner to the same UV).
    const atlas: AtlasPayload = { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8 } }, png_base64: '' }
    const floor = quad({ verts: [0, 0, 0, 64, 0, 0, 64, 64, 0, 0, 64, 0], tex_index: 0 })
    const got = buildGeometryData([floor], atlas)
    const us: number[] = []
    for (let i = 0; i < got.uvs.length; i += 2) us.push(got.uvs[i])
    expect(Math.min(...us)).toBeCloseTo(0)
    expect(Math.max(...us)).toBeCloseTo(8) // 64 texels / 8-wide texture = 8 tiles, not mod'd to 0
  })

  it('leaves an untextured poly (tex_index -1) at UV (0,0)', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(Array.from(got.uvs)).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
  })
})
