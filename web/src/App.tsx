import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { AtlasPayload, ConflictPayload, LightmapPayload, ScenePayload, ScenePoly, StatusPayload } from './api'
import { fetchLevelState, fetchStaged, fetchStatus, isClosedError, isSupersededError, postLoad, postRebuild, setClaimToken } from './api'
import { useHasUnseenSelection } from './layout/useSelectionSeen'
import { useSidebar } from './layout/useSidebar'
import { ConflictResolver } from './panels/ConflictResolver'
import type { SurfaceSelection } from './panels/Inspector'
import { SaveBar } from './panels/SaveBar'
import { Sidebar } from './panels/Sidebar'
import { buildSidebarPanels } from './panels/sidebarRegistry'
import { subscribeChangesAvailable } from './reload'
import type { Vec3 } from './scene/camera'
import { resolveBuildSolved } from './scene/buildStatus'
import type { FrameRequest } from './scene/frame'
import { unionBBox } from './scene/frame'
import { applyStagedOffsets } from './scene/dragStage'
import { QuadLayout } from './scene/QuadLayout'
import { clearSelection, parseSurfaceKey, surfaceKey, toggleSelection } from './scene/selectionSet'
import { SessionDropdown } from './session/SessionDropdown'
import { SessionLabel } from './session/SessionLabel'
import { SessionPicker } from './session/SessionPicker'
import { navigate, useRoute } from './session/route'
import { useSession } from './session/SessionContext'
import { useTheme } from './theme/useTheme'
import type { ThemePreference } from './theme/useTheme'

/** Load's own resolutionLabels/mapping (Task 10) -- 'mine' is a no-op (declining to resolve
 * already keeps the staged edit, `check_load_conflicts`'s own deliberate simplification); only a
 * 'theirs' pick produces a real resolution value, `"accept-load"`. Filters the resolver's generic
 * `Record<string, 'mine'|'theirs'>` down to just the theirs-picked names. */
function mapToAcceptLoadOnly(picks: Record<string, 'mine' | 'theirs'>): Record<string, 'accept-load'> {
  const out: Record<string, 'accept-load'> = {}
  for (const [name, pick] of Object.entries(picks)) {
    if (pick === 'theirs') out[name] = 'accept-load'
  }
  return out
}
const LOAD_RESOLUTION_LABELS = { mine: 'Keep my move', theirs: 'Accept trunk' }

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

/** The session-editing screen (the plan's former `App`, now mounted only for the `/session/<id>/`
 * route -- `App` below decides picker vs. editor). The incoming `sessionId` prop is renamed to
 * `routeSessionId` to feed `useSession` -- the body below keeps using the hook's OWN `sessionId`
 * (destructured from `session`), which is null until the resolve settles, matching this file's
 * pre-existing "gate every fetch/render on a resolved id" convention exactly (the same reason the
 * old auto-create bootstrap's `sessionId` started null too). Once resolved, the two are equal. */
