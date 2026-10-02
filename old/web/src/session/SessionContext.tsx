// Session identity (persistent-GUI-editing-sessions plan, Task 16; redesigned for path-based
// routing, session-management-UI spec). Follows this codebase's existing plain-hook convention
// (theme/useTheme.ts, layout/useSidebar.ts) rather than React's Context API -- App.tsx mounts
// `useSession(sessionId)` once per mounted `SessionEditor` and threads the result down as props.
//
// The session id is now an ARGUMENT, not something this hook reads from the URL itself: `App.tsx`
// already parses the route (`route.ts`) to decide whether to render the picker or the editor, so it
// already has the id in hand by the time it mounts a `SessionEditor`. This hook owns none of the
// URL -- creating a session (the picker) and switching between them (the dropdown) both navigate
// via `route.ts`'s own `navigate()`, never through here.
import { useCallback, useEffect, useRef, useState } from 'react'

import type { SessionDetail } from '../api'
import { fetchSession } from '../api'

export type SessionView = 'editing' | 'notfound' | 'closed' | 'superseded'

export interface SessionState {
  sessionId: string | null
  level: string | null
  view: SessionView
  claimToken: string | null
  name: string | null
}

export interface UseSessionResult extends SessionState {
  // Re-resolves the CURRENT sessionId argument: mints a FRESH claim token, re-claiming the session
  // for THIS window (superseding whichever window is holding it now), and flips `view` back to
  // 'editing' on success. Fires on mount, whenever `sessionId` itself changes, and from the
  // superseded-takeover banner's own Reload button.
  reload: () => void
  // Flips `view` to 'superseded' -- fired by the `/ws` "superseded" push (reload.ts) or a mutating
  // call's 409 (`isSupersededError`). Leaves `sessionId`/`level`/`claimToken` untouched: nothing is
  // wrong with them, the session just isn't this window's to edit until `reload()` reclaims it.
  markSuperseded: () => void
  // Flips `view` to 'closed' -- fired by the `/ws` "closed" push or a mutating call's 409
  // (`isClosedError`). The session is genuinely gone; there is nothing to reclaim.
  markClosed: () => void
}

const INITIAL_STATE: SessionState = { sessionId: null, level: null, view: 'editing', claimToken: null, name: null }

/** `resolvedIdsRef` tells apart a `sessionId` that has NEVER resolved (a bad/garbage id -- `view:
 * 'notfound'`) from one that resolved fine before and has now started failing (this tab's own
 * session was closed elsewhere -- `view: 'closed'`, reached by `reload()` re-resolving an id this
 * hook already knew was good and finding it 404 now). */
export function useSession(sessionId: string): UseSessionResult {
  const [state, setState] = useState<SessionState>(INITIAL_STATE)
  const resolvedIdsRef = useRef<Set<string>>(new Set())
  // Per-call sequence guard: `reload()` is a fire-and-forget promise chain with no cancellation --
  // calling it twice in quick succession (a rapid `sessionId` change, or a slow response arriving
  // after a newer one already landed) could otherwise let the SLOWER response commit AFTER the
  // faster one and overwrite fresher state with stale data.
  const seqRef = useRef(0)

  const activate = useCallback((rec: SessionDetail) => {
    resolvedIdsRef.current.add(rec.id)
    setState({ sessionId: rec.id, level: rec.level, claimToken: rec.claim_token, view: 'editing', name: rec.name })
  }, [])

  const reload = useCallback(() => {
    const mySeq = ++seqRef.current
    fetchSession(sessionId)
      .then((rec) => {
        if (seqRef.current !== mySeq) return
        activate(rec)
      })
      .catch(() => {
        if (seqRef.current !== mySeq) return
        setState({
          sessionId,
          level: null,
          claimToken: null,
          name: null,
          view: resolvedIdsRef.current.has(sessionId) ? 'closed' : 'notfound',
        })
      })
  }, [sessionId, activate])

  // Re-fires on mount AND whenever the `sessionId` argument itself changes (e.g. a session switch
  // via the dropdown, which navigates and re-renders this hook's caller with a new id) -- no
  // separate "switch" method is needed on top of this.
  useEffect(() => {
    reload()
  }, [reload])

  const markSuperseded = useCallback(() => {
    setState((s) => ({ ...s, view: 'superseded' }))
  }, [])

  const markClosed = useCallback(() => {
    setState((s) => ({ ...s, view: 'closed' }))
  }, [])

  return { ...state, reload, markSuperseded, markClosed }
}
