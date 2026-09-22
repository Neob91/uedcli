// Hand-authored inline SVG icons for the move-mode/shading-mode/misc-options control cluster
// (viewport-control-redesign-icon-cluster-replaces spec, "Icons") -- first icons of their kind in
// this app (today's controls use plain unicode glyphs); deliberately no icon library/font
// dependency. Sized by the consuming CSS (e.g. `.control-cluster-btn svg`), not by width/height
// attributes here.
const STROKE_PROPS = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function FlyIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <path d="M4 15 L12 6 L20 15" />
      <path d="M12 6 v13" />
      <path d="M15 3.5 a5 5 0 0 1 3 3" />
    </svg>
  )
}

export function PanIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <path d="M12 2 L9 6 h6 z" fill="currentColor" stroke="none" />
      <path d="M12 22 L9 18 h6 z" fill="currentColor" stroke="none" />
      <path d="M2 12 L6 9 v6 z" fill="currentColor" stroke="none" />
      <path d="M22 12 L18 9 v6 z" fill="currentColor" stroke="none" />
      <path d="M12 8 v8 M8 12 h8" />
    </svg>
  )
}

export function WireframeIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <path d="M5 8 L12 4 L19 8 L19 16 L12 20 L5 16 Z" />
      <path d="M5 8 L12 12 L19 8 M12 12 V20" />
    </svg>
  )
}

export function FullbrightIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="5" width="14" height="14" rx="1.5" fill="currentColor" />
    </svg>
  )
}

export function LitIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <path d="M5 8 L12 4 L19 8 L19 16 L12 20 L5 16 Z" />
      <path d="M12 4 L12 12 L19 8 Z" fill="currentColor" fillOpacity={0.55} stroke="none" />
      <path d="M12 12 L19 8 L19 16 L12 20 Z" fill="currentColor" fillOpacity={0.25} stroke="none" />
    </svg>
  )
}

export function MiscIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="7" cy="7" r="1.6" fill="currentColor" />
      <circle cx="12" cy="7" r="1.6" fill="currentColor" />
      <circle cx="17" cy="7" r="1.6" fill="currentColor" />
      <circle cx="7" cy="12" r="1.6" fill="currentColor" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
      <circle cx="17" cy="12" r="1.6" fill="currentColor" />
    </svg>
  )
}

export function MoversIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <rect x="4" y="9" width="10" height="6" rx="1" />
      <path d="M16 12 H20 M17.5 9.5 L20 12 L17.5 14.5" />
    </svg>
  )
}

export function RadiiIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 12 L18 12" />
      <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function GridIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <path d="M4 9 H20 M4 15 H20 M9 4 V20 M15 4 V20" />
      <rect x="4" y="4" width="16" height="16" rx="1.5" />
    </svg>
  )
}
