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
  it('fan-triangulates a quad into 2 triangles (6 verts)', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(got.positions.length).toBe(6 * 3)
    expect(got.uvs.length).toBe(6 * 2)
    expect(got.groups.nonMasked).toEqual({ start: 0, count: 6 })
    expect(got.groups.masked).toEqual({ start: 6, count: 0 })
  })

  it('splits masked and non-masked polys into separate contiguous groups', () => {
    const got = buildGeometryData([quad({ masked: false }), quad({ masked: true })], EMPTY_ATLAS)
    expect(got.groups.nonMasked).toEqual({ start: 0, count: 6 })
    expect(got.groups.masked).toEqual({ start: 6, count: 6 })
    expect(got.positions.length).toBe(12 * 3)
  })

  it('skips a degenerate poly (fewer than 3 verts) without crashing', () => {
    const got = buildGeometryData([quad({ verts: [0, 0, 0, 1, 0, 0] })], EMPTY_ATLAS)
    expect(got.positions.length).toBe(0)
  })

  it('maps a textured poly into its atlas rect, tiling texel coordinates', () => {
    const atlas: AtlasPayload = {
      width: 100,
      height: 100,
      manifest: { '0': { x: 10, y: 20, w: 8, h: 8 } },
      png_base64: '',
    }
    // The quad's second vertex (1,0,0) is 1 unit along `tu` from `base` -- inside the 8x8 tile.
    const got = buildGeometryData([quad({ tex_index: 0 })], atlas)
    // First triangle is verts [0, 1, 2]; vertex index 1 (the quad's second vertex) is the 2nd
    // entry emitted (uv index 1).
    const u = got.uvs[1 * 2]
    const v = got.uvs[1 * 2 + 1]
    expect(u).toBeCloseTo((10 + 1) / 100)
    expect(v).toBeCloseTo(20 / 100)
  })

  it('leaves an untextured poly (tex_index -1) at UV (0,0)', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(Array.from(got.uvs)).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
  })
})
