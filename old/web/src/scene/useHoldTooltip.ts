// Shared hover/hold-vs-tap tooltip mechanism (viewport-control-redesign-icon-cluster-replaces spec,
// "Tooltips"): hover shows a tooltip on desktop (plain CSS, index.css's `[data-tip]:hover` -- no JS
// needed for that half). Touch has no hover, so a press-and-hold past HOLD_MS shows the same
// tooltip and suppresses the tap's normal click action on release; a plain tap (released before
// HOLD_MS) still performs it. Returns props to spread directly onto the tooltip-bearing element.
//
// Not used for the misc-options grid-size <select> (spec, "Tooltips" exception): a native <select>'s
// tap-to-open-picker behavior is OS/browser-owned and can't be reliably pre-empted by this hold
// gesture the way a custom button can -- that one control keeps the browser's own native tooltip
// behavior (a plain `title` attribute) instead. See MiscOptions.tsx.
import { useCallback, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from 'react'

const HOLD_MS = 500

export interface HoldTooltipProps {
  'data-tip': string
  'data-tip-active': 'true' | undefined
  onPointerDown: (e: ReactPointerEvent<HTMLElement>) => void
  onPointerUp: (e: ReactPointerEvent<HTMLElement>) => void
  onPointerCancel: (e: ReactPointerEvent<HTMLElement>) => void
  onClickCapture: (e: ReactMouseEvent<HTMLElement>) => void
}

export function useHoldTooltip(label: string): HoldTooltipProps {
  const [active, setActive] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const suppressRef = useRef(false)

  const clear = useCallback(() => {
    if (timerRef.current !== null) clearTimeout(timerRef.current)
    timerRef.current = null
    setActive(false)
  }, [])

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    if (e.pointerType === 'mouse') return // mouse relies on plain CSS :hover
    suppressRef.current = false
    timerRef.current = setTimeout(() => {
      setActive(true)
      suppressRef.current = true
    }, HOLD_MS)
  }, [])

  const onPointerUp = useCallback(() => clear(), [clear])
  const onPointerCancel = useCallback(() => clear(), [clear])

  // Capture phase: runs before the element's own onClick, so it can veto a click that follows a
  // hold past HOLD_MS -- a hold-to-peek must never also perform the button's action.
  const onClickCapture = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    if (suppressRef.current) {
      e.stopPropagation()
      e.preventDefault()
      suppressRef.current = false
    }
  }, [])

  return {
    'data-tip': label,
    'data-tip-active': active ? 'true' : undefined,
    onPointerDown,
    onPointerUp,
    onPointerCancel,
    onClickCapture,
  }
}
