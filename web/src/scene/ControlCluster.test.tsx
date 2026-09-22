import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ControlCluster } from './ControlCluster'

afterEach(cleanup)

function renderCluster(overrides: Partial<Parameters<typeof ControlCluster>[0]> = {}) {
  const props = {
    moveMode: 'fly' as const,
    onCycleMoveMode: vi.fn(),
    shadingMode: 'lit' as const,
    buildSolved: true,
    onSelectShadingMode: vi.fn(),
    activeTray: null,
    onActiveTrayChange: vi.fn(),
    ...overrides,
  }
  render(<ControlCluster {...props} />)
  return props
}

describe('ControlCluster move-mode button', () => {
  it('shows the current mode as a caption', () => {
    renderCluster({ moveMode: 'fly' })
    expect(screen.getByText('Fly')).toBeTruthy()
  })

  it('clicking the move-mode button calls onCycleMoveMode', () => {
    const props = renderCluster({ moveMode: 'fly' })
    fireEvent.click(screen.getByRole('button', { name: 'Move mode' }))
    expect(props.onCycleMoveMode).toHaveBeenCalledTimes(1)
  })

  it("shows 'Pan' when moveMode is 'pan'", () => {
    renderCluster({ moveMode: 'pan' })
    expect(screen.getByText('Pan')).toBeTruthy()
    expect(screen.queryByText('Fly')).toBeNull()
  })

  it('the move-mode button carries a tooltip naming the current mode', () => {
    renderCluster({ moveMode: 'fly' })
    expect(screen.getByRole('button', { name: 'Move mode' }).getAttribute('data-tip')).toBe('Move mode: Fly')
  })
})

describe('ControlCluster shading-mode tray', () => {
  it('shows the current shading mode on the collapsed trigger via its tooltip', () => {
    renderCluster({ shadingMode: 'lit' })
    expect(screen.getByRole('button', { name: 'Shading mode' }).getAttribute('data-tip')).toBe('Shading: Lit')
  })

  it('the tray is closed by default (activeTray is not "shade")', () => {
    renderCluster({ activeTray: null })
    // No @testing-library/jest-dom in this codebase's test setup -- use classList directly, the
    // established convention here (grep confirms no other test file uses toHaveClass).
    expect(
      screen.getByTestId('control-cluster-tile-wireframe').closest('.control-cluster-flyout')?.classList.contains(
        'open',
      ),
    ).toBe(false)
  })

  it('clicking the trigger opens the tray by setting activeTray to "shade"', () => {
    const props = renderCluster({ activeTray: null })
    fireEvent.click(screen.getByRole('button', { name: 'Shading mode' }))
    expect(props.onActiveTrayChange).toHaveBeenCalledWith('shade')
  })

  it('clicking the trigger again (tray already open) closes it', () => {
    const props = renderCluster({ activeTray: 'shade' })
    fireEvent.click(screen.getByRole('button', { name: 'Shading mode' }))
    expect(props.onActiveTrayChange).toHaveBeenCalledWith(null)
  })

  it('the tray is visually open when activeTray is "shade"', () => {
    renderCluster({ activeTray: 'shade' })
    expect(
      screen.getByTestId('control-cluster-tile-wireframe').closest('.control-cluster-flyout')?.classList.contains(
        'open',
      ),
    ).toBe(true)
  })

  it('picking a tile calls onSelectShadingMode and closes the tray', () => {
    const props = renderCluster({ activeTray: 'shade' })
    fireEvent.click(screen.getByTestId('control-cluster-tile-lit'))
    expect(props.onSelectShadingMode).toHaveBeenCalledWith('lit')
    expect(props.onActiveTrayChange).toHaveBeenCalledWith(null)
  })

  it('disables unlit/lit (not wireframe) when the build is not solved', () => {
    renderCluster({ buildSolved: false })
    expect(screen.getByTestId('control-cluster-tile-wireframe').hasAttribute('disabled')).toBe(false)
    expect(screen.getByTestId('control-cluster-tile-unlit').hasAttribute('disabled')).toBe(true)
    expect(screen.getByTestId('control-cluster-tile-lit').hasAttribute('disabled')).toBe(true)
  })

  it('marks the current shading mode pressed on its own tile', () => {
    renderCluster({ shadingMode: 'lit', activeTray: 'shade' })
    expect(screen.getByTestId('control-cluster-tile-lit').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('control-cluster-tile-wireframe').getAttribute('aria-pressed')).toBe('false')
  })
})

