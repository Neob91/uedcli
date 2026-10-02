import { describe, expect, it } from 'vitest'

import type { AtlasPayload, LightmapPayload, ScenePoly } from '../api'
import { buildEdgePickData, buildGeometryData, buildOwnerVertexRanges, patchOwnerPositions } from './geometry'

function quad(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], // a unit square, 4 verts
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    normal: [0, 0, 1],
    area: 100,
    tex_index: -1,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: null,
    i_brush_poly: null,
    ...overrides,
  }
}

const EMPTY_ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

describe('buildGeometryData', () => {
  it('fan-triangulates a quad into 2 triangles (6 verts) in one group', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(got.positions.length).toBe(6 * 3)
    expect(got.uvs.length).toBe(6 * 2)
    expect(got.uv1.length).toBe(6 * 2)
    expect(got.colors.length).toBe(6 * 3)
    expect(got.groups).toEqual([{ texIndex: -1, masked: false, twoSided: false, blend: 'opaque', lit: false, start: 0, count: 6 }])
    expect(got.triangleOwners.length).toBe(2) // one entry per triangle, not per vertex
  })

  it('tags each triangle with its poly owner, in the same order as positions', () => {
    const got = buildGeometryData(
      [quad({ owner: 'Room' }), quad({ tex_index: 0, owner: 'Inner' })],
      { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null } }, png_base64: '' },
    )
    // 2 groups (different tex_index), 2 triangles each -> 4 total, owner aligned per-triangle.
    expect(got.triangleOwners).toEqual(['Room', 'Room', 'Inner', 'Inner'])
  })

  it('tags a poly with no resolved owner as null, not a crash', () => {
    const got = buildGeometryData([quad({ owner: null })], EMPTY_ATLAS)
    expect(got.triangleOwners).toEqual([null, null])
  })

  it('tags each triangle with its poly\'s i_brush_poly (BRUSH:IDX, not an array position)', () => {
    const got = buildGeometryData(
      [quad({ owner: 'Room', i_brush_poly: 4 }), quad({ tex_index: 0, owner: 'Inner', i_brush_poly: 2 })],
      { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null } }, png_base64: '' },
    )
    // 2 groups (different tex_index), 2 triangles each -- poly 0 (Room:4) then poly 1 (Inner:2).
    expect(got.trianglePolyIndex).toEqual([4, 4, 2, 2])
  })

  it('lets several disjoint ScenePolys share one i_brush_poly -- CSG-split-fragment grouping', () => {
    // Two fragments of the SAME authored polygon (e.g. a wall split by a niche brush) carry the
    // same owner + i_brush_poly even though they're separate ScenePoly entries.
    const got = buildGeometryData(
      [quad({ owner: 'Wall', i_brush_poly: 1 }), quad({ owner: 'Wall', i_brush_poly: 1 })],
      EMPTY_ATLAS,
    )
    expect(got.trianglePolyIndex).toEqual([1, 1, 1, 1])
  })

  it('tags a poly with no i_brush_poly (a mesh actor, no brush.polys) as null', () => {
    const got = buildGeometryData([quad({ owner: 'Crate', i_brush_poly: null })], EMPTY_ATLAS)
    expect(got.trianglePolyIndex).toEqual([null, null])
  })

  it('groups by (texture, masked) pair -- one group per distinct texture', () => {
    const got = buildGeometryData(
      [quad({ tex_index: 0 }), quad({ tex_index: 1 }), quad({ tex_index: 0, masked: true })],
      { width: 16, height: 16, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null }, '1': { x: 8, y: 0, w: 8, h: 8, name: null } }, png_base64: '' },
    )
    expect(got.groups).toEqual([
      { texIndex: 0, masked: false, twoSided: false, blend: 'opaque', lit: false, start: 0, count: 6 },
      { texIndex: 1, masked: false, twoSided: false, blend: 'opaque', lit: false, start: 6, count: 6 },
      { texIndex: 0, masked: true, twoSided: false, blend: 'opaque', lit: false, start: 12, count: 6 },
    ])
    expect(got.positions.length).toBe(18 * 3)
  })

  it('splits masked and non-masked polys of one texture into separate groups', () => {
    const atlas: AtlasPayload = { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null } }, png_base64: '' }
    const got = buildGeometryData([quad({ tex_index: 0 }), quad({ tex_index: 0, masked: true })], atlas)
    expect(got.groups).toEqual([
      { texIndex: 0, masked: false, twoSided: false, blend: 'opaque', lit: false, start: 0, count: 6 },
      { texIndex: 0, masked: true, twoSided: false, blend: 'opaque', lit: false, start: 6, count: 6 },
    ])
  })

  it('skips a degenerate poly (fewer than 3 verts) without crashing', () => {
    const got = buildGeometryData([quad({ verts: [0, 0, 0, 1, 0, 0] })], EMPTY_ATLAS)
    expect(got.positions.length).toBe(0)
    expect(got.groups).toEqual([])
  })

  it('tiles UVs raw over the texture size -- a surface spanning 8 tiles goes 0..8 in U, not collapsed', () => {
    const atlas: AtlasPayload = { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null } }, png_base64: '' }
    const floor = quad({ verts: [0, 0, 0, 64, 0, 0, 64, 64, 0, 0, 64, 0], tex_index: 0 })
    const got = buildGeometryData([floor], atlas)
    const us: number[] = []
    for (let i = 0; i < got.uvs.length; i += 2) us.push(got.uvs[i])
    expect(Math.min(...us)).toBeCloseTo(0)
    expect(Math.max(...us)).toBeCloseTo(8) // 64 texels / 8-wide texture = 8 tiles, not mod'd to 0
  })

  it('leaves an untextured poly (tex_index -1) at base UV (0,0)', () => {
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    expect(Array.from(got.uvs)).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
  })

  it('shades an unlit poly per-face with the KEY_LIGHT flat shade (matching render.rs)', () => {
    // The XY-plane quad's Newell normal is (0,0,2); |n·KEY_LIGHT|/|n| = 0.707, so shade =
    // 0.55 + 0.45*0.707 = 0.8682 -- the same grey in all 3 channels, all 6 verts.
    const got = buildGeometryData([quad()], EMPTY_ATLAS)
    for (let i = 0; i < got.colors.length; i++) expect(got.colors[i]).toBeCloseTo(0.8682, 3)
  })

  const LIT_ATLAS: LightmapPayload = {
    width: 16,
    height: 16,
    intensity: 2,
    manifest: { '0': { x: 1, y: 1, w: 2, h: 2 } },
    png_base64: '',
  }

  it('emits a lit group with white vertex colours and atlas uv1 for a poly with a lightmap+rect', () => {
    const lit = quad({ lightmap: { origin: [0, 0, 0], u_step: [1, 0, 0], v_step: [0, 1, 0], u_size: 2, v_size: 2 } })
    const got = buildGeometryData([lit], EMPTY_ATLAS, LIT_ATLAS)
    expect(got.groups).toEqual([{ texIndex: -1, masked: false, twoSided: false, blend: 'opaque', lit: true, start: 0, count: 6 }])
    // Lit verts carry white colour (the lightmap does the shading, not the flat shade).
    for (let i = 0; i < got.colors.length; i++) expect(got.colors[i]).toBe(1)
    // Vertex v0 at world (0,0,0): lu=lv=0 -> atlas texel centre (rect.x+0.5)/16 = 1.5/16.
    expect(got.uv1[0]).toBeCloseTo(1.5 / 16, 5)
    expect(got.uv1[1]).toBeCloseTo(1.5 / 16, 5)
  })

  it('treats a poly with a lightmap frame but no packed rect as unlit', () => {
    const lit = quad({ lightmap: { origin: [0, 0, 0], u_step: [1, 0, 0], v_step: [0, 1, 0], u_size: 2, v_size: 2 } })
    const noRect: LightmapPayload = { width: 16, height: 16, intensity: 2, manifest: {}, png_base64: '' }
    const got = buildGeometryData([lit], EMPTY_ATLAS, noRect)
    expect(got.groups[0].lit).toBe(false)
  })

  it('splits a lit and an unlit poly of the same texture into separate groups', () => {
    const atlas: AtlasPayload = { width: 8, height: 8, manifest: { '0': { x: 0, y: 0, w: 8, h: 8, name: null } }, png_base64: '' }
    const litFrame = { origin: [0, 0, 0], u_step: [1, 0, 0], v_step: [0, 1, 0], u_size: 2, v_size: 2 }
    const got = buildGeometryData(
      [quad({ tex_index: 0, lightmap: litFrame }), quad({ tex_index: 0 })],
      atlas,
      LIT_ATLAS,
    )
    expect(got.groups).toEqual([
      { texIndex: 0, masked: false, twoSided: false, blend: 'opaque', lit: true, start: 0, count: 6 },
      { texIndex: 0, masked: false, twoSided: false, blend: 'opaque', lit: false, start: 6, count: 6 },
    ])
  })
})

