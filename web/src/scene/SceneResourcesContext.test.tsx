import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AtlasPayload, BrushHighlight, SceneActor, ScenePayload, ScenePoly } from '../api'
import { SceneResourcesProvider } from './SceneResourcesContext'
import { useSceneResourcesContext } from './useSceneResourcesContext'

afterEach(cleanup)

function quad(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: -1,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: null,
    i_brush_poly: null,
    ...overrides,
  }
}

const SCENE: ScenePayload = { polys: [quad()], actors: [], geometry_pinned: false }
const ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

// Records every bufferGeometry object it sees (by identity, via a shared list) into a testid'd span
// -- the sibling's `Object.is` reference-equality proof relies on comparing the ACTUAL objects
// collected here, so the test does that in the test body, not via string comparison.
function RecordingConsumer({ id, seen }: { id: string; seen: { current: unknown[] } }) {
  const { bufferGeometry } = useSceneResourcesContext()
  seen.current.push(bufferGeometry)
  const [count, setCount] = useState(0)
  return (
    <div>
      <span data-testid={`consumer-${id}-count`}>{count}</span>
      <button type="button" data-testid={`consumer-${id}-bump`} onClick={() => setCount((c) => c + 1)}>
        bump
      </button>
    </div>
  )
}

describe('SceneResourcesProvider / useSceneResourcesContext', () => {
  it('gives two sibling consumers the SAME built bufferGeometry object', () => {
    const seenA: { current: unknown[] } = { current: [] }
    const seenB: { current: unknown[] } = { current: [] }
    render(
      <SceneResourcesProvider scene={SCENE} atlas={ATLAS} lightmap={null}>
        <RecordingConsumer id="a" seen={seenA} />
        <RecordingConsumer id="b" seen={seenB} />
      </SceneResourcesProvider>,
    )
    expect(seenA.current).toHaveLength(1)
    expect(seenB.current).toHaveLength(1)
    expect(Object.is(seenA.current[0], seenB.current[0])).toBe(true)
  })

  it("a re-render of one consumer (unrelated state change) leaves the OTHER consumer's bufferGeometry reference unchanged", () => {
    const seenA: { current: unknown[] } = { current: [] }
    const seenB: { current: unknown[] } = { current: [] }
    render(
      <SceneResourcesProvider scene={SCENE} atlas={ATLAS} lightmap={null}>
        <RecordingConsumer id="a" seen={seenA} />
        <RecordingConsumer id="b" seen={seenB} />
      </SceneResourcesProvider>,
    )
    const beforeB = seenB.current[0]

    act(() => {
      fireEvent.click(screen.getByTestId('consumer-a-bump'))
    })

    expect(screen.getByTestId('consumer-a-count').textContent).toBe('1')
    // Consumer B never re-rendered (its own count span is still absent from any new render pass),
    // so it recorded no NEW bufferGeometry -- confirm the one it did see is unchanged.
    expect(seenB.current).toHaveLength(1)
    expect(Object.is(seenB.current[0], beforeB)).toBe(true)
  })

  it('throws a clear error when used outside a provider', () => {
    function Orphan() {
      useSceneResourcesContext()
      return null
    }
    // React logs an error boundary-less throw to the console; the assertion itself is what matters.
    expect(() => render(<Orphan />)).toThrow(/SceneResourcesProvider/)
  })
})

// GUI.md "Movers": a Mover's own solved geometry must NOT ride the default `bufferGeometry` a pane
// draws unconditionally in every non-wireframe mode -- it's split into `moverGeometry`, drawn only
// when the "Movers: on" toggle is active (Viewport3D).
function moverActor(name: string): SceneActor {
  return {
    name, cls: 'Engine.Mover', bbox_lo: [0, 0, 0], bbox_hi: [1, 1, 1], location: [0, 0, 0],
    rotation: [0, 0, 0], folder: null, labels: [], order_value: 'm', csg_rank: 1, props: [],
    categories: [], brush: null, sprite: null, radii: null, is_mover: true,
    directional_arrow: null,
  }
}

