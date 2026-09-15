import { useCallback, useEffect, useMemo, useState } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload, StatusPayload } from './api'
import { fetchLevelState, fetchStatus, postLoad, postRebuild } from './api'
import { Inspector } from './panels/Inspector'
import { subscribeChangesAvailable } from './reload'
import { Viewport3D } from './scene/Viewport3D'

interface HealthResponse {
  status: string
  level: string
}

const STATUS_POLL_MS = 3000

function buildStatusLabel(status: StatusPayload | null): string {
  if (!status) return 'unknown'
  if (status.build_status === 'built') return 'built'
  if (status.build_status === 'evicted') return 'build evicted -- Rebuild to re-solve'
  return 'not built -- Rebuild to see level geometry'
}

/** The Load/Rebuild toolbar (gui-explicit-rebuild spec: Load and Rebuild are independent, explicit,
 * UnrealEd-style actions -- nothing here ever auto-builds). `busy` disables both buttons while
 * either request is in flight (they're not meaningfully composable: Rebuild itself performs an
 * implicit first Load if none has happened yet). */
function BuildToolbar({
  status,
  busy,
  onLoad,
  onRebuild,
}: {
  status: StatusPayload | null
  busy: 'load' | 'rebuild' | null
  onLoad: () => void
  onRebuild: () => void
}) {
  return (
    <div className="build-toolbar">
      <button type="button" onClick={onLoad} disabled={busy !== null}>
        {busy === 'load' ? 'Loading…' : 'Load'}
      </button>
      <button type="button" onClick={onRebuild} disabled={busy !== null}>
        {busy === 'rebuild' ? 'Rebuilding…' : 'Rebuild'}
      </button>
      <span className="build-status">{buildStatusLabel(status)}</span>
      {status?.changes_available && <span className="changes-badge">trunk changed -- Load to see it</span>}
    </div>
  )
}

function App() {
  const [level, setLevel] = useState<string | null>(null)
  const [scene, setScene] = useState<ScenePayload | null>(null)
  const [atlas, setAtlas] = useState<AtlasPayload | null>(null)
  const [lightmap, setLightmap] = useState<LightmapPayload | null>(null)
  const [status, setStatus] = useState<StatusPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  // A failed Load/Rebuild must NOT blank an already-working page (review finding): `error` above is
  // reserved for the two INITIAL fetches, where there's genuinely nothing else to show yet.
  // `buildError` is a dismissable banner alongside the still-good scene -- the old scene/atlas/
  // lightmap state is left exactly as it was before the failed action, same as a settled trunk
  // change never discards it (reload.ts's own "leave the stale scene visible" contract).
  const [buildError, setBuildError] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [reloading, setReloading] = useState(false)
  const [busy, setBusy] = useState<'load' | 'rebuild' | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json() as Promise<HealthResponse>)
      .then((body) => setLevel(body.level))
      .catch((e: unknown) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!level) return
    fetchLevelState(level)
      .then(({ scene: s, atlas: a, lightmap: l }) => {
        setScene(s)
        setAtlas(a)
        setLightmap(l)
      })
      .catch((e: unknown) => setError(String(e)))
  }, [level])

  const refreshStatus = useCallback((lvl: string) => {
    fetchStatus(lvl)
      .then(setStatus)
      .catch(() => {
        // A status poll failing is not worth surfacing as a page-level error -- the next poll tries again.
      })
  }, [])

  // Poll /status (cheap: no CSG solve) so the toolbar reflects build_status/changes_available even
  // with no WS push in between -- e.g. right after this tab's own Load/Rebuild, or a slow network.
  useEffect(() => {
    if (!level) return
    refreshStatus(level)
    const id = setInterval(() => refreshStatus(level), STATUS_POLL_MS)
    return () => clearInterval(id)
  }, [level, refreshStatus])

  // gui-explicit-rebuild spec §2: a settled trunk change is a BANNER signal only -- refresh
  // `/status` so the badge shows up immediately, never an automatic scene refetch.
  useEffect(() => {
    if (!level) return
    const sub = subscribeChangesAvailable(() => refreshStatus(level))
    return () => sub.unsubscribe()
  }, [level, refreshStatus])

  // Shared by Load and Rebuild: run the POST, then refetch scene+atlas+lightmap and /status --
  // both actions change what the server has to hand back (Load: the trunk view; Rebuild: the
  // solved geometry), so both need the same full refresh afterward.
  const runBuildAction = useCallback(
    (which: 'load' | 'rebuild', post: (lvl: string) => Promise<unknown>) => {
      if (!level || busy) return
      setBusy(which)
      setReloading(true)
      setBuildError(null)   // clear any previous failure banner -- this attempt gets a fresh verdict
      post(level)
        .then(() => fetchLevelState(level))
        .then(({ scene: s, atlas: a, lightmap: l }) => {
          setScene(s)
          setAtlas(a)
          setLightmap(l)
        })
        .then(() => refreshStatus(level))
        .catch((e: unknown) => setBuildError(String(e)))
        .finally(() => {
          setBusy(null)
          setReloading(false)
        })
    },
    [level, busy, refreshStatus],
  )
  const handleLoad = useCallback(() => runBuildAction('load', postLoad), [runBuildAction])
  const handleRebuild = useCallback(() => runBuildAction('rebuild', postRebuild), [runBuildAction])

  const selectedActor = useMemo(
    () => scene?.actors.find((a) => a.name === selectedName) ?? null,
    [scene, selectedName],
  )

  if (error) return <div className="status-message error">{error}</div>
  if (!scene || !atlas || !lightmap) return <div className="status-message">Loading…</div>

  return (
    <div id="app-root">
      <div className="viewport-pane">
        <BuildToolbar status={status} busy={busy} onLoad={handleLoad} onRebuild={handleRebuild} />
        {buildError && (
          <div className="build-error-banner">
            {buildError}
            <button type="button" onClick={() => setBuildError(null)}>
              Dismiss
            </button>
          </div>
        )}
        {reloading && <div className="updating-badge">updating…</div>}
        <Viewport3D scene={scene} atlas={atlas} lightmap={lightmap} selectedName={selectedName} onSelectActor={setSelectedName} />
      </div>
      <div className="inspector-pane">
        <Inspector actor={selectedActor} />
      </div>
    </div>
  )
}

export default App
