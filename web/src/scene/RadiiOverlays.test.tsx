import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { RadiiOverlays, type RadiiView } from './RadiiOverlays'

// Regression for GUI-PARITY.md "Radii overlay colors" (✅ real `uned/UED22/Editor.dll` disassembly,
// 2026-09-18). `UEditorEngine::Draw`'s radii block draws the collision shape in `C_BrushWire` in the
// perspective pane (`Render->DrawCylinder`) but `C_ActorArrow` in the ortho panes, and the light
// radius in `C_ActorArrow` everywhere -- one shared dark red for all four, at 0.55 alpha, is what
// made the overlay hard to see. UED22 uses no alpha at all here.
//
// Read back with `LinearSRGBColorSpace` (three's working space, i.e. no conversion): the app's own
// canvases run `legacy: true` (`viewportRender.ts`'s `CANVAS_COLOR_MANAGEMENT`) so a `THREE.Color`
// channel IS the rendered byte, but the test renderer leaves `ColorManagement` on and the default
// `getHex()` would re-encode.
const C_BRUSH_WIRE = 0xff3f3f
const C_ACTOR_ARROW = 0xa30000

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
  }
}

async function materials(radii: SceneActor['radii'], view: RadiiView) {
  const renderer = await ReactThreeTestRenderer.create(
    <RadiiOverlays actors={[actor(radii)]} view={view} selectedNames={new Set(['A'])} />,
  )
  const found: THREE.LineBasicMaterial[] = []
  renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
    const line = o as THREE.LineSegments
    if (line.isLineSegments) found.push(line.material as THREE.LineBasicMaterial)
  })
  return found
}

const COLLISION = { collision_radius: 20, collision_height: 40, light_radius: null }
const LIGHT = { collision_radius: null, collision_height: null, light_radius: 300 }

describe('RadiiOverlays colors', () => {
  it('draws the perspective collision cylinder in C_BrushWire', async () => {
    const found = await materials(COLLISION, 'perspective')
    expect(found).toHaveLength(1)
    expect(found[0].color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_BRUSH_WIRE)
  })

  it('draws the ortho collision shape in C_ActorArrow', async () => {
    for (const view of ['top', 'front', 'side'] as const) {
      const found = await materials(COLLISION, view)
      expect(found).toHaveLength(1)
      expect(found[0].color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_ACTOR_ARROW)
    }
  })

  it('draws the light radius in C_ActorArrow in every pane', async () => {
    for (const view of ['perspective', 'top', 'front', 'side'] as const) {
      const found = await materials(LIGHT, view)
      expect(found).toHaveLength(1)
      expect(found[0].color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_ACTOR_ARROW)
    }
  })

  it('never blends -- UED22 draws these opaque', async () => {
    for (const radii of [COLLISION, LIGHT]) {
      for (const view of ['perspective', 'top'] as const) {
        for (const material of await materials(radii, view)) {
          expect(material.transparent).toBe(false)
          expect(material.opacity).toBe(1)
        }
      }
    }
  })
})
