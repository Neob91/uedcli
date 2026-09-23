// Live-reload wiring (gui-explicit-rebuild spec §2): a settled trunk change on disk pushes a
// "changes available" WS message -- a banner/badge signal ONLY. It never triggers an automatic
// refetch (that would silently rebuild the level's displayed state out from under the user); the
// actual refresh only happens when the user explicitly clicks Load or Rebuild (App.tsx), via
// `fetchLevelState`.
//
// Task 17: the same socket also carries the session's "superseded" signal (another window took
// this session's claim, or it was deleted) -- the live counterpart to a mutating call's 409
// fallback (`isSupersededError` in api.ts). Only an explicit `{"type":"superseded"}` push counts
// as that signal; an ordinary close (a dropped connection, a proxy hiccup, a server restart) is
// NOT proof the session is gone, so it reconnects instead of showing the takeover.
import { openChangesAvailableSocket } from './api'

export interface ReloadSubscription {
  /** Closes the underlying WebSocket and stops any pending reconnect attempt. */
  unsubscribe: () => void
}

// A fixed delay, not a backoff ladder -- this isn't a task about a sophisticated reconnection
// strategy, just not leaving a dropped connection dead until the next full page load.
const RECONNECT_DELAY_MS = 2000

/** Subscribes to one session's live signals: "changes available" (`onChangesAvailable`, fired once
 * per settled trunk change while this socket is open -- the caller's job, e.g. showing a banner or
 * refreshing `/status`, never an automatic scene refetch) and "superseded" (`onSuperseded`, fired
 * exactly once, the moment the server says this connection's claim no longer holds -- never
 * recovered from here; the caller shows the takeover). */
export function subscribeChangesAvailable(
  sessionId: string,
  claimToken: string,
  onChangesAvailable: () => void,
  onSuperseded: () => void,
): ReloadSubscription {
  // Set once a "superseded" push arrives (or once the caller unsubscribes): stops the reconnect
  // loop, since there is no longer a live session worth reconnecting to.
  let stopped = false
  let ws: WebSocket
  let pendingReconnect: ReturnType<typeof setTimeout> | undefined

  function connect(): void {
    ws = openChangesAvailableSocket(sessionId, claimToken, onChangesAvailable, () => {
      stopped = true
      onSuperseded()
    })
    ws.addEventListener('close', (event: CloseEvent) => {
      if (stopped) return
      // Fix round 1, Important finding: code 4001 (`ws_endpoint`'s pre-accept rejection) means the
      // session id was unknown/deleted, or the request was malformed (no claim token at all) --
      // never a transient condition. Retrying with the exact same `sessionId`/`claimToken` can only
      // ever produce the same 4001 again, so give up instead of looping forever. This is distinct
      // from 4003/4004 (claim superseded / session deleted mid-poll): those are always preceded by
      // an explicit `{"type":"superseded"}` message, already handled by the `onSuperseded` callback
      // above, which sets `stopped` before this listener ever runs.
      if (event.code === 4001) {
        stopped = true
        return
      }
      // Re-checked when this actually fires, not just when it was scheduled -- `unsubscribe()` (or
      // a "superseded" push) landing in between must still cancel the reconnect, not just the one
      // that was scheduled *after* it.
      pendingReconnect = setTimeout(() => {
        if (!stopped) connect()
      }, RECONNECT_DELAY_MS)
    })
  }
  connect()

  return {
    unsubscribe: () => {
      stopped = true
      clearTimeout(pendingReconnect)
      ws.close()
    },
  }
}
