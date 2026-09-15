// Visible per-pane shading-mode control (owner ask: an actual UI control, not just the hidden `1`-`4`
// keyboard shortcuts -- QuadLayout.tsx's applyModeKey). Scope is fullbright/lit/wireframe only (the
// owner's own words); 'flat' stays keyboard-only (`3`) and out of this control.
import { isModeAvailable } from './shadingMode'
import type { ShadingMode } from './shadingMode'

// Label 'unlit' as "Fullbright" -- the owner's/CLI's own name for this mode (`preview.py --mode
// fullbright`, dev/docs/GUI.md's Shading modes section), not this codebase's internal 'unlit' spelling.
const VISIBLE_MODES: { mode: ShadingMode; label: string }[] = [
  { mode: 'wireframe', label: 'Wireframe' },
  { mode: 'unlit', label: 'Fullbright' },
  { mode: 'lit', label: 'Lit' },
]

export function ModeSelector({
  mode,
  buildSolved,
  onSelect,
}: {
  mode: ShadingMode
  buildSolved: boolean
  onSelect: (mode: ShadingMode) => void
}) {
  return (
    <div className="mode-selector" role="group" aria-label="Shading mode">
      {VISIBLE_MODES.map(({ mode: m, label }) => {
        const available = isModeAvailable(m, buildSolved)
        return (
          <button
            key={m}
            type="button"
            className="mode-selector-btn"
            data-testid={`mode-btn-${m}`}
            aria-pressed={mode === m}
            disabled={!available}
            title={available ? label : `${label} needs a solved build`}
            onClick={() => onSelect(m)}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
