// Dependency-free routing (spec decision 2): two screens don't justify a router library. `navigate`
// uses `pushState` (not `replaceState` -- the picker and the editor are genuinely different
// screens; back/forward should move between them) and notifies every mounted `useRoute` subscriber
// synchronously, since `pushState` itself fires no browser event. `popstate` (real back/forward)
// is handled the ordinary way, through the same listener set.
import { useEffect, useState } from 'react'

export type Route = { screen: 'picker' } | { screen: 'session'; id: string }

const SESSION_PATH = /^\/session\/([^/]+)\/?$/

export function parseRoute(pathname: string): Route {
  const match = SESSION_PATH.exec(pathname)
  if (match) return { screen: 'session', id: decodeURIComponent(match[1]) }
  return { screen: 'picker' }
}

type Listener = () => void
const listeners = new Set<Listener>()

/** Pushes a new path and notifies every mounted `useRoute` immediately -- `pushState` alone fires
 * no event, so without this, navigating would only ever be visible after the NEXT unrelated
 * re-render. */
export function navigate(path: string): void {
  window.history.pushState(null, '', path)
  listeners.forEach((listener) => listener())
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname))

  useEffect(() => {
    const listener = () => setRoute(parseRoute(window.location.pathname))
    listeners.add(listener)
    window.addEventListener('popstate', listener)
    return () => {
      listeners.delete(listener)
      window.removeEventListener('popstate', listener)
    }
  }, [])

  return route
}
