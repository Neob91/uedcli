import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import { PointActorMarker } from './PointActorMarker'

// Regression for the owner report "point actors grow when I zoom out" -- a point-actor marker is a
// DT_Sprite billboard with a fixed WORLD footprint (UED22 parity), so its `scale` is the world-unit
// (w, h) passed in, NOT a per-frame constant-screen-pixel rescale (the old behaviour, since removed
// with `markerSpriteScale`/`MARKER_SCREEN_PX`). A fixed world scale foreshortens with distance/zoom
// like ordinary geometry. Uses @react-three/test-renderer -- no WebGL context needed.
describe('PointActorMarker', () => {
  it('sizes the billboard by its world footprint (width x height UU), placed at its world position', async () => {
    const renderer = await ReactThreeTestRenderer.create(
      <PointActorMarker position={[10, 20, 30]} width={48} height={64}>
        <spriteMaterial />
      </PointActorMarker>,
    )
    const sprite = renderer.scene.children[0].instance as THREE.Sprite
    expect(sprite).toBeInstanceOf(THREE.Sprite)
    expect(sprite.scale.x).toBe(48)
    expect(sprite.scale.y).toBe(64)
    expect(sprite.scale.z).toBe(1)
    expect(sprite.position.toArray()).toEqual([10, 20, 30])
  })

  it('applies a non-square footprint per axis (aspect preserved, no forced square)', async () => {
    const renderer = await ReactThreeTestRenderer.create(
      <PointActorMarker position={[0, 0, 0]} width={16} height={128}>
        <spriteMaterial />
      </PointActorMarker>,
    )
    const sprite = renderer.scene.children[0].instance as THREE.Sprite
    expect(sprite.scale.x).toBe(16)
    expect(sprite.scale.y).toBe(128)
  })
})
