import { useEffect, useMemo, useState } from 'react'

import type { AtlasPayload, ScenePayload } from './api'
import { fetchAtlas, fetchScene } from './api'
import { Inspector } from './panels/Inspector'
import { subscribeReload } from './reload'
import { Viewport3D } from './scene/Viewport3D'

interface HealthResponse {
  status: string
  level: string
}

function App() {
  const [level, setLevel] = useState<string | null>(null)
  const [scene, setScene] = useState<ScenePayload | null>(null)
  const [atlas, setAtlas] = useState<AtlasPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [reloading, setReloading] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json() as Promise<HealthResponse>)
      .then((body) => setLevel(body.level))
      .catch((e: unknown) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!level) return
    Promise.all([fetchScene(level), fetchAtlas(level)])
      .then(([s, a]) => {
        setScene(s)
        setAtlas(a)
      })
      .catch((e: unknown) => setError(String(e)))
  }, [level])

  // Live-reload: a settled trunk change swaps in the new scene only once it's fully fetched --
  // the current scene stays visible (with an "updating" badge) meanwhile, never a blank flicker.
  useEffect(() => {
    if (!level) return
    const sub = subscribeReload(
      level,
      ({ scene: s, atlas: a }) => {
        setScene(s)
        setAtlas(a)
        setReloading(false)
      },
      () => setReloading(true),
    )
    return () => sub.unsubscribe()
  }, [level])

  const selectedActor = useMemo(
    () => scene?.actors.find((a) => a.name === selectedName) ?? null,
    [scene, selectedName],
  )

  if (error) return <div className="status-message error">{error}</div>
  if (!scene || !atlas) return <div className="status-message">Loading…</div>

  return (
    <div id="app-root">
      <div className="viewport-pane">
        {reloading && <div className="updating-badge">updating…</div>}
        <Viewport3D scene={scene} atlas={atlas} selectedName={selectedName} onSelectActor={setSelectedName} />
      </div>
      <div className="inspector-pane">
        <Inspector actor={selectedActor} />
      </div>
    </div>
  )
}

export default App
