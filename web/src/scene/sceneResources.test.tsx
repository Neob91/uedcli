import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, ScenePayload, ScenePoly } from '../api'
import { buildGeometryData } from './geometry'
import { useBuiltGeometry } from './sceneResources'

function quad(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], // a unit square, 4 verts
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: -1,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: null,
    ...overrides,
  }
}

const EMPTY_ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

// This is a real assertion (catches a wiring mistake in the Part 0 Task 1 extraction), not a
// placeholder move-only smoke test: useBuiltGeometry's THREE.BufferGeometry must carry exactly as
// many positions as calling buildGeometryData directly on the same inputs produces.
describe('useBuiltGeometry', () => {
  it('builds a BufferGeometry whose position count matches buildGeometryData directly', () => {
    const scene: ScenePayload = { polys: [quad()], actors: [], geometry_pinned: false }
    const expected = buildGeometryData(scene.polys, EMPTY_ATLAS, null)

    const { result, unmount } = renderHook(() =>
      useBuiltGeometry(scene.polys, EMPTY_ATLAS, null, { map: new Map(), sprite: new Map() }, null),
    )

    const positionAttr = result.current.bufferGeometry.getAttribute('position')
    expect(positionAttr.count).toBe(expected.positions.length / 3)
    expect(result.current.triangleOwners.length).toBe(expected.triangleOwners.length)

    unmount()
  })

  it("unlitMaterials drops the lightmap so 'unlit' mode genuinely differs from 'lit' (review finding)", () => {
    // A lit poly (carries a LightmapFrame) with a real lightmapTexture supplied -- the shape that
    // makes buildGeometryData's group.lit true and useBuiltGeometry apply a lightMap in `materials`.
    const litPoly = quad({
      lightmap: { origin: [0, 0, 0], u_step: [1, 0, 0], v_step: [0, 1, 0], u_size: 4, v_size: 4 },
    })
    const scene: ScenePayload = { polys: [litPoly], actors: [], geometry_pinned: true }
    const lightmap: LightmapPayload = {
      width: 8, height: 8, intensity: 1,
      manifest: { '0': { x: 0, y: 0, w: 4, h: 4 } },
      png_base64: '',
    }
    const lightmapTexture = new THREE.Texture()

    const { result, unmount } = renderHook(() =>
      useBuiltGeometry(scene.polys, EMPTY_ATLAS, lightmap, { map: new Map(), sprite: new Map() }, lightmapTexture),
    )

    expect(result.current.materials.length).toBeGreaterThan(0)
    expect(result.current.unlitMaterials.length).toBe(result.current.materials.length)
    const litMat = result.current.materials[0] as THREE.MeshBasicMaterial
    const unlitMat = result.current.unlitMaterials[0] as THREE.MeshBasicMaterial
    expect(litMat.lightMap).toBe(lightmapTexture)
    expect(unlitMat.lightMap).toBeNull()

    unmount()
  })
})
