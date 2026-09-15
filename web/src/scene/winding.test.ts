// The one test that ties `geometry.ts`'s `REVERSE_FAN` to the camera that draws it.
//
// Two separate pieces decide which face of a wall you see, and neither can be verified alone:
//   1. `geometry.ts` emits each poly's triangles in some vertex order (`REVERSE_FAN`).
//   2. `Viewport3D.tsx`'s `applyCameraPose` mirrors the projection's NDC-x term, which reverses
//      every triangle's apparent screen winding. three.js never compensates for that -- it flips
//      `frontFace` only from a drawn OBJECT's own `matrixWorld` determinant, never the camera's.
// Flip either one alone and every single-sided surface culls the wrong face. That is exactly what
// happened: `REVERSE_FAN` was verified correct against a pre-mirror camera, the mirror landed in a
// different change, and the two silently stopped agreeing (CSG subtracts rendered as solid blocks).
//
// The ground truth is `render.rs`'s own cull, `light::light_in_front`: a non-two-sided poly is
// visible iff `(camera - verts[0]) . N >= -1`, with `N` the unit Newell normal of the ring over the
// raw world coordinates. three.js `FrontSide` keeps a triangle iff its NDC signed area is positive
// (`gl.frontFace(CCW)` + cull BACK). This test asserts the two agree for every emitted triangle.
import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import type { AtlasPayload, ScenePoly } from '../api'
import { cameraBasis } from './camera'
import type { CameraPose } from './camera'
import { buildGeometryData } from './geometry'
import { applyCameraPose } from './Viewport3D'

const EMPTY_ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

function poly(verts: number[]): ScenePoly {
  return {
    verts, base: [0, 0, 0], tu: [1, 0, 0], tv: [0, 1, 0], pan: [0, 0], tex_index: -1,
    masked: false, two_sided: false, blend: 'opaque', flags: 0, lightmap: null, owner: null,
  }
}

/** Unit Newell normal of a flat vertex ring -- `render.rs`'s `newell_normal`, normalized. */
function newellNormal(verts: number[]): [number, number, number] {
  const n = verts.length / 3
  let x = 0
  let y = 0
  let z = 0
  for (let i = 0; i < n; i++) {
    const a = i * 3
    const b = ((i + 1) % n) * 3
    x += (verts[a + 1] - verts[b + 1]) * (verts[a + 2] + verts[b + 2])
    y += (verts[a + 2] - verts[b + 2]) * (verts[a] + verts[b])
    z += (verts[a] - verts[b]) * (verts[a + 1] + verts[b + 1])
  }
  const len = Math.hypot(x, y, z)
  return [x / len, y / len, z / len]
}

/** `render.rs`'s `light::light_in_front` with the camera standing in for the light, non-two-sided. */
function visiblePerRenderRs(verts: number[], camera: [number, number, number]): boolean {
  const n = newellNormal(verts)
  return (camera[0] - verts[0]) * n[0] + (camera[1] - verts[1]) * n[1] + (camera[2] - verts[2]) * n[2] >= -1
}

/** three.js `FrontSide`'s own verdict for one emitted triangle: NDC signed area > 0. */
function frontFacingInThree(positions: Float32Array, triangle: number, camera: THREE.Camera): boolean {
  const p = [0, 1, 2].map((k) => {
    const i = (triangle * 3 + k) * 3
    return new THREE.Vector3(positions[i], positions[i + 1], positions[i + 2]).project(camera)
  })
  return (p[1].x - p[0].x) * (p[2].y - p[0].y) - (p[1].y - p[0].y) * (p[2].x - p[0].x) > 0
}

// An axis-aligned quad, 400 UU across, centred `depth` UU straight ahead of the camera, spanned by
// `u`/`v` (so its own normal is `u x v`, and reversing the ring flips which side faces the camera).
function quadAhead(
  pose: CameraPose,
  u: [number, number, number],
  v: [number, number, number],
  depth: number,
  reversed: boolean,
): number[] {
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  const c = [0, 1, 2].map((i) => pose.position[i] + forward[i] * depth)
  const s = 200
  const ring = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ].map(([a, b]) => [0, 1, 2].map((i) => c[i] + u[i] * a * s + v[i] * b * s))
  if (reversed) ring.reverse()
  return ring.flat()
}

const POSES: CameraPose[] = [
  { position: [0, 0, 0], pitch: 0, yaw: 0 },
  { position: [0, -500, 200], pitch: -10, yaw: 90 }, // Viewport3D's own INITIAL_POSE
  { position: [-300, 50, 700], pitch: -75, yaw: 0 },
  { position: [400, 400, -100], pitch: 20, yaw: 205 },
]

// Wall orientations whose normals are well off the view axis at every pose above, so no sample is
// edge-on (where the two rules legitimately disagree inside float noise).
const SPANS: [[number, number, number], [number, number, number]][] = [
  [[0, 1, 0], [0, 0, 1]],
  [[0, 0, 1], [1, 0, 0]],
  [[1, 0, 0], [0, 1, 0]],
]

describe('REVERSE_FAN vs the camera that draws it', () => {
  it("culls exactly the faces render.rs culls, through Viewport3D's own camera", () => {
    let checked = 0
    for (const pose of POSES) {
      const camera = new THREE.PerspectiveCamera(75, 16 / 9, 1, 131072)
      applyCameraPose(camera, pose)
      for (const [u, v] of SPANS) {
        for (const reversed of [false, true]) {
          const verts = quadAhead(pose, u, v, 900, reversed)
          const { forward } = cameraBasis(pose.pitch, pose.yaw)
          const n = newellNormal(verts)
          if (Math.abs(n[0] * forward[0] + n[1] * forward[1] + n[2] * forward[2]) < 0.15) continue // edge-on
          const want = visiblePerRenderRs(verts, pose.position)
          const geo = buildGeometryData([poly(verts)], EMPTY_ATLAS)
          for (let t = 0; t < geo.triangleOwners.length; t++) {
            expect(frontFacingInThree(geo.positions, t, camera)).toBe(want)
            checked++
          }
        }
      }
    }
    expect(checked).toBeGreaterThan(20) // the loop above actually ran, not silently skipped
  })
})
