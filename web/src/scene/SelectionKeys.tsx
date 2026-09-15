// `F` frame / `Esc` deselect keybinds (quad-layout Part 3, Task 15, spec §9 + the main spec's
// "Keybindings"). A window-keydown listener, mirroring Viewport3D.tsx's `FlyKeys` component
// pattern (same `isTypingTarget` guard against stealing keystrokes from a focused text input).
import { useEffect } from 'react'

function isTypingTarget(t: EventTarget | null): boolean {
  return t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}

export interface SelectionKeysProps {
  selectedNames: ReadonlySet<string>
  onFrame: (names: ReadonlySet<string>) => void
  onDeselect: () => void
}

/** `F` (guarded by `isTypingTarget`, like `FlyKeys`) calls `onFrame(selectedNames)` -- a no-op
 * downstream when the set is empty (`unionBBox([])` returns `null`, `frame.ts`), not gated here
 * itself. `Esc` calls `onDeselect()` UNCONDITIONALLY, even while a text input has focus -- the main
 * spec states it as a plain, unmodified binding, unlike `F`'s typing-target guard. */
export function SelectionKeys({ selectedNames, onFrame, onDeselect }: SelectionKeysProps) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onDeselect()
        return
      }
      if ((e.key === 'f' || e.key === 'F') && !isTypingTarget(e.target)) {
        onFrame(selectedNames)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedNames, onFrame, onDeselect])

  return null
}