function GeometrySplitProbe() {
  const { bufferGeometry, moverGeometry } = useSceneResourcesContext()
  return (
    <div>
      <span data-testid="default-position-count">{bufferGeometry.getAttribute('position').count}</span>
      <span data-testid="mover-position-count">{moverGeometry.getAttribute('position').count}</span>
    </div>
  )
}

describe('SceneResourcesProvider -- Mover polys split out of the default geometry', () => {
  it("a Mover-owned poly's triangles land in moverGeometry, not the default bufferGeometry", () => {
    const scene: ScenePayload = {
      polys: [quad({ owner: 'Wall1' }), quad({ owner: 'Door1' })],
      actors: [
        { ...moverActor('Wall1'), is_mover: false, cls: 'Engine.Brush' },
        moverActor('Door1'),
      ],
      geometry_pinned: true,
    }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null}>
        <GeometrySplitProbe />
      </SceneResourcesProvider>,
    )
    // Each quad fan-triangulates to 2 triangles * 3 verts = 6 position entries.
    expect(screen.getByTestId('default-position-count').textContent).toBe('6')
    expect(screen.getByTestId('mover-position-count').textContent).toBe('6')
  })

  it('an owner-less poly (no source actor) stays in the default geometry, never treated as a Mover\'s', () => {
    const scene: ScenePayload = { polys: [quad({ owner: null })], actors: [moverActor('Door1')], geometry_pinned: true }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null}>
        <GeometrySplitProbe />
      </SceneResourcesProvider>,
    )
    expect(screen.getByTestId('default-position-count').textContent).toBe('6')
    expect(screen.getByTestId('mover-position-count').textContent).toBe('0')
  })
})

// GUI.md "Shading modes": a mesh actor (never a brush) draws WIREFRAME in wireframe mode, the same
// convention brushes already get there -- `meshWireframeGeometry` is the real triangle-edge
// wireframe of every non-brush actor's own polys (`SceneActor.brush === null`), built alongside the
// default solid geometry (which still carries these same polys unchanged, for non-wireframe modes).
const BRUSH_HIGHLIGHT: BrushHighlight = { csg_class: 'add', color: [0, 0, 255], polys: [], local_origin: [0, 0, 0] }

function meshActor(name: string): SceneActor {
  return {
    name, cls: 'DeusEx.OfficeChair', bbox_lo: [0, 0, 0], bbox_hi: [1, 1, 1], location: [0, 0, 0],
    rotation: [0, 0, 0], folder: null, labels: [], order_value: 'a', csg_rank: 1, props: [],
    categories: [], brush: null, sprite: null, radii: null, is_mover: false,
    directional_arrow: null,
  }
}

function brushActor(name: string): SceneActor {
  return { ...meshActor(name), cls: 'Engine.Brush', brush: BRUSH_HIGHLIGHT }
}

// A single non-degenerate triangle (3 verts, not fan-split) -- three.js's `WireframeGeometry` emits
// exactly its 3 edges (6 vertices) with no shared-edge ambiguity, unlike a quad's 2-triangle fan.
function triangle(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return { ...quad(overrides), verts: [0, 0, 0, 1, 0, 0, 0, 1, 0] }
}

function MeshWireframeProbe() {
  const { meshWireframeGeometry } = useSceneResourcesContext()
  return <span data-testid="mesh-wireframe-position-count">{meshWireframeGeometry.getAttribute('position').count}</span>
}

describe('SceneResourcesProvider -- mesh actor wireframe geometry', () => {
  it("a mesh actor's own triangle produces a non-empty wireframe", () => {
    const scene: ScenePayload = { polys: [triangle({ owner: 'Statue1' })], actors: [meshActor('Statue1')], geometry_pinned: true }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null}>
        <MeshWireframeProbe />
      </SceneResourcesProvider>,
    )
    // 3 edges * 2 endpoint vertices = 6.
    expect(screen.getByTestId('mesh-wireframe-position-count').textContent).toBe('6')
  })

  it("a brush actor's own poly is excluded -- adding one leaves the mesh wireframe unchanged", () => {
    const withBrush: ScenePayload = {
      polys: [triangle({ owner: 'Statue1' }), triangle({ owner: 'Wall1' })],
      actors: [meshActor('Statue1'), brushActor('Wall1')],
      geometry_pinned: true,
    }
    render(
      <SceneResourcesProvider scene={withBrush} atlas={ATLAS} lightmap={null}>
        <MeshWireframeProbe />
      </SceneResourcesProvider>,
    )
    expect(screen.getByTestId('mesh-wireframe-position-count').textContent).toBe('6')
  })

  it('an owner-less poly (no source actor) is excluded from the mesh wireframe', () => {
    const scene: ScenePayload = { polys: [triangle({ owner: null })], actors: [meshActor('Statue1')], geometry_pinned: true }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null}>
        <MeshWireframeProbe />
      </SceneResourcesProvider>,
    )
    expect(screen.getByTestId('mesh-wireframe-position-count').textContent).toBe('0')
  })
})

