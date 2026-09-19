import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { DirectionalArrows } from './DirectionalArrows'

// Regression for GUI-PARITY.md "Directional arrow gizmo" (own-binary `Editor.dll` disassembly,
// VA 0x1003da60-0x1003e098): C_ActorArrow = (163,0,0); a non-Camera bDirectional actor shows the
// arrow only while selected; a Camera-descendant actor always shows it (this GUI's viewports never
// "possess" a level actor, so UED22's own exclusion clause -- skip the viewport's OWN actor -- can
// never fire here).
const C_ACTOR_ARROW = 0xa30000

// 30 floats: 5 segments x 2 points x 3 floats. The exact numbers don't matter to this component --
// it just draws whatever the server already resolved -- so a simple fixed pattern is enough to
// assert "one lineSegments object, N*10 points, this exact color".
const SAMPLE_LINES: number[] = Array.from({ length: 30 }, (_, i) => i)

function actor(name: string, directional_arrow: SceneActor['directional_arrow']): SceneActor {
  return {
    name,
    cls: 'Engine.Actor',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: name,
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow,
  }
}

async function findLineSegments(actors: SceneActor[], selectedNames: ReadonlySet<string>) {
  const renderer = await ReactThreeTestRenderer.create(
    <DirectionalArrows actors={actors} selectedNames={selectedNames} />,
  )
  const found: THREE.LineSegments[] = []
  renderer.scene.instance.traverse((o: THREE.Object3D) => {
    const line = o as THREE.LineSegments
    if (line.isLineSegments) found.push(line)
  })
  return found
}

describe('DirectionalArrows', () => {
  it('draws nothing when no actor has a directional_arrow', async () => {
    const found = await findLineSegments([actor('A', null)], new Set())
    expect(found).toHaveLength(0)
  })

  it('draws nothing for a require_selection actor that is not selected', async () => {
    const found = await findLineSegments(
      [actor('NPC0', { require_selection: true, lines: SAMPLE_LINES })],
      new Set(),
    )
    expect(found).toHaveLength(0)
  })

  it('draws a require_selection actor once it is selected, in C_ActorArrow', async () => {
    const lines = SAMPLE_LINES
    const found = await findLineSegments(
      [actor('NPC0', { require_selection: true, lines })],
      new Set(['NPC0']),
    )
    expect(found).toHaveLength(1)
    expect(found[0].material.color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_ACTOR_ARROW)
    expect(found[0].geometry.getAttribute('position').count).toBe(lines.length / 3)
  })

  it('draws a Camera actor unconditionally, even with nothing selected', async () => {
    const lines = SAMPLE_LINES
    const found = await findLineSegments(
      [actor('Camera0', { require_selection: false, lines })],
      new Set(),
    )
    expect(found).toHaveLength(1)
    expect(found[0].material.color.getHex(THREE.LinearSRGBColorSpace)).toBe(C_ACTOR_ARROW)
  })

  it('batches multiple visible arrows into ONE lineSegments draw call', async () => {
    const a = SAMPLE_LINES
    const b = a.map((v) => v + 100)
    const found = await findLineSegments(
      [
        actor('Camera0', { require_selection: false, lines: a }),
        actor('NPC0', { require_selection: true, lines: b }),
      ],
      new Set(['NPC0']),
    )
    expect(found).toHaveLength(1)
    expect(found[0].geometry.getAttribute('position').count).toBe((a.length + b.length) / 3)
  })
})
