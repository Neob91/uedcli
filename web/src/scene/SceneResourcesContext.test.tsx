import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AtlasPayload, ScenePayload, ScenePoly } from '../api'
import { SceneResourcesProvider, useSceneResourcesContext } from './SceneResourcesContext'

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