function SessionEditor({ sessionId: routeSessionId }: { sessionId: string }) {
  const { preference: themePreference, setPreference: setThemePreference } = useTheme()
  // Session identity (plan Task 16, redesigned for path-based routing): `sessionId`/`level`/`view`
  // are destructured individually (not the whole `session` object) so effects/callbacks below can
  // depend on the exact stable pieces they use, rather than a fresh object every render.
  const session = useSession(routeSessionId)
  const { sessionId, level, view, claimToken, name, reload: reloadSession, markSuperseded, markClosed } = session
  // `SessionLabel`'s own local copy of the session's name (Task 12), seeded from `session.name` and
  // updated immediately by `SessionLabel`'s `onRenamed` -- `SessionContext` has no setter for `name`
  // alone, so a rename would otherwise only show up after the session's next full `reload()`.
  const [displayName, setDisplayName] = useState<string | null>(null)
  useEffect(() => setDisplayName(name), [name])

  // Task 17: pushes the session's current claim token into api.ts's module-level state, the one
  // place every mutating call reads it from (see api.ts's own doc comment on `setClaimToken` for
  // why it isn't threaded through every call site's params instead). Runs before anything else
  // that might fire a mutating call this render.
  useEffect(() => {
    setClaimToken(claimToken)
  }, [claimToken])
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
  // selects the whole brush instead.
  //
  // The two kinds COEXIST, and only a PLAIN (non-additive) pick of either clears the other -- UED22's
  // own mechanism, reproduced, not a convenience. Esc and a tap that hits nothing still clear both.
  // Which branch clears what, and why: GUI-PARITY.md "Actor + surface selection coexist; only a plain
  // click clears both".
  const [selectedNames, setSelectedNames] = useState<Set<string>>(() => new Set())
  const [selectedSurfaces, setSelectedSurfaces] = useState<Set<string>>(() => new Set())
  const onSelectActor = useCallback((name: string, additive: boolean) => {
    // deselectSole=true: re-tapping the one currently-selected actor clears it (bug report:
    // clicking an already-selected mesh actor did nothing) -- same fix as onSelectSurface below,
    // extended to actors. onSelectActor is the single shared path for every actor kind (mesh,
    // point, brush, mover), so this applies uniformly, not just to mesh actors. (A knowing
    // divergence from UED22, whose plain actor click is an unconditional select that never
    // deselects -- recorded in GUI-PARITY.md, kept because the owner asked for it.)
    setSelectedNames((s) => toggleSelection(s, name, additive, true))
    if (!additive) setSelectedSurfaces(clearSelection())
  }, [])
  const onSelectSurface = useCallback((actor: string, polyIndex: number, additive: boolean) => {
    // deselectSole=true: re-tapping the one currently-selected poly clears it (bug report: clicking
    // an already-selected poly did nothing).
    setSelectedSurfaces((s) => toggleSelection(s, surfaceKey(actor, polyIndex), additive, true))
    if (!additive) setSelectedNames(clearSelection())
  }, [])
  // OrgPanel's own batch-select shape (Task 23): a folder-node click replaces/adds a whole actor
  // set at once (mirrors a plain tap's replace / Ctrl+tap's additive semantics over a SET, not a
  // single name) -- a plain union/replace, not a second selection model.
  //
  // It never clears the surface selection, not even when replacing: UED22's actor BATCH verbs don't.
  // `edactBoxSelect` in replace mode clears `bSelected` in its own inline loop and never goes near a
  // surf, and `edactSelectAll`/`edactSelectOfClass`/`edactSelectInside`/`mapSelect*` contain no
  // `PF_Selected` reference at all. `SelectNone`-before-select is specific to the per-CLICK handlers.
  const onSelectMany = useCallback((names: ReadonlySet<string>, additive: boolean) => {
    setSelectedNames((s) => (additive ? new Set([...s, ...names]) : new Set(names)))
  }, [])
  // `Esc` (SelectionKeys, Task 15) and a tap that hits empty space (owner ruling 2026-09-15): the
  // paths that clear BOTH selection kinds entirely.
  const onDeselect = useCallback(() => {
    setSelectedNames(clearSelection())
    setSelectedSurfaces(clearSelection())
  }, [])
  // Frame-on-select (quad-layout Task 15/23): lifted here from QuadLayout so the org panel -- now
  // hosted by Sidebar, a sibling of QuadLayout rather than its child -- can still trigger the same
  // camera-framing QuadLayout's own `F` key uses (SelectionKeys' onFrame). One shared frameRequest,
  // threaded down into QuadLayout as a controlled prop.
  //
  // `frameActors`'s own definition is BELOW `stagedOffsets` (moved there, bug fix: it used to bbox
  // off raw `scene.actors`, so pressing F on a staged-moved actor flew the camera to its PRE-move
  // position, diverging from what's actually drawn -- same divergence class the Inspector/mesh-body
  // fixes above closed, found auditing for more of it, not separately reported).
  const frameSeq = useRef(0)
  const [frameRequest, setFrameRequest] = useState<FrameRequest | null>(null)
  // Staged actor moves (Task 10; the staging itself is Tasks 8/9's per-viewport Ctrl/Cmd-drag).
  // Deliberately approximate, per plan: "a simple hasStaged / stagedNames Set<string> piece of
  // state is enough -- do not duplicate the backend's full staged-actor bookkeeping client-side".
  // `onStaged` (wired to every pane's own `postStage` call, via QuadLayout) unions in newly staged
  // names; SaveBar's `onSaved`/`onDiscarded` clear it outright once IT confirms (from the server's
  // own `postSave`/`postDiscard` responses) the level's whole stage is empty -- see SaveBar.tsx's
  // own doc comment for why a flat clear is correct there, not just convenient.
  const [stagedNames, setStagedNames] = useState<Set<string>>(() => new Set())
  const onStaged = useCallback((names: string[]) => {
    setStagedNames((s) => new Set([...s, ...names]))
  }, [])
  // The shared "confirmed staged" visual position store every pane reads/writes (Critical 2, final
  // review fix wave) -- lifted here from Viewport3D.tsx/OrthoViewport.tsx's own private copies per
  // plan.md's File Structure table ("Staged-position override state" -> App.tsx). `stagedOffsetsRef`
  // mirrors `stagedOffsets` synchronously (React state is async) so a pane's onDrag/onPointerUp can
  // read the just-applied value without waiting on a re-render -- both are always updated together,
  // only through `setStagedOffsets`/`clearStagedOffsetNames` below, never independently.
  const [stagedOffsets, setStagedOffsetsState] = useState<Record<string, Vec3>>(() => ({}))
  const stagedOffsetsRef = useRef<Record<string, Vec3>>({})
  // Perf fix (live report: "moving actors is still jittery -- can we recompute/rewrite the position
  // less often?"): a Ctrl/Cmd-drag calls `setStagedOffsets` from `onDrag`, which fires on EVERY
  // native `pointermove` event -- a rate that can genuinely exceed the display's own refresh rate
  // (a high-poll-rate mouse, or a browser that doesn't coalesce pointermove to the compositor's own
  // frame timing). Committing straight to React state on every one of those forces a full synchronous
  // re-render cascade (every pane's own `effectiveActors` actor-array rebuild, the Inspector, the
  // sidebar panels, `SceneResourcesContext`'s mesh-position patch -- see that file's own "Perf fix"
  // comment for the geometry-rebuild half of this bug, already fixed) MORE OFTEN than a browser could
  // ever actually paint the result, which is pure wasted, jank-causing work.
  //
  // `stagedOffsetsRef.current` still updates SYNCHRONOUSLY on every call, exactly as before (nothing
  // that reads the ref -- `postStage`'s payload, a new gesture's `preGestureOffsetsRef` snapshot --
  // ever sees a stale value). Only the REACT STATE commit (`setStagedOffsetsState`, the expensive
  // part) is coalesced: at most one per animation frame, always flushing whatever is the FRESHEST
  // ref value at the moment the frame actually fires, never a value captured back when the frame was
  // scheduled. `rafPendingRef` is a plain bookkeeping ref (not React state), so reading/writing it
  // during a callback is the normal, safe use of a ref -- unrelated to (and not the same anti-pattern
  // as) reading a ref during a component's RENDER body.
  const rafPendingRef = useRef(false)
  const setStagedOffsets = useCallback((next: Record<string, Vec3>) => {
    stagedOffsetsRef.current = next
    if (rafPendingRef.current) return
    rafPendingRef.current = true
    requestAnimationFrame(() => {
      rafPendingRef.current = false
      setStagedOffsetsState(stagedOffsetsRef.current)
    })
  }, [])
  // `frameActors`/`handleOrgSelect` (declared just above `stagedOffsets`'s state, above) need it in
  // scope -- see that comment for why. Frames on the STAGED-offset-applied bbox, the same
  // `applyStagedOffsets` pure function `effectiveActorsForInspector` below uses.
  const frameActors = useCallback(
    (names: ReadonlySet<string>) => {
      if (!scene) return
      const bbox = unionBBox(applyStagedOffsets(scene.actors, stagedOffsets).filter((a) => names.has(a.name)))
      if (!bbox) return // nothing to frame -- unionBBox's own no-op signal (frame.ts)
      frameSeq.current += 1
      setFrameRequest({ bbox, seq: frameSeq.current })
    },
    [scene, stagedOffsets],
  )
  // OrgPanel's own batch-select shape: a folder-node click replaces/adds a whole actor set at once
  // AND frames the camera onto it -- mirrors QuadLayout's own former handleOrgSelect exactly.
  const handleOrgSelect = useCallback(
    (names: string[], additive: boolean) => {
      const nameSet = new Set(names)
      onSelectMany(nameSet, additive)
      frameActors(nameSet)
    },
    [onSelectMany, frameActors],
  )
  // Drops just the named actors' staged offsets, leaving every other staged actor's visual position
  // untouched -- used wherever the BACKEND clears a subset of the stage (a Save's "trunk" pick, a
  // Load's "accept-load" pick, the per-actor conflict-discard escape hatch) so the client never keeps
  // showing a staged position the trunk write already superseded.
  const clearStagedOffsetNames = useCallback((names: readonly string[]) => {
    if (names.length === 0) return
    const drop = new Set(names)
    const next: Record<string, Vec3> = {}
    for (const [name, loc] of Object.entries(stagedOffsetsRef.current)) {
      if (!drop.has(name)) next[name] = loc
    }
    setStagedOffsets(next)
  }, [setStagedOffsets])
  // Surfaces a failed `postStage` call (Important 3, final review fix wave) -- the same dismissable-
  // banner pattern `buildError` above already uses, not a new mechanism.
  const [stageError, setStageError] = useState<string | null>(null)
  const onStageError = useCallback((message: string) => setStageError(message), [])
  const onDiscarded = useCallback(() => {
    setStagedNames(new Set())
    setStagedOffsets({})
  }, [setStagedOffsets])
  // The per-actor conflict-discard escape hatch (SaveBar's own "discard just this one" button) --
  // NOT the whole-level Discard above: only that ONE actor's staged offset is dropped, since the
  // others may still be legitimately staged.
  const onActorDiscarded = useCallback((name: string) => clearStagedOffsetNames([name]), [clearStagedOffsetNames])
  // Load's own conflict set (Task 10, symmetric with Save's): populated from the extended
  // `postLoad` response's `conflicts` field. Load never blocks on a conflict (the refresh below
  // always completes) -- this just surfaces the SAME shared ConflictResolver so the user can
  // optionally accept the trunk's value for a conflicting actor, clearing its stage.
  const [loadConflicts, setLoadConflicts] = useState<ConflictPayload[]>([])
  const [reloading, setReloading] = useState(false)
  const [busy, setBusy] = useState<'load' | 'rebuild' | null>(null)
  // The unified sidebar's own collapse/active-tab state (spec's Architecture -> Components) --
  // owned HERE, not inside Sidebar.tsx, because the Selection tab's discoverability dot (below)
  // needs `activeTabId` too (spec's "Selection strip data"). Sidebar.tsx receives all three as
  // plain props, same as any other panel-agnostic piece of its own state.
  const { collapsed: sidebarCollapsed, activeTabId: sidebarActiveTabId, setActiveTab: setSidebarActiveTab } = useSidebar()
  // A stable string that changes iff the actor+surface selection ITSELF changes -- a fresh Set
  // every render must not itself register as a change (useSelectionSeen.ts's own doc comment).
  const selectionIdentity = useMemo(
    () => `${[...selectedNames].sort().join(',')}|${[...selectedSurfaces].sort().join(',')}`,
    [selectedNames, selectedSurfaces],
  )
  // The Selection rail icon's discoverability dot (spec's Decisions section) -- the ONLY thing that
  // computes `hasIndicator` for the `selection` registry entry; Sidebar.tsx never computes it.
  const hasUnseenSelection = useHasUnseenSelection(selectionIdentity, sidebarActiveTabId)

  // Fetches this session's full scene+atlas+lightmap state whenever the RESOLVED session changes
  // -- the initial resolve, or a later switch to a different session (SessionDropdown). Clears the
  // previous session's own scene/selection/staging state FIRST (same blast radius the old
  // `handleSwitchLevel` cleared explicitly): the render gate below blanks the page to "Loading…"
  // the instant `scene` goes null, and stays blanked until the new session's own fetch resolves --
  // the same "unload immediately, block until the new state has fully loaded" behavior the old
  // level switch had, just driven by this effect's own dependency change instead of a bespoke
  // pre-switch clearing step.
  useEffect(() => {
    if (!sessionId || !level) return
    setScene(null)
    setAtlas(null)
    setLightmap(null)
    setStatus(null)
    setSelectedNames(clearSelection())
    setSelectedSurfaces(clearSelection())
    setStagedNames(clearSelection())
    setStagedOffsets({})
    setStageError(null)
    setLoadConflicts([])
    fetchLevelState(sessionId)
      .then(({ scene: s, atlas: a, lightmap: l }) => {
        setScene(s)
        setAtlas(a)
        setLightmap(l)
      })
      .catch((e: unknown) => setError(String(e)))
  }, [sessionId, level, setStagedOffsets])

  // Staged edits survive a page refresh (a `POST /stage` writes through immediately -- only the
  // in-progress drag PREVIEW is refresh-lost, plan's own "Known limitations") -- so `stagedNames`
  // must be re-derived from `GET /staged` on every level (re)load, not start empty and silently
  // hide an already-staged edit until the next drag. `stagedOffsets` is seeded the same way
  // (Critical 2, final review fix wave): a refresh must recover the staged edit's VISUAL state too,
  // not just its count -- previously only `stagedNames` was recovered here, so a refreshed page
  // showed the Save bar but rendered every actor at its un-staged trunk position until the next drag.
  useEffect(() => {
    if (!sessionId) return
    fetchStaged(sessionId)
      .then((staged) => {
        setStagedNames(new Set(Object.keys(staged)))
        const offsets: Record<string, Vec3> = {}
        for (const [name, entry] of Object.entries(staged)) offsets[name] = entry.staged_location
        setStagedOffsets(offsets)
      })
      .catch(() => {
        // Same tolerance as refreshStatus below -- not worth a page-level error.
      })
  }, [sessionId, setStagedOffsets])

  const refreshStatus = useCallback((sid: string) => {
    fetchStatus(sid)
      .then(setStatus)
      .catch(() => {
        // A status poll failing is not worth surfacing as a page-level error -- the next poll tries again.
      })
  }, [])

  // Poll /status (cheap: no CSG solve) so the toolbar reflects build_status/changes_available even
  // with no WS push in between -- e.g. right after this tab's own Load/Rebuild, or a slow network.
  useEffect(() => {
    if (!sessionId) return
    refreshStatus(sessionId)
    const id = setInterval(() => refreshStatus(sessionId), STATUS_POLL_MS)
    return () => clearInterval(id)
  }, [sessionId, refreshStatus])

  // gui-explicit-rebuild spec §2: a settled trunk change is a BANNER signal only -- refresh
  // `/status` so the badge shows up immediately, never an automatic scene refetch.
  //
  // Task 17: the same socket also carries the session's "superseded" push -- the live counterpart
  // to a mutating call's 409 fallback below. Needs `claimToken` too (the backend's `/ws` requires
  // `?session=&claim=`), so this waits for both, and re-subscribes with a fresh token whenever one
  // is minted (a session switch, or the takeover's own Reload re-claiming this window).
  useEffect(() => {
    if (!sessionId || !claimToken) return
    const sub = subscribeChangesAvailable(sessionId, claimToken, () => refreshStatus(sessionId), markSuperseded, markClosed)
    return () => sub.unsubscribe()
  }, [sessionId, claimToken, refreshStatus, markSuperseded, markClosed])

  // Shared by Load and Rebuild: run the POST, then refetch scene+atlas+lightmap and /status --
  // both actions change what the server has to hand back (Load: the trunk view; Rebuild: the
  // solved geometry), so both need the same full refresh afterward. `onResult` (Task 10) lets a
  // caller inspect the POST's own response (Load's `conflicts` field) before that refresh fires --
  // it must run first, not after, since a slow refresh must not delay showing the conflict UI.
  const runBuildAction = useCallback(
    <T,>(which: 'load' | 'rebuild', post: (sid: string) => Promise<T>, onResult?: (result: T) => void) => {
      if (!sessionId || busy) return
      setBusy(which)
      setReloading(true)
      setBuildError(null)   // clear any previous failure banner -- this attempt gets a fresh verdict
      post(sessionId)
        .then((result) => {
          onResult?.(result)
          return fetchLevelState(sessionId)
        })
        .then(({ scene: s, atlas: a, lightmap: l }) => {
          setScene(s)
          setAtlas(a)
          setLightmap(l)
        })
        .then(() => refreshStatus(sessionId))
        .catch((e: unknown) => {
          // A 409 here means this session's claim was taken by another window, or the session was
          // deleted outright -- the same two takeovers the `/ws` "superseded"/"closed" pushes show,
          // kept as a fallback for whenever that push was lost. Not a build failure, so neither goes
          // in `buildError`. Same check order as SaveBar.tsx's own catch branches.
          if (isClosedError(e)) {
            markClosed()
            return
          }
          if (isSupersededError(e)) {
            markSuperseded()
            return
          }
          setBuildError(String(e))
        })
        .finally(() => {
          setBusy(null)
          setReloading(false)
        })
    },
    [sessionId, busy, refreshStatus, markSuperseded, markClosed],
  )
  const handleLoad = useCallback(
    () => runBuildAction('load', (sid) => postLoad(sid), (result) => setLoadConflicts(result.conflicts)),
    [runBuildAction],
  )
  const handleRebuild = useCallback(() => runBuildAction('rebuild', postRebuild), [runBuildAction])
  // Save success (Important 5, final review fix wave): route through the SAME refresh path Load/
  // Rebuild already use, so the Inspector and every non-dragged pane pick up the newly-committed
  // trunk state instead of showing the pre-Save Location until the user manually clicks Load.
  // Reusing an actual Load (not just `fetchLevelState`) matters: `serve`'s `_trunk_ref` is a
  // per-process cache that only Load/Rebuild ever invalidate, so a bare `fetchLevelState` after a
  // Save would still read the STALE cached trunk -- only `POST /load` forces the re-read. This also
  // re-clears the server's `changes_available` flag, which the Save's own trunk write would
  // otherwise leave set (Save doesn't touch it) and show as a spurious "reload available" banner.
  // KNOWN RESIDUAL (documented, not silently left out): `TrunkWatcher` debounces its own filesystem
  // watch by ~0.4s, so if that debounced callback fires AFTER this auto-Load already re-cleared the
  // flag, it can set `changes_available` back to true moments later, observing our own already-
  // loaded write as if it were external -- closing that fully needs a backend change (e.g. the
  // watcher suppressing its own write) that is out of scope for this fix wave.
  const onSaved = useCallback(() => {
    setStagedNames(new Set())
    setStagedOffsets({})
    runBuildAction('load', (sid) => postLoad(sid), (result) => setLoadConflicts(result.conflicts))
  }, [runBuildAction, setStagedOffsets])
  // Load conflict resolution (Task 10, fixed -- Important 4, final review fix wave): a 'theirs' pick
  // means "accept the trunk's value", POSTed as `check_load_conflicts`'s own `"accept-load"`. A
  // 'mine' pick ("Keep my move") is a no-op SERVER-side (declining to resolve already keeps the
  // staged edit) -- but it used to be a dead end CLIENT-side too: `mapToAcceptLoadOnly` dropped every
  // 'mine' pick, so an all-'mine' Confirm posted an EMPTY `resolutions`, `check_load_conflicts`
  // re-reported the identical unresolved conflict, and the banner reappeared unchanged with no way to
  // dismiss it short of picking "Accept trunk" (abandoning the very edit the user just said to keep).
  // Fixed: a 'mine' pick is dismissed LOCALLY, no network call needed for it either way -- when every
  // pick is 'mine', skip the POST entirely; when picks are mixed, still POST only the 'theirs' ones,
  // and additionally drop the 'mine'-picked names from the POST response's own `conflicts` (which
  // `check_load_conflicts` will otherwise keep re-reporting them in forever, since there is no
  // acknowledge-only signal to send it).
  const handleResolveLoadConflicts = useCallback(
    (picks: Record<string, 'mine' | 'theirs'>) => {
      const resolutions = mapToAcceptLoadOnly(picks)
      const mineNames = Object.entries(picks).filter(([, p]) => p === 'mine').map(([name]) => name)
      if (Object.keys(resolutions).length === 0) {
        setLoadConflicts((prev) => prev.filter((c) => !mineNames.includes(c.name)))
        return
      }
      runBuildAction(
        'load',
        (sid) => postLoad(sid, resolutions),
        (result) => {
          setLoadConflicts(result.conflicts.filter((c) => !mineNames.includes(c.name)))
          clearStagedOffsetNames(Object.keys(resolutions))
        },
      )
    },
    [runBuildAction, clearStagedOffsetNames],
  )

  // Session switch (SessionDropdown's own "switch to" action, plan Task 16 -- replaces the old
  // LevelPicker's PUT /api/level call entirely). `navigate` (route.ts) is the ONE navigation
  // mechanism a session switch uses now -- it changes the `/session/<id>/` path, which changes the
  // `sessionId` prop the outer `App` passes this component, which `useSession`'s own effect already
  // re-fires on (SessionContext.tsx). No local reload call is needed here any more.
  const handleSwitchSession = useCallback(
    (id: string) => {
      if (id === sessionId) return
      navigate(`/session/${id}/`)
    },
    [sessionId],
  )

  // Every selected actor's CURRENT (staged-offset-applied) state, in scene.actors order --
  // Inspector's own prop (Task 16: 0/1/2+ selected). Bug fix: this used to filter raw `scene.actors`
  // directly, so the Inspector kept showing an actor's pre-move Location even after a Ctrl/Cmd-drag
  // staged a new one -- the SAME `applyStagedOffsets` pure function the viewports already use for
  // their own rendering (Viewport3D.tsx/OrthoViewport.tsx `effectiveActors`), so this can never
  // show a different position than what's actually drawn: both derive from the identical
  // (scene.actors, stagedOffsets) inputs through the identical pure function.
  const effectiveActorsForInspector = useMemo(
    () => (scene ? applyStagedOffsets(scene.actors, stagedOffsets) : []),
    [scene, stagedOffsets],
  )
  const selectedActors = useMemo(
    () => effectiveActorsForInspector.filter((a) => selectedNames.has(a.name)),
    [effectiveActorsForInspector, selectedNames],
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

  // The unified sidebar's registry (Selection + Org/Search launch panels) -- rebuilt each render
  // from the current selection/actor props, same cost class as selectedActors/polyByKey above.
  // `hasUnseenSelection` (Step 10) is the ONLY thing that sets the `selection` entry's indicator --
  // buildSidebarPanels itself has no notion of "which tab was active when".
  const sidebarPanels = useMemo(
    () =>
      buildSidebarPanels({
        selectedActors,
        selectedSurfaces: selectedSurfaceInfos,
        hasUnseenSelection,
        orgActors: scene?.actors ?? [],
        selectedNames,
        onSelectOrgBatch: handleOrgSelect,
      }),
    [selectedActors, selectedSurfaceInfos, hasUnseenSelection, scene, selectedNames, handleOrgSelect],
  )

  // The real shading-mode gating signal (Task 19) -- derived from the /status polling this toolbar
  // already does, not a second fetch.
  const buildSolved = resolveBuildSolved(status)

  // A session id in the URL that the server doesn't know (never created, or a garbage id) -- no
  // auto-create, per the spec: a bare/valid URL auto-creates, but a BAD one is shown, not silently
  // papered over with a fresh session the user never asked for.
  if (view === 'notfound') {
    return (
      <div className="status-message error">
        Session not found: {sessionId}
        <button type="button" onClick={() => navigate('/')}>
          Back to sessions
        </button>
      </div>
    )
  }
  // This tab's own session was closed (by another tab/window, or directly) -- no auto-navigate,
  // per the spec: the user decides what to do next, this never silently creates a replacement.
  if (view === 'closed') {
    return (
      <div className="status-message">
        This session was closed.
        <button type="button" onClick={() => navigate('/')}>
          Back to sessions
        </button>
      </div>
    )
  }
  // Another window took this session's claim (or it was deleted) -- the `/ws` "superseded" push,
  // or a mutating call's 409 fallback, both routed through `markSuperseded`. Reload re-resolves the
  // session (`fetchSession` mints a fresh claim token, reclaiming it for THIS window) and returns
  // to 'editing' on success -- the same primitive a session switch already uses.
  if (view === 'superseded') {
    return (
      <div className="status-message superseded-takeover">
        This session is now open in another window. Reload to keep using it here.
        <button type="button" onClick={reloadSession}>
          Reload
        </button>
      </div>
    )
  }
  if (error) return <div className="status-message error">{error}</div>
  if (!sessionId || !level || !scene || !atlas || !lightmap) {
    return <div className="status-message">Loading…</div>
  }

  return (
    <div id="app-root">
      <div className="viewport-pane">
        <div className="toolbar-row">
          {/* Pinned to the toolbar's own opposite corner from the quad's Grid/Radii/Movers cluster
              (bug fix: it used to sit at the row's right end, crowding that cluster below it). */}
          <ThemeToggle preference={themePreference} onChange={setThemePreference} />
          <BuildToolbar status={status} busy={busy} onLoad={handleLoad} onRebuild={handleRebuild} />
          <SaveBar
            sessionId={sessionId}
            stagedNames={stagedNames}
            hasBuildPin={status !== null && status.build_status !== 'no_build'}
            onSaved={onSaved}
            onDiscarded={onDiscarded}
            onActorDiscarded={onActorDiscarded}
            onSuperseded={markSuperseded}
            onClosed={markClosed}
          />
          <SessionLabel sessionId={sessionId} level={level} name={displayName} onRenamed={setDisplayName} />
          <SessionDropdown currentSessionId={sessionId} onSwitchSession={handleSwitchSession} />
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
          {/* A failed Ctrl/Cmd-drag `postStage` (Important 3, final review fix wave) -- same
              dismissable-banner pattern as buildError above, not a new mechanism. */}
          {stageError && (
            <div className="build-error-banner">
              {stageError}
              <button type="button" onClick={() => setStageError(null)}>
                Dismiss
              </button>
            </div>
          )}
          {reloading && <div className="updating-badge">updating…</div>}
          {/* Load's own conflict UI (Task 10) -- the SAME shared ConflictResolver SaveBar mounts,
              with Load's own labels/mapping. Load never blocks on a conflict (the refresh above
              already completed by the time this can even be non-empty), so this is a follow-up
              prompt, not a gate -- but it's still non-dismissible: no close button, only resolving
              every row (or leaving the tab, same as any other unsaved-state exit). */}
          {loadConflicts.length > 0 && (
            <div className="load-conflict-banner">
              <ConflictResolver
                conflicts={loadConflicts}
                resolutionLabels={LOAD_RESOLUTION_LABELS}
                onResolve={handleResolveLoadConflicts}
              />
            </div>
          )}
          <QuadLayout
            level={sessionId}
            scene={scene}
            atlas={atlas}
            lightmap={lightmap}
            selectedNames={selectedNames}
            onSelectActor={onSelectActor}
            selectedSurfaces={selectedSurfaces}
            onSelectSurface={onSelectSurface}
            onDeselect={onDeselect}
            onStaged={onStaged}
            stagedOffsets={stagedOffsets}
            stagedOffsetsRef={stagedOffsetsRef}
            setStagedOffsets={setStagedOffsets}
            onStageError={onStageError}
            buildSolved={buildSolved}
            frameRequest={frameRequest}
            frameActors={frameActors}
          />
        </div>
      </div>
      {/* The unified sidebar (icon rail + one active panel) -- replaces the old org-panel/
          inspector-pane double sidebar (unified-sidebar spec). Sidebar itself is purely
          presentational; collapse/active-tab state and each panel's `hasIndicator` are all owned
          here (Step 10/12 above) and passed down as plain props. */}
      <Sidebar
        panels={sidebarPanels}
        collapsed={sidebarCollapsed}
        activeTabId={sidebarActiveTabId}
        setActiveTab={setSidebarActiveTab}
        selectedActors={selectedActors}
        selectedSurfaces={selectedSurfaceInfos}
      />
    </div>
  )
}

/** The routing root (session-management-UI spec, decision 1): a bare `/` renders the session
 * picker (create/pick/rename/delete, no auto-create), and `/session/<id>/` renders the real editor.
 * `useRoute()` (route.ts) does the parsing; this component owns no state of its own. */
function App() {
  const route = useRoute()
  if (route.screen === 'picker') return <SessionPicker />
  return <SessionEditor sessionId={route.id} />
}

export default App
