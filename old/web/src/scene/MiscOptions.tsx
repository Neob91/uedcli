// Misc-options icon (viewport-control-redesign-icon-cluster-replaces spec, "Misc-options icon"):
// replaces QuadLayout.tsx's old always-visible `.quad-toolbar` (Movers/Radii/Grid). Deliberately a
// SEPARATE component from ControlCluster (move-mode + shading-mode, Viewport3D.tsx) -- per the
// spec's "Ownership split", this one stays owned/rendered at the QuadLayout level so it's reachable
// even while a non-perspective pane is maximized (Viewport3D, and ControlCluster with it, aren't
// rendered at all then), and because Grid's own effect (OrthoViewport's GridOverlay) has nothing to
// do with the perspective pane. Positioned by plain CSS (index.css's `.misc-options`, anchored to
// `.quad-layout` itself) -- see that rule's own comment for why no JS positioning logic is needed.
import { useEffect, useRef } from 'react'

import type { ActiveTray } from './ControlCluster'
import { GRID_SIZE_OPTIONS } from './grid'
import { GridIcon, MiscIcon, MoversIcon, RadiiIcon } from './icons'
import { useHoldTooltip } from './useHoldTooltip'

export interface MiscOptionsProps {
  showMoverSolid: boolean
  onToggleMoverSolid: () => void
  showRadii: boolean
  onToggleRadii: () => void
  showGrid: boolean
  onToggleGrid: () => void
  baseGridSize: number
  onChangeGridSize: (size: number) => void
  activeTray: ActiveTray
  onActiveTrayChange: (tray: ActiveTray) => void
}

export function MiscOptions({
  showMoverSolid,
  onToggleMoverSolid,
  showRadii,
  onToggleRadii,
  showGrid,
  onToggleGrid,
  baseGridSize,
  onChangeGridSize,
  activeTray,
  onActiveTrayChange,
}: MiscOptionsProps) {
  const open = activeTray === 'misc'
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current?.contains(e.target as Node)) return
      onActiveTrayChange(null)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, onActiveTrayChange])

  const triggerTip = useHoldTooltip('Misc options')
  const moversTip = useHoldTooltip(`Movers: ${showMoverSolid ? 'on' : 'off'}`)
  const radiiTip = useHoldTooltip(`Radii: ${showRadii ? 'on' : 'off'}`)
  const gridTip = useHoldTooltip(`Grid: ${showGrid ? 'on' : 'off'}`)

  return (
    <div className="misc-options" ref={rootRef}>
      <button
        type="button"
        className="misc-options-btn"
        aria-label="Misc options"
        aria-expanded={open}
        onClick={() => onActiveTrayChange(open ? null : 'misc')}
        {...triggerTip}
      >
        <MiscIcon />
      </button>
      <div className={`misc-options-flyout${open ? ' open' : ''}`}>
        <button
          type="button"
          className={`misc-options-toggle${showMoverSolid ? ' on' : ''}`}
          aria-label="Movers"
          aria-pressed={showMoverSolid}
          onClick={onToggleMoverSolid}
          {...moversTip}
        >
          <MoversIcon />
        </button>
        <button
          type="button"
          className={`misc-options-toggle${showRadii ? ' on' : ''}`}
          aria-label="Radii"
          aria-pressed={showRadii}
          onClick={onToggleRadii}
          {...radiiTip}
        >
          <RadiiIcon />
        </button>
        <button
          type="button"
          className={`misc-options-toggle${showGrid ? ' on' : ''}`}
          aria-label="Grid"
          aria-pressed={showGrid}
          onClick={onToggleGrid}
          {...gridTip}
        >
          <GridIcon />
        </button>
        {/* Exception to the hold-tooltip mechanism (spec, "Tooltips"): a native <select>'s
            tap-to-open-picker behavior is OS/browser-owned and can't be reliably pre-empted by the
            custom hold gesture the way a button can -- this control keeps the browser's own native
            tooltip (a plain `title`) instead. */}
        <span className="misc-options-select-wrap" title="Grid size">
          <select
            aria-label="Grid size"
            value={baseGridSize}
            disabled={!showGrid}
            onChange={(e) => onChangeGridSize(Number(e.target.value))}
          >
            {GRID_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </span>
      </div>
    </div>
  )
}
