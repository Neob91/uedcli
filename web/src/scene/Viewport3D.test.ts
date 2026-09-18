import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { cameraBasis } from './camera'
import type { CameraPose } from './camera'
import { applyCameraPose, WIREFRAME_LINE_HIT_WORLD_UNITS } from './viewportRender'

// This repo has no Canvas-in-test pattern (see `QuadLayout.test.tsx`'s own comment) -- Viewport3D
// owns a real `<Canvas>` and can't be rendered here the way `SelectionHighlight.test.tsx` renders
// `SurfaceSelectionHighlight` directly. `SelectionHighlight.test.tsx` already proves the component
// itself is geometry-agnostic (any owner/polyIndex arrays highlight correctly); what's specific to
// board item `mover-poly-select-in-movers-on-mode-not` is that Viewport3D actually WIRES a second
// instance to the Movers:on solid mesh's own arrays, gated the same as that mesh. Pinned as a
// source-text assertion (`toolbarLayout.test.ts`'s established pattern for this kind of gap).
const VIEWPORT3D_SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Viewport3D.tsx'), 'utf8')

describe('Viewport3D -- mover-poly selection highlight (mover-poly-select-in-movers-on-mode-not)', () => {
  it('wires a SECOND SurfaceSelectionHighlight at the Movers:on solid mesh\'s own geometry/owner arrays', () => {
    // Two SurfaceSelectionHighlight instances: one on the world mesh, one on the mover mesh.
    const count = (VIEWPORT3D_SOURCE.match(/<SurfaceSelectionHighlight/g) ?? []).length
    expect(count).toBe(2)
    expect(VIEWPORT3D_SOURCE).toMatch(
      /<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}\s+triangleOwners=\{moverTriangleOwners\}\s+trianglePolyIndex=\{moverTrianglePolyIndex\}/,
    )
  })

  it('gates the mover highlight identically to the mover solid mesh itself (both `showMoverSolid`)', () => {
    // The mover mesh and its highlight must share the exact same JSX gate, or the highlight can
    // exist (or not) independent of the geometry it's supposed to overlay.
    const moverMeshGate = /\{mode !== 'wireframe' && showMoverSolid && \(\s*<mesh ref=\{moverMeshRef\}/
    const moverHighlightGate =
      /\{mode !== 'wireframe' && showMoverSolid && \(\s*<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}/
    expect(VIEWPORT3D_SOURCE).toMatch(moverMeshGate)
    expect(VIEWPORT3D_SOURCE).toMatch(moverHighlightGate)
  })

  it('the mover highlight uses the mover mesh\'s own materials, not the world mesh\'s', () => {
    const moverHighlightBlock = /<SurfaceSelectionHighlight\s+bufferGeometry=\{moverGeometry\}[\s\S]*?\/>/.exec(
      VIEWPORT3D_SOURCE,
    )?.[0]
    expect(moverHighlightBlock).toBeDefined()
    expect(moverHighlightBlock).toContain('materials={activeMoverMaterials}')
  })
})

// Widened hit-test tolerance (owner report, live testing: brush-outline selection in wireframe mode
// needed near-pixel-exact clicks) -- pins the value so a future edit can't silently narrow it back.
describe('WIREFRAME_LINE_HIT_WORLD_UNITS', () => {
  it('is wider than the original 4-world-unit threshold', () => {
    expect(WIREFRAME_LINE_HIT_WORLD_UNITS).toBe(8)
  })
})

// Pins the left-handed-world orientation fix (owner bug report: "meshes render reverted (mirror
// image)") against real three.js math -- no WebGL context needed, `Vector3.project` is pure matrix
// arithmetic. The world is left-handed (X forward, Y right, Z up); all content is drawn inside a
// reflected `<group scale={[1,-1,1]}>` (R = diag(1,-1,1)) and `applyCameraPose` reflects the camera
// pose by the same R. A correct camera must render a point offset toward `cameraBasis.right` on the
// RIGHT of the screen (positive NDC.x) and toward `up` at the TOP (positive NDC.y) -- verified
// against a fresh `level photo --native` (render.rs) of the same poses. Because the content is
// reflected, the on-screen position of a game-coord point is the projection of R*point, so the test
// reflects the point by R (negate Y) before projecting.
function projectRelative(pose: CameraPose, sideOffset: [number, number, number]): THREE.Vector3 {
  const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
  applyCameraPose(camera, pose)
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  const depthAlongForward = 500
  const point = new THREE.Vector3(
    pose.position[0] + forward[0] * depthAlongForward + sideOffset[0],
    -(pose.position[1] + forward[1] * depthAlongForward + sideOffset[1]), // R = diag(1,-1,1): the group reflects Y
    pose.position[2] + forward[2] * depthAlongForward + sideOffset[2],
  )
  return point.project(camera)
}

describe('applyCameraPose', () => {
  it('renders a point offset toward cameraBasis.right on the right of the screen (positive NDC.x)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
      { position: [-300, 50, 700], pitch: -75, yaw: 0 }, // the near-top-down pose the bug/fix was pinned against
    ]
    for (const pose of poses) {
      const { right } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [right[0] * 350, right[1] * 350, right[2] * 350])
      expect(ndc.x).toBeGreaterThan(0)
    }
  })

  it('renders a point offset toward cameraBasis.up higher on the screen (positive NDC.y)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
    ]
    for (const pose of poses) {
      const { up } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [up[0] * 350, up[1] * 350, up[2] * 350])
      expect(ndc.y).toBeGreaterThan(0)
    }
  })

  it('looks along R*cameraBasis.forward (the pose is reflected into the content group space)', () => {
    const pose: CameraPose = { position: [-300, 50, 700], pitch: -75, yaw: 0 }
    const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
    applyCameraPose(camera, pose)
    const { forward } = cameraBasis(pose.pitch, pose.yaw)
    const lookDir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld)
    // Camera posed in reflected space: it looks along R*forward = (fx, -fy, fz).
    expect(lookDir.x).toBeCloseTo(forward[0], 5)
    expect(lookDir.y).toBeCloseTo(-forward[1], 5)
    expect(lookDir.z).toBeCloseTo(forward[2], 5)
  })
})
