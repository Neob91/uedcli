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
    selectedSurfaces,
    onSelectSurface,
    onDeselect,
    mode,
    showMoverSolid,
    buildSolved,
    onSelectMode,
    activeTray,
    onActiveTrayChange,
  }: {
    selectedNames: ReadonlySet<string>
    onSelectActor: (name: string, additive: boolean) => void
    selectedSurfaces: ReadonlySet<string>
    onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
    onDeselect: () => void
    mode: string
    showMoverSolid: boolean
    buildSolved: boolean
    onSelectMode: (mode: string) => void
    activeTray: 'shade' | 'misc' | null
    onActiveTrayChange: (tray: 'shade' | 'misc' | null) => void
  }) => (
    <div>
      <span data-testid="pane-perspective-selected">{[...selectedNames].join(',')}</span>
      <span data-testid="pane-perspective-selected-surfaces">{[...selectedSurfaces].join(',')}</span>
      <span data-testid="pane-perspective-mode">{mode}</span>
      <span data-testid="pane-perspective-mover-solid">{String(showMoverSolid)}</span>
      <span data-testid="pane-perspective-build-solved">{String(buildSolved)}</span>
      <span data-testid="pane-perspective-active-tray">{activeTray ?? ''}</span>
      <button type="button" data-testid="pane-perspective-select" onClick={() => onSelectActor('ActorA', false)} />
      <button type="button" data-testid="pane-perspective-select-poly" onClick={() => onSelectSurface('BrushA', 0, false)} />
      <button type="button" data-testid="pane-perspective-miss" onClick={onDeselect} />
      <button type="button" data-testid="pane-perspective-select-lit-mode" onClick={() => onSelectMode('lit')} />
      <button type="button" data-testid="pane-perspective-open-shade-tray" onClick={() => onActiveTrayChange('shade')} />
    </div>
  ),
}))

vi.mock('./OrthoViewport', () => ({
  OrthoViewport: ({
    axis,
    selectedNames,
    onSelectActor,
    onDeselect,
    mode,
  }: {
    axis: string
    selectedNames: ReadonlySet<string>
    onSelectActor: (name: string, additive: boolean) => void
    onDeselect: () => void
    mode: string
  }) => (
    <div>
      <span data-testid={`pane-${axis}-selected`}>{[...selectedNames].join(',')}</span>
      <span data-testid={`pane-${axis}-mode`}>{mode}</span>
      <button type="button" data-testid={`pane-${axis}-select`} onClick={() => onSelectActor('ActorA', false)} />
      <button type="button" data-testid={`pane-${axis}-miss`} onClick={onDeselect} />
    </div>
  ),
}))

// Imported AFTER the mocks above so QuadLayout picks up the mocked panes (vi.mock is hoisted, but
// the import itself must still come after for readability of the file's own top-to-bottom order).
import { QuadLayout } from './QuadLayout'
import { surfaceKey, toggleSelection } from './selectionSet'

afterEach(cleanup)

const SCENE: ScenePayload = { polys: [], actors: [], geometry_pinned: false, enums: {} }
const ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }

/** Owns `selectedNames` the way App.tsx does -- QuadLayout itself is a controlled component, so the
 * "does a selection from one pane reach every other pane" property needs a real owning parent, not
 * QuadLayout holding its own state. */
