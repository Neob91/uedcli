import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import { SurfaceSelectionHighlight, ActorSelectionHighlight } from './SelectionHighlight'
import { surfaceKey } from './selectionSet'

// Board `poly-highlight-not-visible-for-brush116-0`: selecting `Brush116:0`/`Brush111:0` (both real
// polys, verified non-degenerate and correctly matched by `selectedTriangles.ts`'s own tests) showed
// selected in the Inspector but drew no visible highlight. Root-caused (NOT live-screenshot-
// confirmed -- see the board item) to insufficient `polygonOffset` magnitude: the overlay shares its
// exact triangle position with the base mesh, so it always depends on `polygonOffset` to win the
// depth-test tie against it, but the slope-scaled `polygonOffsetFactor` term contributes ~0 for a
// poly viewed near HEAD-ON (both brushes' real shape) -- leaving only the constant
// `polygonOffsetUnits` term, which this app's unusually large camera depth range (`Viewport3D.tsx`'s
// `near: 1, far: 131072`) can make marginal at ordinary viewing distance. Only `polygonOffsetUnits`
// is raised (`POLYGON_OFFSET_UNITS_MAGNITUDE`); `polygonOffsetFactor` stays at its original magnitude
// (`POLYGON_OFFSET_FACTOR_MAGNITUDE`) since the theory never implicated it, and review flagged that
// scaling both risked a NEW regression (a stronger slope-scaled offset detaching the highlight from
// steep-angle surfaces this bug never touched). This pins that asymmetric fix so it isn't silently
// reverted or re-coupled -- a config/shape assertion, not a pixel test (this repo has no
// WebGL-rendering test harness; see the board item's own report for why a live screenshot wasn't
// possible in this environment).
function buildOverlayGeometry(): { geo: THREE.BufferGeometry; materials: THREE.Material[] } {
  // A single quad, one triangle-fan bucket -- shape matches a real authored poly's own fan
  // triangulation (`geometry.ts`'s `appendTriangleFan`), not load-bearing for this test beyond
  // "a real, non-degenerate poly with 2 triangles."
  const positions = new Float32Array([
    0, 0, 0, 1, 0, 0, 1, 1, 0, // triangle 1
    0, 0, 0, 1, 1, 0, 0, 1, 0, // triangle 2
  ])
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.addGroup(0, 6, 0)
  const materials = [new THREE.MeshBasicMaterial({ alphaTest: 0, side: THREE.FrontSide })]
  return { geo, materials }
}

// Board `poly-highlight-not-visible-for-brush116-0`, reopened: the real repro was `Brush100:0`/
// `Brush106:0`/`Brush111:0` -- masked, but every texel alpha=255 (a fully-opaque "Red Star" sign
// texture, confirmed live via `/api/level/.../atlas`). Root cause (isolated in a standalone three.js
// harness, `_scratch/browser_verify/harness/`, not speculation): the surface-pick overlay's material
// `opacity` is fixed at 0.25 (`HIGHLIGHT_OPACITY`), and WebGL's alphaTest discards on
// `material.opacity * texel.alpha` (`map_fragment` multiplies both channels), not the texel alpha
// alone -- so `0.25 * 1.0 = 0.25` always failed the base's own `alphaTest` (0.5), discarding every
// fragment regardless of the real texture. Fixed by scaling the overlay's `alphaTest` by its own
// effective opacity (1 for the opaque actor-tint variant, `opacity` for the additive surface-pick
// variant) so the discard decision reduces back to the base's own unscaled `texel.a < alphaTest`.
function buildMaskedGeometry(): { geo: THREE.BufferGeometry; map: THREE.Texture; materials: THREE.Material[] } {
  const positions = new Float32Array([
    0, 0, 0, 1, 0, 0, 1, 1, 0, // triangle 1
    0, 0, 0, 1, 1, 0, 0, 1, 0, // triangle 2
  ])
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1]), 2))
  geo.addGroup(0, 6, 0)
  const map = new THREE.Texture() // stub -- no real pixels needed, only object identity/alphaTest matter here
  const materials = [new THREE.MeshBasicMaterial({ alphaTest: 0.5, map, side: THREE.FrontSide })]
  return { geo, map, materials }
}