// GUI-PARITY.md "Mesh selection in 2D/3D wireframe mode vs UED22" -- the raycastable EDGE-only
// geometry a mesh actor picks by in wireframe mode (instead of `buildGeometryData`'s own filled
// triangles), with per-edge owner data `THREE.WireframeGeometry`'s own edge-dedup would discard.
describe('buildEdgePickData', () => {
  it('emits 3 edges (6 verts) per source triangle, each tagged with that triangle\'s own owner/polyIndex', () => {
    const geo = buildGeometryData([quad({ owner: 'Crate0', i_brush_poly: 3 })], EMPTY_ATLAS)
    const got = buildEdgePickData(geo)
    expect(geo.triangleOwners.length).toBe(2) // a quad fan-triangulates to 2 triangles
    expect(got.positions.length).toBe(2 * 18) // 3 edges * 2 verts * 3 coords, per triangle
    expect(got.edgeOwners).toEqual(['Crate0', 'Crate0', 'Crate0', 'Crate0', 'Crate0', 'Crate0'])
    expect(got.edgePolyIndex).toEqual([3, 3, 3, 3, 3, 3])
  })

  it('the first triangle\'s 3 edges connect its own 3 vertices, v0-v1, v1-v2, v2-v0', () => {
    const geo = buildGeometryData([quad()], EMPTY_ATLAS)
    const got = buildEdgePickData(geo)
    const v0 = Array.from(geo.positions.slice(0, 3))
    const v1 = Array.from(geo.positions.slice(3, 6))
    const v2 = Array.from(geo.positions.slice(6, 9))
    expect(Array.from(got.positions.slice(0, 6))).toEqual([...v0, ...v1])
    expect(Array.from(got.positions.slice(6, 12))).toEqual([...v1, ...v2])
    expect(Array.from(got.positions.slice(12, 18))).toEqual([...v2, ...v0])
  })

  it('an unresolved owner/polyIndex triangle produces edges with the same null owner/polyIndex', () => {
    const geo = buildGeometryData([quad({ owner: null, i_brush_poly: null })], EMPTY_ATLAS)
    const got = buildEdgePickData(geo)
    expect(got.edgeOwners).toEqual([null, null, null, null, null, null])
    expect(got.edgePolyIndex).toEqual([null, null, null, null, null, null])
  })
})

