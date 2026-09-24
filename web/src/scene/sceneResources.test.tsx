import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, ScenePayload, ScenePoly } from '../api'
import type { Vec3 } from './camera'
import { buildGeometryData } from './geometry'
import { useBuiltGeometry, usePatchedMeshPositions } from './sceneResources'

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

// This is a real assertion (catches a wiring mistake in the Part 0 Task 1 extraction), not a
// placeholder move-only smoke test: useBuiltGeometry's THREE.BufferGeometry must carry exactly as
// many positions as calling buildGeometryData directly on the same inputs produces.
describe('useBuiltGeometry', () => {
  it('builds a BufferGeometry whose position count matches buildGeometryData directly', () => {
    const scene: ScenePayload = { polys: [quad()], actors: [], geometry_pinned: false, enums: {} }
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
    const scene: ScenePayload = { polys: [litPoly], actors: [], geometry_pinned: true, enums: {} }
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

// Perf fix (live report: "moving actors is super jittery and slow") -- the hook that replaced a
// full per-frame geometry rebuild with an in-place position-buffer patch. `SceneResourcesContext.test.tsx`
// already covers this end-to-end (staged move -> correct final positions); these tests isolate the
// hook itself: does it actually avoid replacing the geometry, and does re-staging/un-staging behave.
describe('usePatchedMeshPositions', () => {
  function geometryWithPositions(positions: number[]): THREE.BufferGeometry {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3))
    return geo
  }

  it('never replaces the position attribute or its underlying array -- patches in place', () => {
    const geo = geometryWithPositions([0, 0, 0, 1, 0, 0, 1, 1, 0])
    const attrBefore = geo.getAttribute('position')
    const arrayBefore = attrBefore.array

    const { rerender } = renderHook(
      ({ deltas }) => usePatchedMeshPositions(geo, ['MeshA'], 3, new Set(['MeshA']), deltas),
      { initialProps: { deltas: new Map<string, Vec3>([['MeshA', [5, 0, 0]]]) } },
    )
    rerender({ deltas: new Map([['MeshA', [10, 0, 0]]]) })

    expect(geo.getAttribute('position')).toBe(attrBefore) // same BufferAttribute object
    expect(geo.getAttribute('position').array).toBe(arrayBefore) // same underlying Float32Array
  })

  it("patches an owner's own vertices by its delta, computed from the ORIGINAL (pre-patch) snapshot, and bumps the attribute's GPU-upload version", () => {
    const geo = geometryWithPositions([0, 0, 0, 1, 0, 0, 1, 1, 0])
    const versionBefore = (geo.getAttribute('position') as THREE.BufferAttribute).version
    renderHook(() => usePatchedMeshPositions(geo, ['MeshA'], 3, new Set(['MeshA']), new Map([['MeshA', [5, 0, 0]]])))
    const positions = geo.getAttribute('position').array as Float32Array
    expect(Array.from(positions)).toEqual([5, 0, 0, 6, 0, 0, 6, 1, 0])
    // `needsUpdate` is write-only (three.js exposes no readable getter) -- setting it to `true`
    // increments `.version`, which IS readable, so that's what proves the setter actually fired.
    expect((geo.getAttribute('position') as THREE.BufferAttribute).version).toBeGreaterThan(versionBefore)
  })

  it('un-staging (delta removed) resets the owner back to its original snapshot exactly', () => {
    const geo = geometryWithPositions([0, 0, 0, 1, 0, 0, 1, 1, 0])
    const { rerender } = renderHook(
      ({ deltas }) => usePatchedMeshPositions(geo, ['MeshA'], 3, new Set(['MeshA']), deltas),
      { initialProps: { deltas: new Map<string, Vec3>([['MeshA', [5, 5, 5]]]) } },
    )
    rerender({ deltas: new Map() }) // MeshA no longer staged
    expect(Array.from(geo.getAttribute('position').array as Float32Array)).toEqual([0, 0, 0, 1, 0, 0, 1, 1, 0])
  })

  it('never touches an owner outside patchableNames, even if a caller mistakenly staged it (the brush-safety net)', () => {
    // Two triangles: MeshA (patchable) then BrushA (not -- simulates the MAIN buffer, which mixes
    // brush and mesh-actor owners; only meshActorNames is ever passed as patchableNames for it).
    const geo = geometryWithPositions([0, 0, 0, 1, 0, 0, 1, 1, 0, 10, 10, 10, 11, 10, 10, 11, 11, 10])
    renderHook(() =>
      usePatchedMeshPositions(
        geo,
        ['MeshA', 'BrushA'],
        3,
        new Set(['MeshA']), // patchableNames excludes BrushA
        new Map([
          ['MeshA', [5, 0, 0]],
          ['BrushA', [5, 0, 0]], // present in deltas, but not patchable here
        ]),
      ),
    )
    const positions = Array.from(geo.getAttribute('position').array as Float32Array)
    expect(positions.slice(0, 9)).toEqual([5, 0, 0, 6, 0, 0, 6, 1, 0]) // MeshA patched
    expect(positions.slice(9, 18)).toEqual([10, 10, 10, 11, 10, 10, 11, 11, 10]) // BrushA untouched
  })

  it('a null owner (an out-of-range CSG join) is never patched', () => {
    const geo = geometryWithPositions([0, 0, 0, 1, 0, 0, 1, 1, 0])
    renderHook(() => usePatchedMeshPositions(geo, [null], 3, new Set(['MeshA']), new Map([['MeshA', [5, 0, 0]]])))
    expect(Array.from(geo.getAttribute('position').array as Float32Array)).toEqual([0, 0, 0, 1, 0, 0, 1, 1, 0])
  })
})