describe('SelectionHighlight masked-group alphaTest scaling', () => {
  it('SurfaceSelectionHighlight (additive, opacity 0.25) scales alphaTest by its own opacity', async () => {
    const { geo, map, materials } = buildMaskedGeometry()
    const renderer = await ReactThreeTestRenderer.create(
      <SurfaceSelectionHighlight
        bufferGeometry={geo}
        triangleOwners={['Brush100', 'Brush100']}
        trianglePolyIndex={[0, 0]}
        selectedSurfaces={new Set([surfaceKey('Brush100', 0)])}
        materials={materials}
      />,
    )
    const mesh = renderer.scene.children[0].instance as THREE.Mesh
    const mat = mesh.material as THREE.MeshBasicMaterial
    // 0.5 (base alphaTest) * 0.25 (this overlay's own opacity) -- NOT the base's raw 0.5, which
    // would discard every fragment since diffuseColor.a tops out at material.opacity * texel.a.
    expect(mat.alphaTest).toBeCloseTo(0.125)
    expect(mat.map).toBe(map)
  })

  it('ActorSelectionHighlight (opaque, real material opacity 1) leaves alphaTest unscaled', async () => {
    const { geo, materials } = buildMaskedGeometry()
    const renderer = await ReactThreeTestRenderer.create(
      <ActorSelectionHighlight
        bufferGeometry={geo}
        triangleOwners={['Hooker0', 'Hooker0']}
        selectedActorNames={new Set(['Hooker0'])}
        materials={materials}
      />,
    )
    const mesh = renderer.scene.children[0].instance as THREE.Mesh
    const mat = mesh.material as THREE.MeshBasicMaterial
    // The opaque variant's own material never sets `opacity` (defaults to 1), so its scale factor
    // is 1 -- matches the base material's alphaTest exactly, same as before this fix.
    expect(mat.alphaTest).toBeCloseTo(0.5)
  })
})

describe('SelectionHighlight polygonOffset', () => {
  it('SurfaceSelectionHighlight raises polygonOffsetUnits but leaves polygonOffsetFactor at its original magnitude', async () => {
    const { geo, materials } = buildOverlayGeometry()
    const renderer = await ReactThreeTestRenderer.create(
      <SurfaceSelectionHighlight
        bufferGeometry={geo}
        triangleOwners={['Brush116', 'Brush116']}
        trianglePolyIndex={[0, 0]}
        selectedSurfaces={new Set([surfaceKey('Brush116', 0)])}
        materials={materials}
      />,
    )
    const mesh = renderer.scene.children[0].instance as THREE.Mesh
    const mat = mesh.material as THREE.MeshBasicMaterial
    expect(mat.polygonOffset).toBe(true)
    expect(Math.abs(mat.polygonOffsetUnits)).toBeGreaterThan(1)
    expect(Math.abs(mat.polygonOffsetFactor)).toBe(1)
    // Not equal -- the fix is deliberately asymmetric, unlike an earlier draft that scaled both.
    expect(mat.polygonOffsetFactor).not.toBe(mat.polygonOffsetUnits)
  })

  it('ActorSelectionHighlight (the opaque actor-tint variant) uses the same asymmetric magnitudes', async () => {
    const { geo, materials } = buildOverlayGeometry()
    const renderer = await ReactThreeTestRenderer.create(
      <ActorSelectionHighlight
        bufferGeometry={geo}
        triangleOwners={['Hooker0', 'Hooker0']}
        selectedActorNames={new Set(['Hooker0'])}
        materials={materials}
      />,
    )
    const mesh = renderer.scene.children[0].instance as THREE.Mesh
    const mat = mesh.material as THREE.MeshBasicMaterial
    expect(mat.polygonOffset).toBe(true)
    expect(Math.abs(mat.polygonOffsetUnits)).toBeGreaterThan(1)
    expect(Math.abs(mat.polygonOffsetFactor)).toBe(1)
  })
})
