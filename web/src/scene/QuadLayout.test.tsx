// The spec's own stated acceptance criterion ("a brush selected in ANY pane highlights identically
// in all four panes"), automated (quad-layout Part 3, Task 17): QuadLayout's job is PROP PLUMBING
// (thread one lifted selectedNames set to every pane), not rendering -- so this mocks the four pane
// components at that exact boundary (matching Inspector.test.tsx's established render/query-by-
// testid RTL pattern) rather than trying to stand up a real WebGL Canvas (confirmed absent from this
// repo's test setup -- no existing Canvas-in-test pattern to reuse).
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  }: {
    selectedNames: ReadonlySet<string>
    onSelectActor: (name: string, additive: boolean) => void
    selectedSurfaces: ReadonlySet<string>
    onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
    onDeselect: () => void
    mode: string
    showMoverSolid: boolean
  }) => (
    <div>
      <span data-testid="pane-perspective-selected">{[...selectedNames].join(',')}</span>
      <span data-testid="pane-perspective-selected-surfaces">{[...selectedSurfaces].join(',')}</span>
      <span data-testid="pane-perspective-mode">{mode}</span>
      <span data-testid="pane-perspective-mover-solid">{String(showMoverSolid)}</span>
      <button type="button" data-testid="pane-perspective-select" onClick={() => onSelectActor('ActorA', false)} />
      <button type="button" data-testid="pane-perspective-select-poly" onClick={() => onSelectSurface('BrushA', 0, false)} />
      <button type="button" data-testid="pane-perspective-miss" onClick={onDeselect} />
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

const SCENE: ScenePayload = { polys: [], actors: [], geometry_pinned: false }
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
      scene={SCENE}
      atlas={ATLAS}
      lightmap={null}
      selectedNames={selectedNames}
      onSelectActor={onSelectActor}
      selectedSurfaces={selectedSurfaces}
      onSelectSurface={onSelectSurface}
      onSelectMany={(names, additive) => setSelectedNames((s) => (additive ? new Set([...s, ...names]) : new Set(names)))}
      onDeselect={() => {
        setSelectedNames(new Set())
        setSelectedSurfaces(new Set())
      }}
      buildSolved={buildSolved}
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

// The visible mode selector (ModeSelector) must drive the SAME per-pane mode state the `1`-`4`
// keyboard shortcuts use, not a second, parallel model -- these pin that it changes only the
// clicked pane's mode, and respects the same buildSolved gating applyModeKey already enforces.
// Owner ruling: ortho panes (top/front/side) are ALWAYS wireframe, no mode choice at all -- only
// perspective gets the selector, and only perspective's mode can ever change.
describe('QuadLayout visible mode selector', () => {
  it("clicking perspective's mode button changes only its mode, leaving ortho panes alone", () => {
    render(<Harness buildSolved={true} />)

    // Defaults: perspective 'lit', the three ortho panes 'wireframe' (QuadLayout's DEFAULT_MODES).
    expect(screen.getByTestId('pane-top-mode').textContent).toBe('wireframe')
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('lit')

    const perspectivePane = screen.getByTestId('quad-pane-perspective')
    fireEvent.click(within(perspectivePane).getByTestId('mode-btn-unlit'))

    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('unlit')
    expect(screen.getByTestId('pane-top-mode').textContent).toBe('wireframe')
    expect(screen.getByTestId('pane-front-mode').textContent).toBe('wireframe')
    expect(screen.getByTestId('pane-side-mode').textContent).toBe('wireframe')
  })

  it('a mode requiring a solved build is disabled, not silently ignored, when buildSolved is false', () => {
    render(<Harness buildSolved={false} />)

    // DEFAULT_MODES requests perspective 'lit', but with no solved build the EFFECTIVE mode falls
    // back to 'wireframe' (resolveEffectiveMode) -- that's what the mocked pane actually receives.
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('wireframe')

    const perspectivePane = screen.getByTestId('quad-pane-perspective')
    const litBtn = within(perspectivePane).getByTestId('mode-btn-lit')
    expect(litBtn.hasAttribute('disabled')).toBe(true)

    fireEvent.click(litBtn)
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('wireframe') // unchanged
  })

  it('ortho panes render no mode selector at all -- there is no choice to make', () => {
    render(<Harness buildSolved={true} />)

    for (const pane of ['top', 'front', 'side']) {
      const paneEl = screen.getByTestId(`quad-pane-${pane}`)
      expect(within(paneEl).queryByRole('group', { name: 'Shading mode' })).toBeNull()
    }
    // Perspective still has it.
    const perspectivePane = screen.getByTestId('quad-pane-perspective')
    expect(within(perspectivePane).getByRole('group', { name: 'Shading mode' })).toBeTruthy()
  })
})

// GUI.md "Movers": the toolbar toggle showing/hiding a Mover's SOLID geometry (wireframe-outline-only
// is always on, unaffected by this toggle -- see Viewport3D/brushRings). Mirrors the existing Grid/
// Radii toggle-button convention.
describe('QuadLayout Movers toggle', () => {
  it('defaults off and threads showMoverSolid to the perspective pane', () => {
    render(<Harness />)

    const button = screen.getByText('Movers: off')
    expect(button.getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByTestId('pane-perspective-mover-solid').textContent).toBe('false')
  })

  it('clicking the button flips the toggle and the value threaded to the perspective pane', () => {
    render(<Harness />)

    fireEvent.click(screen.getByText('Movers: off'))

    const button = screen.getByText('Movers: on')
    expect(button.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('pane-perspective-mover-solid').textContent).toBe('true')
  })

  // The click must still change the toggle's stored state even while the focused pane is currently
  // in wireframe mode -- the button is never disabled/greyed based on the pane's current mode
  // (unlike ModeSelector's buildSolved gating above, a deliberately different rule for this button).
  it('stays enabled and toggles even when the perspective pane is in wireframe mode (buildSolved=false)', () => {
    render(<Harness buildSolved={false} />)
    expect(screen.getByTestId('pane-perspective-mode').textContent).toBe('wireframe')

    const button = screen.getByText('Movers: off')
    expect(button.hasAttribute('disabled')).toBe(false)

    fireEvent.click(button)
    expect(screen.getByText('Movers: on')).toBeTruthy()
    expect(screen.getByTestId('pane-perspective-mover-solid').textContent).toBe('true')
  })
})
