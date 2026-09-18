import { useCallback, useEffect, useMemo, useState } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload, ScenePoly, StatusPayload } from './api'
import { fetchLevelState, fetchStatus, postLoad, postRebuild, switchLevel } from './api'
import { useCollapsiblePanel } from './layout/useCollapsiblePanel'
import { Inspector } from './panels/Inspector'
import type { SurfaceSelection } from './panels/Inspector'
import { LevelPicker } from './panels/LevelPicker'
import { subscribeChangesAvailable } from './reload'
import { resolveBuildSolved } from './scene/buildStatus'
import { QuadLayout } from './scene/QuadLayout'
import { clearSelection, parseSurfaceKey, surfaceKey, toggleSelection } from './scene/selectionSet'
import { useTheme } from './theme/useTheme'
import type { ThemePreference } from './theme/useTheme'

const THEME_CYCLE: ThemePreference[] = ['dark', 'light', 'system']

/** Cycles dark -> light -> system -> dark on each click (Task 30). */
function ThemeToggle({ preference, onChange }: { preference: ThemePreference; onChange: (pref: ThemePreference) => void }) {
  const next = THEME_CYCLE[(THEME_CYCLE.indexOf(preference) + 1) % THEME_CYCLE.length]
  return (
    <button type="button" className="theme-toggle" onClick={() => onChange(next)} title={`Switch to ${next}`}>
      Theme: {preference}
    </button>
  )
}

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
      {status?.changes_available && (
        <button type="button" onClick={onLoad} disabled={busy !== null}>
          {busy === 'load' ? 'Reloading…' : 'Reload'}
        </button>
      )}
      <button type="button" onClick={onRebuild} disabled={busy !== null}>
        {busy === 'rebuild' ? 'Rebuilding…' : 'Rebuild'}
      </button>
      <span className="build-status">{buildStatusLabel(status)}</span>
      {status?.changes_available && <span className="changes-badge">trunk changed -- Reload to see it</span>}
    </div>
  )
}

