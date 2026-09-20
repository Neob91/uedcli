// Which physical input the move joystick (`MoveJoystick.tsx`) should assume the user is on right
// now -- INPUT-DRIVEN, not a one-time device capability guess (that was `touchCapability.ts`, now
// removed): games switch their on-screen prompts (controller vs. keyboard/mouse) based on the last
// input actually used, and this mirrors that. A real touch starts it; a real keyboard press or mouse
// click ends it -- a `pen` pointer is deliberately a no-op (owner ruling, 2026-09-20): a stylus is
// usually paired with a keyboard-less tablet, the exact device this control exists for, so treating
// it like a mouse would hide the joystick on the one device that most needs it. Default is
// `'desktop'` (hidden) until the FIRST real touch, so a device that merely CAN receive touch (a
// touch-capable laptop that's never actually touched) doesn't show it unprompted.
//
// Mirrors `useCollapsiblePanel.ts`'s split: a pure, unit-testable reducer (`nextInputMode`) wrapped
// by a hook that owns the live global-listener/`localStorage` plumbing.
import { useEffect, useRef, useState } from 'react'

export type InputMode = 'touch' | 'desktop'

const STORAGE_KEY = 'uedcli-joystick-input-mode'

export type InputModeEvent = { kind: 'pointerdown'; pointerType: string } | { kind: 'keydown' }

/** Pure reducer: a touch pointer switches to `'touch'`; a mouse pointer or any keypress switches to
 * `'desktop'`; anything else (a `pen` pointer, or an unrecognized `pointerType`) is a no-op. */
export function nextInputMode(current: InputMode, event: InputModeEvent): InputMode {
  if (event.kind === 'keydown') return 'desktop'
  if (event.pointerType === 'touch') return 'touch'
  if (event.pointerType === 'mouse') return 'desktop'
  return current
}

function readStoredMode(): InputMode | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'touch' || stored === 'desktop') return stored
  } catch {
    // localStorage unavailable (private mode, blocked) -- fall back to the default.
  }
  return null
}

/** `'desktop'` (hidden) until the device's own history says otherwise -- either a real touch this
 * session, or a `'touch'` choice persisted from a previous one. */
export function useInputMode(): InputMode {
  const [mode, setMode] = useState<InputMode>(() => readStoredMode() ?? 'desktop')
  // A ref, not `mode` itself, so the single effect below (installed once on mount) always reduces
  // against the CURRENT mode rather than the value captured when the listeners were attached. Its
  // ONLY writer is `apply` below, which updates it in lockstep with `setMode` -- so it never needs a
  // separate sync effect (and never risks the "mutating a ref during render" pitfall that would
  // cause) to stay correct.
  const modeRef = useRef(mode)

  useEffect(() => {
    const apply = (event: InputModeEvent) => {
      const next = nextInputMode(modeRef.current, event)
      if (next === modeRef.current) return
      modeRef.current = next
      setMode(next)
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        // Persistence is a nicety -- a blocked localStorage just means the choice doesn't survive a reload.
      }
    }
    const onPointerDown = (e: PointerEvent) => apply({ kind: 'pointerdown', pointerType: e.pointerType })
    const onKeyDown = () => apply({ kind: 'keydown' })
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  return mode
}
