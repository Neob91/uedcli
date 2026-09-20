import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { BrushOutlines } from './BrushOutlines'

function brushActor(name: string, isMover: boolean): SceneActor {
  return {
    name,
    cls: isMover ? 'Engine.Mover' : 'Engine.Brush',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: { csg_class: 'add', color: [0, 255, 0], polys: [[0, 0, 0, 1, 0, 0, 1, 1, 0]], local_origin: [0, 0, 0] },
    sprite: null,
    radii: null,
    is_mover: isMover,
  }
}

// `BrushOutlines` renders TWO sibling root groups (a Fragment) -- the ordinary `groupRef` group and
// a separate `moverGroupRef` group holding just the Mover thin ring (board item
// `mover-not-selectable-via-wireframe-click`: exposed separately so the outer viewport can wire it
// into the raycast candidate set in every mode, not just wireframe) -- so a test must search both
// roots, not just `renderer.scene.children[0]`.
function allLines(renderer: Awaited<ReturnType<typeof ReactThreeTestRenderer.create>>) {
  return renderer.scene.children
    .flatMap((root) => root.children)
    .filter((c): c is typeof c & { instance: THREE.LineSegments } => c.instance instanceof THREE.LineSegments)
}

// Board `mover-wireframe-occluded-by-geometry`: a Mover's wireframe must always composite on top of
// other geometry, in every render mode -- normal depth-testing was letting an opaque wall/floor in
// front of it hide the outline. An ordinary (non-Mover) brush's thin wireframe must keep normal
// depth-testing, unaffected.
describe('BrushOutlines -- Mover wireframe always composites on top, ordinary brushes unaffected', () => {
  it("an unselected Mover's thin ring renders depthTest=false with a renderOrder above the default", async () => {
    const mover = brushActor('Door1', true)
    const renderer = await ReactThreeTestRenderer.create(
      <BrushOutlines actors={[mover]} selectedNames={new Set()} mode="csg-all" />,
    )
    const lines = allLines(renderer)
    expect(lines).toHaveLength(1)
    const line = lines[0].instance
    const material = line.material as THREE.LineBasicMaterial
    expect(material.depthTest).toBe(false)
    expect(line.renderOrder).toBeGreaterThan(0)
  })

  it("an unselected ordinary brush's thin ring keeps normal depth-testing (renderOrder 0, depthTest true)", async () => {
    const brush = brushActor('Wall1', false)
    const renderer = await ReactThreeTestRenderer.create(
      <BrushOutlines actors={[brush]} selectedNames={new Set()} mode="csg-all" />,
    )
    const lines = allLines(renderer)
    expect(lines).toHaveLength(1)
    const line = lines[0].instance
    const material = line.material as THREE.LineBasicMaterial
    expect(material.depthTest).toBe(true)
    expect(line.renderOrder).toBe(0)
  })

  it('a Mover mixed with an ordinary brush keeps each in its own draw call with the right settings', async () => {
    const mover = brushActor('Door1', true)
    const brush = brushActor('Wall1', false)
    const renderer = await ReactThreeTestRenderer.create(
      <BrushOutlines actors={[mover, brush]} selectedNames={new Set()} mode="csg-all" />,
    )
    const lines = allLines(renderer)
    expect(lines).toHaveLength(2)
    const byDepthTest = new Map(lines.map((l) => [(l.instance.material as THREE.LineBasicMaterial).depthTest, l.instance]))
    expect(byDepthTest.get(false)?.renderOrder).toBeGreaterThan(0)
    expect(byDepthTest.get(true)?.renderOrder).toBe(0)
  })
})
