// Move-mode + shading-mode icon cluster (viewport-control-redesign-icon-cluster-replaces spec):
// replaces MoveJoystick.tsx (touch joystick + up/down buttons) and ModeSelector.tsx (the
// always-visible 3-button shading row). Rendered inside Viewport3D.tsx's own pointer container, the
// exact spot the joystick used to occupy -- perspective-pane-scoped state (move-mode, shading-mode)
// stays owned/rendered here, per the spec's "Ownership split". Misc-options is a SEPARATE component
// (MiscOptions.tsx, owned/rendered by QuadLayout.tsx) -- do not merge the two into one shared
// container; that would reintroduce the reachability regression a prior review caught.
import { useCallback, useEffect, useRef } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactElement } from 'react'

import { FlyIcon, FullbrightIcon, LitIcon, PanIcon, WireframeIcon } from './icons'
import type { MoveMode } from './moveMode'
import { isModeAvailable } from './shadingMode'
import type { ShadingMode } from './shadingMode'
import { useHoldTooltip } from './useHoldTooltip'

export type ActiveTray = 'shade' | 'misc' | null

const MOVE_MODE_LABEL: Record<MoveMode, string> = { fly: 'Fly', pan: 'Pan' }

// ReactElement, not a bare `JSX.Element` -- that ambient global isn't safe to assume resolves
// unqualified across React/TS version bumps (recent @types/react releases have been shifting it
// under React.JSX), and nothing else in this codebase relies on it.
const SHADING_TILES: { mode: ShadingMode; label: string; Icon: () => ReactElement }[] = [
  { mode: 'wireframe', label: 'Wireframe', Icon: WireframeIcon },
  { mode: 'unlit', label: 'Fullbright', Icon: FullbrightIcon },
  { mode: 'lit', label: 'Lit', Icon: LitIcon },
]

export interface ControlClusterProps {
  moveMode: MoveMode
  onCycleMoveMode: () => void
  shadingMode: ShadingMode
  buildSolved: boolean
  onSelectShadingMode: (mode: ShadingMode) => void
  activeTray: ActiveTray
  onActiveTrayChange: (tray: ActiveTray) => void
}

function ShadingTile({
  mode,
  label,
  Icon,
  current,
  available,
  onPick,
}: {
  mode: ShadingMode
  label: string
  Icon: () => ReactElement
  current: ShadingMode
  available: boolean
  onPick: (mode: ShadingMode) => void
}) {
  const tip = useHoldTooltip(available ? label : `${label} needs a solved build`)
  return (
    <button
      type="button"
      className="control-cluster-tile"
      data-testid={`control-cluster-tile-${mode}`}
      aria-pressed={current === mode}
      disabled={!available}
      onClick={() => onPick(mode)}
      {...tip}
    >
      <Icon />
    </button>
  )
}

export function ControlCluster({
  moveMode,
  onCycleMoveMode,
  shadingMode,
  buildSolved,
  onSelectShadingMode,
  activeTray,
  onActiveTrayChange,
}: ControlClusterProps) {
  const shadeOpen = activeTray === 'shade'
  const rootRef = useRef<HTMLDivElement | null>(null)

  // Dismissing without picking (spec): app-wide, not scoped to this pane -- a tap on the
  // Inspector/org panel while the tray is open must still close it. A click INSIDE this component
  // (the trigger, or a tile) is left alone; those manage activeTray through their own onClick.
  useEffect(() => {
    if (!shadeOpen) return
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current?.contains(e.target as Node)) return
      onActiveTrayChange(null)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [shadeOpen, onActiveTrayChange])

  const toggleShadeTray = useCallback(() => {
    onActiveTrayChange(shadeOpen ? null : 'shade')
  }, [shadeOpen, onActiveTrayChange])

  // Picking a tile applies it but leaves the tray open (owner call) -- close it the same two ways
  // as dismissing without picking: click the trigger button again, or click/tap elsewhere.
  const pickShadingMode = useCallback(
    (mode: ShadingMode) => {
      onSelectShadingMode(mode)
    },
    [onSelectShadingMode],
  )

  // Neutralizes Viewport3D.tsx's own container div, which unconditionally captures the pointer and
  // starts tracking a tap/drag for ANY pointerdown that reaches it -- touch (single-finger
  // look-rotation) AND mouse (tap-select on a miss, or camera drag) alike. A mouse click on a
  // cluster button that isn't stopped here bubbles straight through and can silently clear the
  // current actor selection or nudge the camera. This component's interactions are simple taps,
  // not a multi-event drag, so one stopPropagation here is enough; no per-element pointer capture
  // is needed the way the joystick's own drag gesture required.
  const onWrapperPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
  }, [])

  const moveTip = useHoldTooltip(`Move mode: ${MOVE_MODE_LABEL[moveMode]}`)
  const currentTileLabel = SHADING_TILES.find((t) => t.mode === shadingMode)?.label ?? shadingMode
  const shadeTip = useHoldTooltip(`Shading: ${currentTileLabel}`)

  return (
    <div className="control-cluster" ref={rootRef} onPointerDown={onWrapperPointerDown}>
      <div className="control-cluster-item">
        <button
          type="button"
          className="control-cluster-btn"
          aria-label="Move mode"
          onClick={onCycleMoveMode}
          {...moveTip}
        >
          {moveMode === 'fly' ? <FlyIcon /> : <PanIcon />}
        </button>
        <span className="control-cluster-caption">{MOVE_MODE_LABEL[moveMode]}</span>
      </div>
      <div className="control-cluster-item">
        <button
          type="button"
          className="control-cluster-btn"
          aria-label="Shading mode"
          aria-expanded={shadeOpen}
          onClick={toggleShadeTray}
          {...shadeTip}
        >
          {shadingMode === 'wireframe' ? <WireframeIcon /> : shadingMode === 'lit' ? <LitIcon /> : <FullbrightIcon />}
        </button>
        <div className={`control-cluster-flyout${shadeOpen ? ' open' : ''}`}>
          {SHADING_TILES.map(({ mode, label, Icon }) => (
            <ShadingTile
              key={mode}
              mode={mode}
              label={label}
              Icon={Icon}
              current={shadingMode}
              available={isModeAvailable(mode, buildSolved)}
              onPick={pickShadingMode}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
