// Session identity, carried in the URL (persistent-GUI-editing-sessions plan, Task 16) -- replaces
// the old in-process `PUT /api/level` level switch: a session, not a level, is now the unit of
// navigation. Follows this codebase's existing plain-hook convention (theme/useTheme.ts,
// layout/useSidebar.ts) rather than React's Context API -- App.tsx mounts `useSession()` once and
// threads the result down as props, same as every other piece of lifted state here; the file is
// still named "Context" per this plan's own interface naming, not because it uses `createContext`.
import { useCallback, useEffect, useRef, useState } from 'react'

import type { SessionDetail, SessionRecord } from '../api'
import { createSession as postCreateSession, fetchLevels, fetchSession } from '../api'

export type SessionView = 'editing' | 'notfound' | 'closed' | 'superseded'

export interface SessionState {
  sessionId: string | null
  level: string | null
  view: SessionView
  claimToken: string | null
}

export interface UseSessionResult extends SessionState {
  // Explicitly starts a brand-new session on `level`, overwriting the URL's `?session=` and
  // whatever session was previously active -- distinct from the auto-create `reload()` performs
  // when the URL has no session id at all.
  createSession: (level: string) => void
  // Re-resolves the CURRENT `?session=` from the URL (or auto-creates, if there is none) -- the
  // ONE navigation primitive this hook exposes. A session switch (SessionDropdown) writes the new
  // id into the URL first, then calls this to pick it up; a page load with a `?session=` already
  // present does the same thing at mount, through the exact same code path. It's also what the
  // superseded takeover's own Reload button calls: `fetchSession` mints a FRESH claim token on
  // every call, re-claiming the session for THIS window (superseding whichever window is holding it
  // now), and flips `view` back to 'editing' on success.
  reload: () => void
  // Flips `view` to 'superseded' (Task 17) -- fired by the `/ws` "superseded" push (reload.ts) or a
  // mutating call's 409 (`isSupersededError`, the fallback path for whenever that push was lost).
  // Leaves `sessionId`/`level`/`claimToken` untouched: there's nothing wrong with them, the session
  // itself just isn't this window's to edit anymore until `reload()` reclaims it.
  markSuperseded: () => void
}

const SESSION_PARAM = 'session'

const INITIAL_STATE: SessionState = { sessionId: null, level: null, view: 'editing', claimToken: null }

function readSessionIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get(SESSION_PARAM)
}

function writeSessionIdToUrl(id: string): void {
  const url = new URL(window.location.href)
  url.searchParams.set(SESSION_PARAM, id)
  window.history.replaceState(null, '', url.toString())
}

/** Owns the session id carried in the URL. `resolvedIdsRef` is what tells apart a `?session=` id
 * that has NEVER resolved (a bad/garbage id typed or pasted into the URL -- `view: 'notfound'`,
 * per the spec's "no auto-create") from one that resolved fine before and has now started failing
 * (this tab's own session was closed elsewhere -- `view: 'closed'`, per the spec's "no
 * auto-navigate"). `closed` is reached by `reload()` re-resolving an id this hook already knows was
 * good and finding it 404 now (the session was deleted); `superseded` (below) is the DIFFERENT
 * live-close signal for a session that still exists but whose claim this window no longer holds --
 * the `/ws` "superseded" push (reload.ts) or a mutating call's 409, wired in App.tsx. */
export function useSession(): UseSessionResult {
  const [state, setState] = useState<SessionState>(INITIAL_STATE)
  const resolvedIdsRef = useRef<Set<string>>(new Set())

  const activate = useCallback((rec: SessionRecord | SessionDetail) => {
    writeSessionIdToUrl(rec.id)
    resolvedIdsRef.current.add(rec.id)
    setState({ sessionId: rec.id, level: rec.level, claimToken: rec.claim_token, view: 'editing' })
  }, [])

  const createSession = useCallback(
    (level: string) => {
      postCreateSession(level)
        .then(activate)
        .catch((e: unknown) => {
          // Nothing in this hook's produced state has room for a bootstrap-failure message (the
          // spec's view enum is editing/notfound/closed, not "error") -- surfaced to the console
          // rather than silently swallowed.
          console.error('createSession failed', e)
        })
    },
    [activate],
  )

  const reload = useCallback(() => {
    const existingId = readSessionIdFromUrl()
    if (existingId) {
      fetchSession(existingId)
        .then(activate)
        .catch(() => {
          setState({
            sessionId: existingId,
            level: null,
            claimToken: null,
            view: resolvedIdsRef.current.has(existingId) ? 'closed' : 'notfound',
          })
        })
      return
    }
    // No session id in the URL at all -- auto-create one on the project's default level. A bare
    // URL with no session id IS a real page load (the spec's "a session is created only by a real
    // page load, never automatically" is about `LevelContext`s, not this).
    fetchLevels()
      .then((payload) => {
        const defaultLevel = payload.current || payload.levels[0]?.name
        if (!defaultLevel) throw new Error('no levels available to create a session on')
        return postCreateSession(defaultLevel)
      })
      .then(activate)
      .catch((e: unknown) => console.error('session bootstrap failed', e))
  }, [activate])

  // `reload` is a stable callback (its own deps -- `activate`'s deps -- never change), so this is
  // mount-only: a session switch re-invokes `reload` explicitly (App.tsx's own handler), not by
  // this effect re-running.
  useEffect(() => {
    reload()
  }, [reload])

  const markSuperseded = useCallback(() => {
    setState((s) => ({ ...s, view: 'superseded' }))
  }, [])

  return { ...state, createSession, reload, markSuperseded }
}