function Harness({ buildSolved = false }: { buildSolved?: boolean }) {
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set())
  const [selectedSurfaces, setSelectedSurfaces] = useState<Set<string>>(new Set())
  // Both mirror App.tsx's real wiring -- deselectSole=true, and the other kind is cleared only on a
  // PLAIN (non-additive) pick (GUI-PARITY.md "Actor + surface selection coexist"). Keep in sync.
  const onSelectActor = (name: string, additive: boolean) => {
    setSelectedNames((s) => toggleSelection(s, name, additive, true))
    if (!additive) setSelectedSurfaces(new Set())
  }
  const onSelectSurface = (actor: string, polyIndex: number, additive: boolean) => {
    setSelectedSurfaces((s) => toggleSelection(s, surfaceKey(actor, polyIndex), additive, true))
    if (!additive) setSelectedNames(new Set())
  }
  return (
    <QuadLayout
      level="test-level"
      scene={SCENE}
      atlas={ATLAS}
      lightmap={null}
      selectedNames={selectedNames}
      onSelectActor={onSelectActor}
      selectedSurfaces={selectedSurfaces}
      onSelectSurface={onSelectSurface}
      onDeselect={() => {
        setSelectedNames(new Set())
        setSelectedSurfaces(new Set())
      }}
      stagedOffsets={{}}
      stagedOffsetsRef={{ current: {} }}
      setStagedOffsets={() => {}}
      buildSolved={buildSolved}
      frameRequest={null}
      frameActors={() => {}}
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

  // Owner ruling 2026-09-15: a tap that hits nothing (any pane) deselects everything, the same
  // `onDeselect` QuadLayout already wires to SelectionKeys' `Esc` -- verifies QuadLayout forwards it
  // to both Viewport3D and OrthoViewport, not just SelectionKeys.
  it("a miss (onDeselect) from ANY pane clears the selection everywhere", () => {
    render(<Harness />)

    fireEvent.click(screen.getByTestId('pane-top-select'))
    for (const pane of ['perspective', 'top', 'front', 'side']) {
      expect(screen.getByTestId(`pane-${pane}-selected`).textContent).toBe('ActorA')
    }

    fireEvent.click(screen.getByTestId('pane-perspective-miss'))
    for (const pane of ['perspective', 'top', 'front', 'side']) {
      expect(screen.getByTestId(`pane-${pane}-selected`).textContent).toBe('')
    }
  })

  // Board item click-on-a-selected-poly-does-not-deselect-it: through the REAL onSelectSurface
  // wiring (Harness mirrors App.tsx exactly), clicking the sole selected poly again must clear it.
  it('clicking the sole selected poly again deselects it', () => {
    render(<Harness />)

    fireEvent.click(screen.getByTestId('pane-perspective-select-poly'))
    expect(screen.getByTestId('pane-perspective-selected-surfaces').textContent).toBe('BrushA#0')

    fireEvent.click(screen.getByTestId('pane-perspective-select-poly'))
    expect(screen.getByTestId('pane-perspective-selected-surfaces').textContent).toBe('')
  })

  // Board item click-on-selected-mesh-actor-does-not-deselect: through the REAL onSelectActor
  // wiring (Harness mirrors App.tsx exactly), clicking the sole selected actor again must clear it,
  // same as the poly case above.
  it('clicking the sole selected actor again deselects it', () => {
    render(<Harness />)

    fireEvent.click(screen.getByTestId('pane-perspective-select'))
    expect(screen.getByTestId('pane-perspective-selected').textContent).toBe('ActorA')

    fireEvent.click(screen.getByTestId('pane-perspective-select'))
    expect(screen.getByTestId('pane-perspective-selected').textContent).toBe('')
  })
})

describe('QuadLayout mode-select plumbing (now inside Viewport3D/ControlCluster)', () => {
  it('threads buildSolved to Viewport3D', () => {
    render(<Harness buildSolved={true} />)
    expect(screen.getByTestId('pane-perspective-build-solved').textContent).toBe('true')
  })

  it("onSelectMode reaches Viewport3D and drives the SAME per-pane mode state '1'-'4' would", () => {
    render(<Harness buildSolved={true} />)
    fireEvent.click(screen.getByTestId('pane-perspective-select-lit-mode'))
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('lit')
    // Ortho panes are untouched -- only perspective's mode can ever change (unchanged rule).
    expect(screen.getByTestId('pane-top-mode').textContent).toBe('wireframe')
  })

  it('a mode requiring a solved build has no effect when buildSolved is false (resolveEffectiveMode falls back)', () => {
    render(<Harness buildSolved={false} />)
    fireEvent.click(screen.getByTestId('pane-perspective-select-lit-mode'))
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('wireframe')
  })
})

describe('QuadLayout misc-options plumbing', () => {
  it('renders MiscOptions and threads showMoverSolid through it to the perspective pane', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Misc options' }))
    fireEvent.click(screen.getByLabelText('Movers'))
    expect(screen.getByTestId('pane-perspective-mover-solid').textContent).toBe('true')
  })
})

describe('QuadLayout activeTray mutual exclusion', () => {
  it('opening the MiscOptions tray, then the ControlCluster (Viewport3D) tray, closes MiscOptions\' own', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Misc options' }))
    // activeTray is lifted to QuadLayout and passed identically to both consumers -- Viewport3D's
    // mock renders it verbatim, so it now reads 'misc', not '' (Viewport3D doesn't OWN this state,
    // but it does receive and display the same value MiscOptions just set).
    expect(screen.getByTestId('pane-perspective-active-tray').textContent).toBe('misc')
    fireEvent.click(screen.getByTestId('pane-perspective-open-shade-tray'))
    expect(screen.getByTestId('pane-perspective-active-tray').textContent).toBe('shade')
    // MiscOptions' own tray reads the SAME lifted state -- it must now report closed.
    expect(
      screen.getByLabelText('Movers').closest('.misc-options-flyout')?.classList.contains('open'),
    ).toBe(false)
  })
})
