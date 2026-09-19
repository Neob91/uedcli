import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { RadiiOverlays } from './RadiiOverlays'

// Regression for GUI-PARITY.md "Radii overlay colors" divergence 1 (closed 2026-09-18,
// `dev/docs/board/done/gui-light-radius-is-a-camera-facing-circle-not/`): real UED22 draws the
// perspective-pane light radius as a `URender::DrawCircle` built from the CAMERA's own axes (a
// billboard), not a fixed world-plane sphere silhouette. This checks the actual geometry the
// `LightRadiusCircle3D` component (RadiiOverlays.tsx) produces: its plane must track the camera's
// forward direction across different camera poses, not sit fixed in world space.
const LIGHT = { collision_radius: null, collision_height: null, light_radius: 300, sound_radius: null }

function actor(radii: SceneActor['radii']): SceneActor {
  return {
    name: 'A',
    cls: 'Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'A',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii,
    is_mover: false,
    directional_arrow: null,
  }
}

/** Reads back the circle's own plane normal from its rendered line-segment geometry -- two
 * non-parallel chords from the (world-origin-centered) ring, cross-producted, normalized. Sign is
 * ambiguous (a plane has two normals); callers compare via `Math.abs(dot)`. */
function planeNormalFromGeometry(geometry: THREE.BufferGeometry): THREE.Vector3 {
  const arr = geometry.attributes.position.array as Float32Array
  const p0 = new THREE.Vector3(arr[0], arr[1], arr[2])
  const p1 = new THREE.Vector3(arr[3], arr[4], arr[5])
  // A point a quarter of the way around the ring -- far enough from p0/p1 to avoid a near-parallel
  // (numerically unstable) cross product.
  const quarter = Math.floor(arr.length / 4 / 6) * 6
  const p2 = new THREE.Vector3(arr[quarter], arr[quarter + 1], arr[quarter + 2])
  return new THREE.Vector3().subVectors(p1, p0).cross(new THREE.Vector3().subVectors(p2, p0)).normalize()
}

/** The plane normal a faithful camera-facing circle at the world origin must have: the camera's own
 * forward direction, reflected the same way `viewportRender.ts`'s `applyCameraPose` poses the camera
 * (Y negated) -- see `RadiiOverlays.tsx`'s `LightRadiusCircle3D` doc comment for why. */
function expectedNormal(camera: THREE.Camera): THREE.Vector3 {
  const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion)
  forward.y *= -1
  return forward.normalize()
}

async function renderCircleGeometry(camera: THREE.PerspectiveCamera): Promise<THREE.BufferGeometry> {
  const renderer = await ReactThreeTestRenderer.create(
    <RadiiOverlays actors={[actor(LIGHT)]} view="perspective" selectedNames={new Set(['A'])} />,
    { camera },
  )
  await renderer.advanceFrames(1, 0.016)
  let found: THREE.BufferGeometry | undefined
  renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
    const line = o as THREE.LineSegments
    if (line.isLineSegments) found = line.geometry
  })
  if (!found) throw new Error('no lineSegments found')
  return found
}

describe('LightRadiusCircle3D camera-facing behavior', () => {
  it('faces the camera looking down -Z', async () => {
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000)
    camera.up.set(0, 1, 0)
    camera.position.set(0, 0, 100)
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld(true)
    const geometry = await renderCircleGeometry(camera)
    const normal = planeNormalFromGeometry(geometry)
    const expected = expectedNormal(camera)
    expect(Math.abs(normal.dot(expected))).toBeGreaterThan(0.999)
  })

  it('faces the camera looking down -X, a different plane than the -Z pose', async () => {
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000)
    camera.up.set(0, 1, 0)
    camera.position.set(100, 0, 0)
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld(true)
    const geometry = await renderCircleGeometry(camera)
    const normal = planeNormalFromGeometry(geometry)
    const expected = expectedNormal(camera)
    expect(Math.abs(normal.dot(expected))).toBeGreaterThan(0.999)
  })

  it('faces the camera from an oblique angle', async () => {
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000)
    camera.up.set(0, 0, 1)
    camera.position.set(60, 80, 40)
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld(true)
    const geometry = await renderCircleGeometry(camera)
    const normal = planeNormalFromGeometry(geometry)
    const expected = expectedNormal(camera)
    expect(Math.abs(normal.dot(expected))).toBeGreaterThan(0.999)
  })

  it('is a genuine 3D circle -- every point is `radius` from the actor location', async () => {
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000)
    camera.up.set(0, 0, 1)
    camera.position.set(60, 80, 40)
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld(true)
    const geometry = await renderCircleGeometry(camera)
    const arr = geometry.attributes.position.array as Float32Array
    for (let i = 0; i < arr.length; i += 3) {
      const d = Math.hypot(arr[i], arr[i + 1], arr[i + 2])
      expect(d).toBeCloseTo(LIGHT.light_radius, 3)
    }
  })
})
