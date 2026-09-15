// Theme preference (dark/light/system), quad-layout Part 9, Task 30. `resolveEffectiveTheme` is the
// pure piece worth unit-testing; `useTheme` wraps it with `matchMedia`/`localStorage` and sets
// `data-theme` on `<html>` (index.css's tokens key off that attribute).
import { useEffect, useState } from 'react'

export type ThemePreference = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'uedcli-theme-preference'

/** An explicit 'light'/'dark' preference always wins; 'system' follows `prefersDarkMedia` (the
 * live `matchMedia('(prefers-color-scheme: dark)').matches` value). */
export function resolveEffectiveTheme(pref: ThemePreference, prefersDarkMedia: boolean): 'dark' | 'light' {
  if (pref === 'dark') return 'dark'
  if (pref === 'light') return 'light'
  return prefersDarkMedia ? 'dark' : 'light'
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'dark' || stored === 'light' || stored === 'system') return stored
  } catch {
    // localStorage unavailable (private mode, blocked) -- fall back to the default.
  }
  return 'system'
}

export interface UseThemeResult {
  preference: ThemePreference
  effective: 'dark' | 'light'
  setPreference: (pref: ThemePreference) => void
}

/** Owns the theme preference (persisted to `localStorage`), tracks the live OS media query for the
 * 'system' case, and reflects the effective theme onto `<html data-theme>` -- index.css's tokens
 * (`:root[data-theme='light']` / the bare dark `:root` / the `prefers-color-scheme` system-follow
 * block) key off exactly that attribute (or its absence, for 'system'). */
export function useTheme(): UseThemeResult {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference)
  const [prefersDarkMedia, setPrefersDarkMedia] = useState(() => {
    try {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    } catch {
      return true // no matchMedia (old browser/test env) -- default to dark, this app's own default
    }
  })

  useEffect(() => {
    let media: MediaQueryList
    try {
      media = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      return
    }
    const onChange = (e: MediaQueryListEvent) => setPrefersDarkMedia(e.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const effective = resolveEffectiveTheme(preference, prefersDarkMedia)

  useEffect(() => {
    // 'system' leaves `data-theme` UNSET (index.css's own system-follow media block applies then);
    // an explicit choice sets it, so it wins over the OS preference in both directions.
    if (preference === 'system') {
      document.documentElement.removeAttribute('data-theme')
    } else {
      document.documentElement.setAttribute('data-theme', preference)
    }
  }, [preference])

  const setPreference = (pref: ThemePreference) => {
    setPreferenceState(pref)
    try {
      localStorage.setItem(STORAGE_KEY, pref)
    } catch {
      // Persistence is a nicety -- a blocked localStorage just means the choice doesn't survive a reload.
    }
  }

  return { preference, effective, setPreference }
}
