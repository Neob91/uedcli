// Live-reload wiring (spec, "Loading & performance": "keeps the current scene visible ... and
// swaps when ready (no blank flicker)"): on a WS reload push, refetch the scene+atlas and hand
// them to the caller only once BOTH resolve. The caller's displayed state is therefore never
// blanked mid-reload -- it stays exactly what it was until the new payload is ready.
import { fetchAtlas, fetchScene, openReloadSocket } from './api'
import type { AtlasPayload, ScenePayload } from './api'

export interface LevelState {
  scene: ScenePayload
  atlas: AtlasPayload
}

export interface ReloadSubscription {
  /** Closes the underlying WebSocket. */
  unsubscribe: () => void
}

/** Subscribes to live-reload for `level`. `onReloadStart` fires the moment a settled trunk change
 * is pushed (before the refetch) -- e.g. to show an "updating" badge while the stale scene stays
 * on screen; `onReady` fires once the refetched scene+atlas have BOTH resolved, with the new
 * state to swap in. A refetch that fails leaves the stale scene visible (no fallback content, no
 * crash) rather than blanking it.
 *
 * Two reload pushes can overlap (a cold solve is ~24s per the plan, so a second trunk change can
 * easily settle before the first refetch finishes) -- `generation` tags each push and `onReady`
 * only fires for the LATEST one, so an older fetch resolving after a newer one can never regress
 * the displayed scene to stale data (review finding). */
export function subscribeReload(
  level: string,
  onReady: (state: LevelState) => void,
  onReloadStart?: () => void,
): ReloadSubscription {
  let generation = 0
  const ws = openReloadSocket(() => {
    const thisGeneration = ++generation
    onReloadStart?.()
    Promise.all([fetchScene(level), fetchAtlas(level)])
      .then(([scene, atlas]) => {
        if (thisGeneration !== generation) return // a newer reload has already superseded this one
        onReady({ scene, atlas })
      })
      .catch(() => {
        // Leave the stale scene visible; the next settled trunk change gets another try.
      })
  })
  return { unsubscribe: () => ws.close() }
}
