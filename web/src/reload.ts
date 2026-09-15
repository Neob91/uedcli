// Live-reload wiring (gui-explicit-rebuild spec §2): a settled trunk change on disk pushes a
// "changes available" WS message -- a banner/badge signal ONLY. It never triggers an automatic
// refetch (that would silently rebuild the level's displayed state out from under the user); the
// actual refresh only happens when the user explicitly clicks Load or Rebuild (App.tsx), via
// `fetchLevelState`.
import { openChangesAvailableSocket } from './api'

export interface ReloadSubscription {
  /** Closes the underlying WebSocket. */
  unsubscribe: () => void
}

/** Subscribes to the "changes available" signal. `onChangesAvailable` fires once per settled trunk
 * change pushed while this socket is open -- the caller's job (e.g. showing a banner, or refreshing
 * `/status`), never an automatic scene refetch. */
export function subscribeChangesAvailable(onChangesAvailable: () => void): ReloadSubscription {
  const ws = openChangesAvailableSocket(() => onChangesAvailable())
  return { unsubscribe: () => ws.close() }
}
