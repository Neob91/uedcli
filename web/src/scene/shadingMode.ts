// Per-pane shading-mode state + solved-build gating (quad-layout Part 4, Task 18/20, spec §3).
// Wireframe renders from ScenePoly/brush.polys data directly (no solve dependency); the other three
// reuse the existing resolveMaterialState/buildGeometryData machinery, which needs a SOLVED build
// (the gui-explicit-rebuild-pinned-build-state-mode item's own "wireframe always available" rule --
// this plan consumes that signal, it does not redefine it).
import type { PaneId } from './paneLayout'

export type ShadingMode = 'wireframe' | 'unlit' | 'flat' | 'lit'

/** `'wireframe'` is always available; the other three need a solved build. */
export function isModeAvailable(mode: ShadingMode, buildSolved: boolean): boolean {
  return mode === 'wireframe' || buildSolved
}

/** The mode a pane actually renders in: `requested` when available, else `'wireframe'` (e.g. a pane
 * left on `'lit'` before a level with no solved build loads). */
export function resolveEffectiveMode(requested: ShadingMode, buildSolved: boolean): ShadingMode {
  return isModeAvailable(requested, buildSolved) ? requested : 'wireframe'
}

/** `'unlit'` and `'flat'` both draw the lightmap-free material set (bug fix: this used to check
 * only `'unlit'`, silently rendering `'flat'` identically to `'lit'` -- contradicting the `mode`
 * prop's own doc comment in Viewport3D.tsx/OrthoViewport.tsx). Only `'lit'`/`'wireframe'` don't. */
export function usesUnlitMaterials(mode: ShadingMode): boolean {
  return mode === 'unlit' || mode === 'flat'
}

const KEY_TO_MODE: Record<'1' | '2' | '3' | '4', ShadingMode> = {
  '1': 'wireframe',
  '2': 'unlit',
  '3': 'flat',
  '4': 'lit',
}

/** `1`-`4` sets the FOCUSED pane's requested mode (main spec's keybindings, Task 20) -- a no-op
 * (returns the SAME `current` object, not an equivalent copy, so a caller's `setState` doesn't
 * spuriously re-render) when the requested mode isn't available yet (e.g. `buildSolved=false` and
 * the key requests anything but wireframe). */
export function applyModeKey(
  current: Record<PaneId, ShadingMode>,
  focused: PaneId,
  key: '1' | '2' | '3' | '4',
  buildSolved: boolean,
): Record<PaneId, ShadingMode> {
  const requested = KEY_TO_MODE[key]
  if (!isModeAvailable(requested, buildSolved)) return current
  return { ...current, [focused]: requested }
}
