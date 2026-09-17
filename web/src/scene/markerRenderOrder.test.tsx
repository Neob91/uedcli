import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import { PointActorMarker } from './PointActorMarker'
import { SurfaceSelectionHighlight } from './SelectionHighlight'
import { surfaceKey } from './selectionSet'
import { MARKER_RENDER_ORDER } from './markers'

// Board `selected-surface-highlight-renders-above-point`: a selected surface's translucent overlay
// (`SurfaceSelectionHighlight`) rendered on top of a point-actor sprite that was genuinely closer to
// the camera. Both are `transparent` objects, so three.js's transparent-pass sort only falls back to
// distance-from-camera once `renderOrder` ties -- and that distance is measured from each object's
// own `matrixWorld` origin, not its geometry, which is meaningless for the highlight `<mesh>` (it
// never sets a `position`; its vertices live only in a shared-attribute index subset). Fixed by
// giving the marker sprite an explicit `renderOrder` higher than the highlight's default, which
// three.js's sort checks before distance -- see `markers.ts`'s `MARKER_RENDER_ORDER` doc comment for
// the full mechanism. No WebGL context needed (`@react-three/test-renderer`).
describe('point-actor marker vs. surface highlight draw order', () => {
  it('SurfaceSelectionHighlight keeps the plain three.js default renderOrder (0)', async () => {
    const positions = new Float32Array([
      0, 0, 0, 1, 0, 0, 1, 1, 0, // triangle 1
      0, 0, 0, 1, 1, 0, 0, 1, 0, // triangle 2
    ])
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.addGroup(0, 6, 0)
    const materials = [new THREE.MeshBasicMaterial({ alphaTest: 0, side: THREE.FrontSide })]
    const renderer = await ReactThreeTestRenderer.create(
      <SurfaceSelectionHighlight
        bufferGeometry={geo}
        triangleOwners={['Brush1', 'Brush1']}
        trianglePolyIndex={[0, 0]}
        selectedSurfaces={new Set([surfaceKey('Brush1', 0)])}
        materials={materials}
      />,
    )
    const mesh = renderer.scene.children[0].instance as THREE.Mesh
    expect(mesh.renderOrder).toBe(0)
  })

  it("Viewport3D's MARKER_RENDER_ORDER is higher, so a marker sprite always draws after a coincident-depth highlight", async () => {
    expect(MARKER_RENDER_ORDER).toBeGreaterThan(0)
    const renderer = await ReactThreeTestRenderer.create(
      <PointActorMarker position={[0, 0, 0]} width={32} height={32} renderOrder={MARKER_RENDER_ORDER}>
        <spriteMaterial />
      </PointActorMarker>,
    )
    const sprite = renderer.scene.children[0].instance as THREE.Sprite
    expect(sprite.renderOrder).toBe(MARKER_RENDER_ORDER)
  })
})