// Bug fix (reported live, post-merge): a staged Ctrl/Cmd-drag move only ever reached the overlay
// layers (marker/brush outline/vertex dots), never a mesh actor's own rendered BODY -- its polys
// live in `scene.polys`, not on the actor object `applyStagedOffsets` (dragStage.ts) translates.
// `stagedOffsets` threads into the shared default solid buffer AND the mesh wireframe, scoped to
// mesh-actor owners only (never a brush's CSG-solved polys -- see dragStage.ts's own doc comment).
function BodyPositionProbe() {
  const { bufferGeometry, meshWireframeGeometry } = useSceneResourcesContext()
  const solidX = Array.from(bufferGeometry.getAttribute('position').array as Float32Array).filter((_, i) => i % 3 === 0)
  const wireX = Array.from(meshWireframeGeometry.getAttribute('position').array as Float32Array).filter((_, i) => i % 3 === 0)
  return (
    <div>
      <span data-testid="solid-x">{solidX.join(',')}</span>
      <span data-testid="wire-x">{wireX.join(',')}</span>
    </div>
  )
}

describe('SceneResourcesProvider -- stagedOffsets moves a mesh actor\'s own rendered body', () => {
  it("translates a staged mesh actor's solid triangles AND its wireframe by the staged delta", () => {
    const scene: ScenePayload = { polys: [triangle({ owner: 'Statue1' })], actors: [meshActor('Statue1')], geometry_pinned: true }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null} stagedOffsets={{ Statue1: [10, 0, 0] }}>
        <BodyPositionProbe />
      </SceneResourcesProvider>,
    )
    // triangle()'s verts are x=[0,1,0] -- staged +10 on x -> [10,11,10]. Solid triangle order is
    // stable; the wireframe's edge order is an internal three.js extraction detail, so compare
    // its x-values as a set (each of the 3 edges' 2 endpoints is one of the same 3 translated verts).
    expect(screen.getByTestId('solid-x').textContent).toBe('10,11,10')
    const wireX = (screen.getByTestId('wire-x').textContent ?? '').split(',').map(Number).sort()
    expect(wireX).toEqual([10, 10, 10, 10, 11, 11])
  })

  it('leaves the body untouched when no offset is staged for it', () => {
    const scene: ScenePayload = { polys: [triangle({ owner: 'Statue1' })], actors: [meshActor('Statue1')], geometry_pinned: true }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null} stagedOffsets={{}}>
        <BodyPositionProbe />
      </SceneResourcesProvider>,
    )
    expect(screen.getByTestId('solid-x').textContent).toBe('0,1,0')
  })

  it("never translates a BRUSH actor's own polys, even if (by caller mistake) staged -- the CSG safety net", () => {
    const scene: ScenePayload = {
      polys: [triangle({ owner: 'Wall1' })],
      actors: [brushActor('Wall1')],
      geometry_pinned: true,
    }
    render(
      <SceneResourcesProvider scene={scene} atlas={ATLAS} lightmap={null} stagedOffsets={{ Wall1: [10, 0, 0] }}>
        <BodyPositionProbe />
      </SceneResourcesProvider>,
    )
    // Wall1 is a brush -- meshActorNames excludes it, so its solved polys stay put despite the offset.
    expect(screen.getByTestId('solid-x').textContent).toBe('0,1,0')
  })
})
