import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { SelectionMarkers } from './SelectionMarkers'

// Regression for GUI-PARITY.md "Pivot-cross ... Part 4" (real `uned/UED22/Editor.dll` disassembly +
// a live UED22 capture, 2026-09-18): UED22 keeps ONE global pivot location and draws at most ONE
// cross, anchored to the actor that was most recently the SOLE selection, and only when that actor
// snaps to the grid (`bEdShouldSnap`, set by `Engine.Brush`'s class defaults, unset on point
// actors). This file used to draw one cross per selected brush, unconditionally.
//
// The pivot sprite is the one with `renderOrder` 40; vertex-handle dots use 30.
const PIVOT_RENDER_ORDER = 40
const VERTEX_DOT_RENDER_ORDER = 30

function brush(name: string, location: [number, number, number]): SceneActor {
  return {
    name,
    cls: 'Brush',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location,
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: name,
    csg_rank: 1,
    props: [],
    brush: { csg_class: 'add', color: [70, 110, 255], polys: [[0, 0, 0]], local_origin: location },
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
}

function light(name: string, location: [number, number, number]): SceneActor {
  return { ...brush(name, location), cls: 'Light', brush: null }
}

async function spritesByRenderOrder(actors: SceneActor[], selected: string[], renderOrder: number) {
  const renderer = await ReactThreeTestRenderer.create(
    <SelectionMarkers actors={actors} selectedNames={new Set(selected)} />,
  )
  const found: THREE.Sprite[] = []
  renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
    if ((o as THREE.Sprite).isSprite && o.renderOrder === renderOrder) found.push(o as THREE.Sprite)
  })
  return found
}

function pivotSprites(actors: SceneActor[], selected: string[]) {
  return spritesByRenderOrder(actors, selected, PIVOT_RENDER_ORDER)
}

describe('SelectionMarkers pivot cross', () => {
  it('draws none when nothing is selected', async () => {
    expect(await pivotSprites([brush('A', [0, 0, 0])], [])).toHaveLength(0)
  })

  it('draws exactly one, on the selected brush', async () => {
    const found = await pivotSprites([brush('A', [10, 20, 30])], ['A'])
    expect(found).toHaveLength(1)
    expect(found[0].position.toArray()).toEqual([10, 20, 30])
  })

  it('draws exactly one for a multi-brush selection, anchored on the first-clicked brush', async () => {
    const actors = [brush('A', [10, 20, 30]), brush('B', [40, 50, 60]), brush('C', [70, 80, 90])]
    const found = await pivotSprites(actors, ['A', 'B', 'C'])
    expect(found).toHaveLength(1)
    expect(found[0].position.toArray()).toEqual([10, 20, 30])
  })

  it('draws none for a lone selected point actor (no bEdShouldSnap)', async () => {
    expect(await pivotSprites([light('L', [1, 2, 3])], ['L'])).toHaveLength(0)
  })

  it('draws none while the anchor is a point actor, even with a brush also selected', async () => {
    const actors = [light('L', [1, 2, 3]), brush('A', [10, 20, 30])]
    expect(await pivotSprites(actors, ['L', 'A'])).toHaveLength(0)
  })
})

// Regression for board item `vertex-local-origin-dot-only-shows-on-primary`: the local-origin
// (PrePivot) dot used to be gated to the "primary" (most-recently-selected) actor only, at most one
// dot even under a multi-brush selection. Real UED22's `DrawLevelBrush` draws it for every
// highlighted brush (`preview.py`'s `_scene_geometry`, `is_hi_actor`) -- distinct from the single
// global pivot cross above. Each test brush's single poly vertex sits at [0, 0, 0]
// (`brush()`'s `polys`), so a dot at the brush's own (non-origin) `location` can only be its
// local-origin dot, not a vertex dot.
describe('SelectionMarkers local-origin dot', () => {
  it('draws one local-origin dot per selected brush under a multi-selection', async () => {
    const actors = [brush('A', [10, 20, 30]), brush('B', [40, 50, 60]), brush('C', [70, 80, 90])]
    const found = await spritesByRenderOrder(actors, ['A', 'B', 'C'], VERTEX_DOT_RENDER_ORDER)
    const positions = found.map((s) => s.position.toArray())
    expect(positions).toContainEqual([10, 20, 30])
    expect(positions).toContainEqual([40, 50, 60])
    expect(positions).toContainEqual([70, 80, 90])
  })
})