function App() {
  const { preference: themePreference, setPreference: setThemePreference } = useTheme()
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
  // Multi-actor selection (spec §9): a plain tap replaces it, Ctrl+tap toggles membership
  // (selectionSet.ts's toggleSelection) -- one lifted set, shared by every QuadLayout pane.
  //
  // Surface (single-polygon texture) selection is a SECOND, DISTINCT selection kind (GUI.md
  // "Selection & the Inspector"): a plain LMB-tap on a brush surface in a non-wireframe mode selects
  // just that one polygon's texture (highlight + inspect only); Shift+LMB on the same surface
  // selects the whole brush instead. The two kinds are mutually exclusive at any moment -- switching
  // which kind a click targets clears the OTHER kind's set, so "the current selection" (point 1 of
  // the spec: a miss always clears it) reads as one selection, not two independently-surviving ones.
  const [selectedNames, setSelectedNames] = useState<Set<string>>(() => new Set())
  const [selectedSurfaces, setSelectedSurfaces] = useState<Set<string>>(() => new Set())
  const onSelectActor = useCallback((name: string, additive: boolean) => {
    // deselectSole=true: re-tapping the one currently-selected actor clears it (bug report:
    // clicking an already-selected mesh actor did nothing) -- same fix as onSelectSurface below,
    // extended to actors. onSelectActor is the single shared path for every actor kind (mesh,
    // point, brush, mover), so this applies uniformly, not just to mesh actors.
    setSelectedNames((s) => toggleSelection(s, name, additive, true))
    setSelectedSurfaces(clearSelection())
  }, [])
  const onSelectSurface = useCallback((actor: string, polyIndex: number, additive: boolean) => {
    // deselectSole=true: re-tapping the one currently-selected poly clears it (bug report: clicking
    // an already-selected poly did nothing).
    setSelectedSurfaces((s) => toggleSelection(s, surfaceKey(actor, polyIndex), additive, true))
    setSelectedNames(clearSelection())
  }, [])
  // OrgPanel's own batch-select shape (Task 23): a folder-node click replaces/adds a whole actor
  // set at once (mirrors a plain tap's replace / Ctrl+tap's additive semantics over a SET, not a
  // single name) -- a plain union/replace, not a second selection model.
  const onSelectMany = useCallback((names: ReadonlySet<string>, additive: boolean) => {
    setSelectedNames((s) => (additive ? new Set([...s, ...names]) : new Set(names)))
    setSelectedSurfaces(clearSelection())
  }, [])
  // `Esc` (SelectionKeys, Task 15) and a tap that hits empty space (owner ruling 2026-09-15): the
  // paths that clear BOTH selection kinds entirely.
  const onDeselect = useCallback(() => {
    setSelectedNames(clearSelection())
    setSelectedSurfaces(clearSelection())
  }, [])
  const [reloading, setReloading] = useState(false)
  const [busy, setBusy] = useState<'load' | 'rebuild' | null>(null)
  // Level switching (owner ruling): unload the OLD level's state the instant a switch starts, and
  // block the whole app until the new level's full state has loaded -- a broader blast radius than
  // Load/Rebuild's `reloading` badge, since the picker/org-panel/selection are all invalid mid-switch,
  // not just the built geometry. `!scene` in the render gate below (already used for the initial
  // load) does the actual blocking -- unmounting the whole app is the most thorough "block all UI".
  const [levelSwitching, setLevelSwitching] = useState(false)
  const [levelSwitchError, setLevelSwitchError] = useState<string | null>(null)
  // Collapsible inspector sidebar (mobile/laptop layout spec, owner-approved 2026-09-18) -- see
  // QuadLayout.tsx's identical org-panel wiring and useCollapsiblePanel's own doc comment. A
  // separate storage key: the two sidebars toggle independently, per the owner's spec.
  const { collapsed: inspectorCollapsed, toggle: toggleInspector } = useCollapsiblePanel('uedcli-inspector-pane-collapsed')

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
      // Covers both the initial load and a level switch's own setLevel() below -- a level switch
      // stays blocked (levelSwitching stays true) until exactly this fetch settles; a no-op for the
      // initial load, where levelSwitching is already false.
      .finally(() => setLevelSwitching(false))
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

  // Level switch (LevelPicker's own PUT /api/level call site -- moved here since a switch
  // invalidates far more of App's own state than LevelPicker owns).
  const handleSwitchLevel = useCallback(
    (name: string) => {
      if (!level || name === level || levelSwitching) return
      setLevelSwitching(true)
      setLevelSwitchError(null)
      setBuildError(null)
      // Unload the old level's state FIRST, before the switch request even resolves -- never let
      // stale scene/atlas/lightmap/selection linger while the new level loads.
      setScene(null)
      setAtlas(null)
      setLightmap(null)
      setStatus(null)
      setSelectedNames(clearSelection())
      setSelectedSurfaces(clearSelection())
      switchLevel(name)
        .then(() => setLevel(name)) // drives the fetch-on-level-change effect above
        .catch((e: unknown) => {
          // The switch itself failed server-side -- `level` never changed, so restore its state
          // instead of leaving the app blocked on nothing.
          setLevelSwitchError(String(e))
          setLevelSwitching(false)
          return fetchLevelState(level)
            .then(({ scene: s, atlas: a, lightmap: l }) => {
              setScene(s)
              setAtlas(a)
              setLightmap(l)
            })
            .then(() => refreshStatus(level))
        })
        .catch((e: unknown) => setError(String(e))) // the restore itself failed -- nothing left to show
    },
    [level, levelSwitching, refreshStatus],
  )

  // Every selected actor, in scene.actors order -- Inspector's own prop (Task 16: 0/1/2+ selected).
  const selectedActors = useMemo(
    () => scene?.actors.filter((a) => selectedNames.has(a.name)) ?? [],
    [scene, selectedNames],
  )

  // `surfaceKey(owner, i_brush_poly) -> one representative ScenePoly` -- CSG can split one authored
  // polygon into several solved fragments sharing the SAME `i_brush_poly` (that's the whole point of
  // this identity: a click anywhere on the authored face selects/highlights all of them), and any one
  // fragment's texture/UV/blend data is representative of the whole authored poly (they all derive
  // from the same source `Polygon`) -- so `set` (keep the LAST, i.e. any) rather than a multi-map.
  const polyByKey = useMemo(() => {
    const m = new Map<string, ScenePoly>()
    if (!scene) return m
    for (const poly of scene.polys) {
      if (poly.owner != null && poly.i_brush_poly != null) m.set(surfaceKey(poly.owner, poly.i_brush_poly), poly)
    }
    return m
  }, [scene])

  // Every selected SURFACE, resolved to its actor name + poly index + a representative poly's own
  // data -- Inspector's second selection-kind prop (GUI.md "Selection & the Inspector"). A key that
  // no longer resolves (a stale selection surviving a Rebuild/reload whose authored geometry actually
  // changed) is silently dropped rather than shown broken -- the same "a rename/delete invalidates a
  // stale selectedNames entry" tolerance `selectedActors` above already has via its `.filter`.
  const selectedSurfaceInfos = useMemo(() => {
    const infos: SurfaceSelection[] = []
    for (const key of selectedSurfaces) {
      const parsed = parseSurfaceKey(key)
      const poly = parsed ? polyByKey.get(key) : undefined
      if (parsed && poly) infos.push({ actorName: parsed.actor, polyIndex: parsed.polyIndex, poly })
    }
    return infos
  }, [polyByKey, selectedSurfaces])

  // The real shading-mode gating signal (Task 19) -- derived from the /status polling this toolbar
  // already does, not a second fetch.
  const buildSolved = resolveBuildSolved(status)

  if (error) return <div className="status-message error">{error}</div>
  if (!level || !scene || !atlas || !lightmap) {
    return <div className="status-message">{levelSwitching ? 'Switching level…' : 'Loading…'}</div>
  }

  return (
    <div id="app-root">
      <div className="viewport-pane">
        <div className="toolbar-row">
          {/* Pinned to the toolbar's own opposite corner from the quad's Grid/Radii/Movers cluster
              (bug fix: it used to sit at the row's right end, crowding that cluster below it). */}
          <ThemeToggle preference={themePreference} onChange={setThemePreference} />
          <BuildToolbar status={status} busy={busy} onLoad={handleLoad} onRebuild={handleRebuild} />
          <LevelPicker
            currentLevel={level}
            disabled={levelSwitching}
            error={levelSwitchError}
            onSwitchLevel={handleSwitchLevel}
          />
        </div>
        {/* Fills exactly the space left below the toolbar row (a flex column: toolbar + this),
            instead of the quad being sized against the full viewport height and drawing underneath
            the toolbar. Banners below are positioned relative to THIS box, so they sit just below
            the toolbar regardless of the toolbar's own rendered height. */}
        <div className="viewport-content">
          {buildError && (
            <div className="build-error-banner">
              {buildError}
              <button type="button" onClick={() => setBuildError(null)}>
                Dismiss
              </button>
            </div>
          )}
          {reloading && <div className="updating-badge">updating…</div>}
          <QuadLayout
            scene={scene}
            atlas={atlas}
            lightmap={lightmap}
            selectedNames={selectedNames}
            onSelectActor={onSelectActor}
            selectedSurfaces={selectedSurfaces}
            onSelectSurface={onSelectSurface}
            onSelectMany={onSelectMany}
            onDeselect={onDeselect}
            buildSolved={buildSolved}
          />
        </div>
      </div>
      {/* Collapsible sidebar (mobile/laptop layout spec) -- see QuadLayout.tsx's identical org-panel
          wrapper for the shared shape/rationale. */}
      <div className="inspector-pane-wrapper">
        <button
          type="button"
          className="sidebar-toggle"
          onClick={toggleInspector}
          aria-pressed={inspectorCollapsed}
          aria-label={inspectorCollapsed ? 'Show inspector panel' : 'Hide inspector panel'}
          title={inspectorCollapsed ? 'Show inspector panel' : 'Hide inspector panel'}
        >
          {inspectorCollapsed ? '◀' : '▶'}
        </button>
        {!inspectorCollapsed && (
          <div className="inspector-pane">
            <Inspector selected={selectedActors} selectedSurfaces={selectedSurfaceInfos} />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
