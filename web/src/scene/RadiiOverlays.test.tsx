import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { RadiiOverlays, type RadiiView } from './RadiiOverlays'

// Regression for GUI-PARITY.md "Radii overlay colors" (✅ real `uned/UED22/Editor.dll` disassembly,
// 2026-09-18). `UEditorEngine::Draw`'s radii block draws the collision shape in `C_BrushWire` in the
// perspective pane (`Render->DrawCylinder`) but `C_ActorArrow` in the ortho panes, the light radius
// in `C_ActorArrow` everywhere, and the sound radius in `C_GroundHighlight` everywhere -- one shared
// dark red for all four, at 0.55 alpha, is what made the overlay hard to see. UED22 uses no alpha at
// all here.
//
// Read back with `LinearSRGBColorSpace` (three's working space, i.e. no conversion): the app's own
// canvases run `legacy: true` (`viewportRender.ts`'s `CANVAS_COLOR_MANAGEMENT`) so a `THREE.Color`
// channel IS the rendered byte, but the test renderer leaves `ColorManagement` on and the default
// `getHex()` would re-encode.
const C_BRUSH_WIRE = 0xff3f3f
const C_ACTOR_ARROW = 0xa30000
const C_GROUND_HIGHLIGHT = 0x00007f

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

const COLLISION = { collision_radius: 20, collision_height: 40, light_radius: null, sound_radius: null }
const LIGHT = { collision_radius: null, collision_height: null, light_radius: 300, sound_radius: null }
const SOUND = { collision_radius: null, collision_height: null, light_radius: null, sound_radius: 150 }

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

  it('draws the sound radius in C_GroundHighlight in every pane', async () => {
    for (const view of ['perspective', 'top', 'front', 'side'] as const) {
      const found = await materials(SOUND, view)
      expect(found).toHaveLength(1)
      expect(found[0].color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_GROUND_HIGHLIGHT)
    }
  })

  it('never blends -- UED22 draws these opaque', async () => {
    for (const radii of [COLLISION, LIGHT, SOUND]) {
      for (const view of ['perspective', 'top'] as const) {
        for (const material of await materials(radii, view)) {
          expect(material.transparent).toBe(false)
          expect(material.opacity).toBe(1)
        }
      }
    }
  })

  // Regression for board item gui-mouse-nav-jitter-ortho-radii-css (2026-09-19): the perspective
  // pane's light/sound circles used to be ONE `<lineSegments>` (one draw call, one `useFrame`
  // camera-basis recompute) PER SELECTED ACTOR -- N actors meant N redundant per-frame camera-basis
  // computations and N draw calls, continuously, in every mounted Canvas (react-three-fiber's
  // default "always" frameloop), which measurably degraded pointer-drag responsiveness in BOTH the
  // perspective and ortho panes (one shared JS main thread). Fixed by batching every actor's
  // same-colored circle into ONE shared geometry per radius type -- this asserts that batching:
  // multiple selected actors with a light radius must still produce exactly ONE lineSegments object
  // for light (not one per actor), same for sound.
  it('batches every selected actor\'s light circle into ONE draw call, not one per actor', async () => {
    const actors: SceneActor[] = [
      { ...actor(LIGHT), name: 'A', location: [0, 0, 0] },
      { ...actor(LIGHT), name: 'B', location: [100, 0, 0] },
      { ...actor(LIGHT), name: 'C', location: [200, 0, 0] },
    ]
    const renderer = await ReactThreeTestRenderer.create(
      <RadiiOverlays actors={actors} view="perspective" selectedNames={new Set(['A', 'B', 'C'])} />,
    )
    const found: THREE.LineSegments[] = []
    renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
      const line = o as THREE.LineSegments
      if (line.isLineSegments) found.push(line)
    })
    expect(found).toHaveLength(1)
    // 3 actors * CIRCLE_SEGMENTS(32) * 2 vertices-per-segment-line * 3 floats/vertex.
    expect((found[0].geometry.attributes.position.array as Float32Array).length).toBe(3 * 32 * 2 * 3)
  })

  it('batches light and sound circles into two SEPARATE draw calls (different fixed colors)', async () => {
    const actors: SceneActor[] = [
      { ...actor(LIGHT), name: 'A', location: [0, 0, 0] },
      { ...actor(SOUND), name: 'B', location: [100, 0, 0] },
    ]
    const renderer = await ReactThreeTestRenderer.create(
      <RadiiOverlays actors={actors} view="perspective" selectedNames={new Set(['A', 'B'])} />,
    )
    const found: THREE.LineBasicMaterial[] = []
    renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
      const line = o as THREE.LineSegments
      if (line.isLineSegments) found.push(line.material as THREE.LineBasicMaterial)
    })
    expect(found).toHaveLength(2)
    const hexes = found.map((m) => m.color.getHex(THREE.LinearSRGBColorSpace)).sort()
    expect(hexes).toEqual([C_ACTOR_ARROW, C_GROUND_HIGHLIGHT].sort())
  })
})