// Perf fix (live report: "moving actors is super jittery and slow"): dragging a mesh actor used to
// rebuild an entire level's geometry every pointer-move frame. These two functions live-patch an
// already-built geometry's position buffer in place instead.
describe('buildOwnerVertexRanges', () => {
  it('maps each owner to the flat float offset of each of its own primitives (3 floats/vertex)', () => {
    // 2 triangles (owned by A, then B), vertsPerPrimitive=3 -> 9 floats each.
    const owners = ['A', 'B']
    expect(buildOwnerVertexRanges(owners, 3)).toEqual(
      new Map([
        ['A', [0]],
        ['B', [9]],
      ]),
    )
  })

  it("scatters one owner's primitives across non-contiguous starts, in source order", () => {
    const owners = ['A', 'B', 'A', 'B']
    expect(buildOwnerVertexRanges(owners, 3)).toEqual(
      new Map([
        ['A', [0, 18]],
        ['B', [9, 27]],
      ]),
    )
  })

  it('a null owner (an out-of-range CSG join) contributes no range', () => {
    expect(buildOwnerVertexRanges([null, 'A', null], 3)).toEqual(new Map([['A', [9]]]))
  })

  it('vertsPerPrimitive=2 (edges) uses a 6-float stride', () => {
    expect(buildOwnerVertexRanges(['A', 'A'], 2)).toEqual(new Map([['A', [0, 6]]]))
  })
})

describe('patchOwnerPositions', () => {
  it("translates one owner's triangle by delta, computed from basePositions, leaving other vertices untouched", () => {
    const base = new Float32Array([0, 0, 0, 10, 0, 0, 10, 10, 0, /* second (untouched) triangle */ 100, 100, 100, 101, 100, 100, 101, 101, 100])
    const positions = base.slice()
    patchOwnerPositions(positions, base, [0], 3, [5, 0, 0])
    expect(Array.from(positions.slice(0, 9))).toEqual([5, 0, 0, 15, 0, 0, 15, 10, 0])
    expect(Array.from(positions.slice(9, 18))).toEqual(Array.from(base.slice(9, 18))) // untouched
  })

  it('re-applying with a DIFFERENT delta recomputes from basePositions, never compounding on the previous patch', () => {
    const base = new Float32Array([0, 0, 0, 10, 0, 0, 10, 10, 0])
    const positions = base.slice()
    patchOwnerPositions(positions, base, [0], 3, [5, 0, 0])
    patchOwnerPositions(positions, base, [0], 3, [1, 0, 0]) // NOT 5+1
    expect(Array.from(positions.slice(0, 3))).toEqual([1, 0, 0])
  })

  it('delta [0, 0, 0] resets a previously-patched primitive back to basePositions exactly (un-staging)', () => {
    const base = new Float32Array([0, 0, 0, 10, 0, 0, 10, 10, 0])
    const positions = base.slice()
    patchOwnerPositions(positions, base, [0], 3, [5, 5, 5])
    patchOwnerPositions(positions, base, [0], 3, [0, 0, 0])
    expect(Array.from(positions)).toEqual(Array.from(base))
  })

  it('patches every start in a multi-range (scattered) owner', () => {
    const base = new Float32Array(36) // 4 triangles' worth, all zeros
    const positions = base.slice()
    patchOwnerPositions(positions, base, [0, 18], 3, [1, 2, 3])
    expect(Array.from(positions.slice(0, 9))).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3])
    expect(Array.from(positions.slice(9, 18))).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0]) // untouched
    expect(Array.from(positions.slice(18, 27))).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3])
  })
})
