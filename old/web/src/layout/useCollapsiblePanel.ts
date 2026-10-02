// Collapsible sidebar state (mobile/laptop layout spec, owner-approved 2026-09-18): `.org-panel` and
// `.inspector-pane` each get their own independent toggle, defaulting collapsed below a narrow-window
// breakpoint / open above it -- until the user manually toggles, at which point that choice persists
// via `localStorage` and overrides the responsive default from then on (this device/browser only).
// Mirrors `theme/useTheme.ts`'s split: a pure, unit-testable resolver (`resolveCollapsed`) wrapped by
// a hook that owns the live `window.innerWidth`/`localStorage` plumbing.
import { useEffect, useState } from 'react'

// A common tablet/mobile cutoff -- below it, the org/inspector panels (220px + 280px = 500px
// combined) would dominate the screen; above it there's room for both sidebars AND a usable
// viewport. The exact pixel value is an implementation judgment call (not owner-specified).
export const SIDEBAR_COLLAPSE_BREAKPOINT_PX = 768

// `null` = never manually toggled -- the responsive default applies. An explicit choice always wins
// over the breakpoint, in either direction (a wide window with a manually-collapsed panel stays
// collapsed; a narrow window with a manually-opened panel stays open).
export type CollapseChoice = 'collapsed' | 'expanded' | null

/** Pure resolver: an explicit `choice` always wins; otherwise collapse below `breakpoint`. */
export function resolveCollapsed(choice: CollapseChoice, viewportWidth: number, breakpoint: number): boolean {
  if (choice === 'collapsed') return true
  if (choice === 'expanded') return false
  return viewportWidth < breakpoint
}

function readStoredChoice(storageKey: string): CollapseChoice {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored === 'collapsed' || stored === 'expanded') return stored
  } catch {
    // localStorage unavailable (private mode, blocked) -- fall back to the responsive default.
  }
  return null
}

export interface UseCollapsiblePanelResult {
  collapsed: boolean
  toggle: () => void
}

/** `storageKey` must be unique per panel (e.g. one for the org panel, a different one for the
 * inspector pane) -- each sidebar toggles independently, per the owner-approved spec. */
export function useCollapsiblePanel(
  storageKey: string,
  breakpoint: number = SIDEBAR_COLLAPSE_BREAKPOINT_PX,
): UseCollapsiblePanelResult {
  const [choice, setChoiceState] = useState<CollapseChoice>(() => readStoredChoice(storageKey))
  const [viewportWidth, setViewportWidth] = useState(() => {
    try {
      return window.innerWidth
    } catch {
      return 1920 // no `window` (test env) -- default to a wide desktop width
    }
  })

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const toggle = () => {
    const collapsedNow = resolveCollapsed(choice, viewportWidth, breakpoint)
    const next: CollapseChoice = collapsedNow ? 'expanded' : 'collapsed'
    setChoiceState(next)
    try {
      localStorage.setItem(storageKey, next)
    } catch {
      // Persistence is a nicety -- a blocked localStorage just means the choice doesn't survive a reload.
    }
  }

  return { collapsed: resolveCollapsed(choice, viewportWidth, breakpoint), toggle }
}
