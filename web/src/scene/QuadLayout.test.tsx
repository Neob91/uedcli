// The spec's own stated acceptance criterion ("a brush selected in ANY pane highlights identically
// in all four panes"), automated (quad-layout Part 3, Task 17): QuadLayout's job is PROP PLUMBING
// (thread one lifted selectedNames set to every pane), not rendering -- so this mocks the four pane
// components at that exact boundary (matching Inspector.test.tsx's established render/query-by-
// testid RTL pattern) rather than trying to stand up a real WebGL Canvas (confirmed absent from this
// repo's test setup -- no existing Canvas-in-test pattern to reuse).
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AtlasPayload, ScenePayload } from '../api'

vi.mock('./Viewport3D', () => ({
  Viewport3D: ({
    selectedNames,
    onSelectActor,
  }: {
    selectedNames: ReadonlySet<string>
    onSelectActor: (name: string, additive: boolean) => void
  }) => (
    <div>
      <span data-testid="pane-perspective-selected">{[...selectedNames].join(',')}</span>
      <button type="button" data-testid="pane-perspective-select" onClick={() => onSelectActor('ActorA', false)} />
    </div>
  ),
}))

vi.mock('./OrthoViewport', () => ({
  OrthoViewport: ({
    axis,
    selectedNames,
    onSelectActor,
  }: {
    axis: string
    selectedNames: ReadonlySet<string>
    onSelectActor: (name: string, additive: boolean) => void
  }) => (
    <div>
      <span data-testid={`pane-${axis}-selected`}>{[...selectedNames].join(',')}</span>
      <button type="button" data-testid={`pane-${axis}-select`} onClick={() => onSelectActor('ActorA', false)} />
    </div>
  ),
}))

// Imported AFTER the mocks above so QuadLayout picks up the mocked panes (vi.mock is hoisted, but
// the import itself must still come after for readability of the file's own top-to-bottom order).
import { QuadLayout } from './QuadLayout'
import { toggleSelection } from './selectionSet'

afterEach(cleanup)

const SCENE: ScenePayload = { polys: [], actors: [], geometry_pinned: false }
const ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

/** Owns `selectedNames` the way App.tsx does -- QuadLayout itself is a controlled component, so the
 * "does a selection from one pane reach every other pane" property needs a real owning parent, not
 * QuadLayout holding its own state. */
function Harness() {
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set())
  const onSelectActor = (name: string, additive: boolean) => setSelectedNames((s) => toggleSelection(s, name, additive))
  return (
    <QuadLayout
      scene={SCENE}
      atlas={ATLAS}
      lightmap={null}
      selectedNames={selectedNames}
      onSelectActor={onSelectActor}
      onSelectMany={(names, additive) => setSelectedNames((s) => (additive ? new Set([...s, ...names]) : new Set(names)))}
      onDeselect={() => setSelectedNames(new Set())}
      buildSolved={false}
    />
  )
}

describe('QuadLayout cross-pane selection consistency', () => {
  it('a selection originating from ANY one pane is threaded to all four panes identically', () => {
    render(<Harness />)

    // Nothing selected initially, in every pane.
    for (const pane of ['perspective', 'top', 'front', 'side']) {
      expect(screen.getByTestId(`pane-${pane}-selected`).textContent).toBe('')
    }

    // Select from the "top" ortho pane's own mocked control.
    fireEvent.click(screen.getByTestId('pane-top-select'))

    for (const pane of ['perspective', 'top', 'front', 'side']) {
      expect(screen.getByTestId(`pane-${pane}-selected`).textContent).toBe('ActorA')
    }
  })

  it('a selection originating from Perspective also reaches every ortho pane', () => {
    render(<Harness />)

    fireEvent.click(screen.getByTestId('pane-perspective-select'))

    for (const pane of ['perspective', 'top', 'front', 'side']) {
      expect(screen.getByTestId(`pane-${pane}-selected`).textContent).toBe('ActorA')
    }
  })
})