describe('ControlCluster mutual exclusion / outside-click dismiss', () => {
  it('a click outside the cluster while the tray is open dismisses it (activeTray -> null)', () => {
    const props = renderCluster({ activeTray: 'shade' })
    fireEvent.pointerDown(document.body)
    expect(props.onActiveTrayChange).toHaveBeenCalledWith(null)
  })

  it('a click INSIDE the cluster (e.g. a tile) does not ALSO fire the outside-dismiss path', () => {
    const props = renderCluster({ activeTray: 'shade' })
    fireEvent.pointerDown(screen.getByTestId('control-cluster-tile-lit'))
    // Only the tile's own onClick should drive onActiveTrayChange (asserted above) -- the document
    // listener must recognize this target as "inside" and no-op.
    expect(props.onActiveTrayChange).not.toHaveBeenCalled()
  })

  it('installs no document listener at all while the tray is closed', () => {
    renderCluster({ activeTray: null })
    const spy = vi.spyOn(document, 'removeEventListener')
    cleanup()
    // If no listener was ever added, there is nothing for this component's own unmount to remove --
    // a real listener leak would show up as an extra call here in a suite that also has the "open"
    // tests above (each adds/removes its own). This just guards against an unconditional effect.
    expect(spy).not.toHaveBeenCalledWith('pointerdown', expect.anything())
  })
})

describe("ControlCluster pointer isolation from Viewport3D's own container", () => {
  // ControlCluster is mounted INSIDE Viewport3D.tsx's containerRef div, which unconditionally
  // calls setPointerCapture and starts tracking a tap/drag on ANY pointerdown that reaches it --
  // if a click on a cluster button bubbles out, it can silently clear the current selection (a
  // raycast miss on release) or, on a small jitter, nudge the camera. Stopping the DOWN event here
  // is what matters: the container's own logic only starts tracking on a pointerdown it actually
  // observed, so a down that never arrives means the corresponding up is never acted on either --
  // this wrapper only needs an onPointerDown spy to prove the guard works, not onPointerUp too.
  function renderInOuterContainer() {
    const outerDown = vi.fn()
    const props = {
      moveMode: 'fly' as const,
      onCycleMoveMode: vi.fn(),
      shadingMode: 'lit' as const,
      buildSolved: true,
      onSelectShadingMode: vi.fn(),
      activeTray: null,
      onActiveTrayChange: vi.fn(),
    }
    render(
      <div onPointerDown={outerDown}>
        <ControlCluster {...props} />
      </div>,
    )
    return { outerDown }
  }

  it('a mouse pointerdown on the move-mode button does not reach the outer container', () => {
    const { outerDown } = renderInOuterContainer()
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Move mode' }), { pointerType: 'mouse' })
    expect(outerDown).not.toHaveBeenCalled()
  })

  it('a mouse pointerdown on a shading tile does not reach the outer container', () => {
    const { outerDown } = renderInOuterContainer()
    fireEvent.pointerDown(screen.getByTestId('control-cluster-tile-lit'), { pointerType: 'mouse' })
    expect(outerDown).not.toHaveBeenCalled()
  })

  it('a touch pointerdown on the move-mode button still does not reach the outer container', () => {
    const { outerDown } = renderInOuterContainer()
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Move mode' }), { pointerType: 'touch' })
    expect(outerDown).not.toHaveBeenCalled()
  })
})
