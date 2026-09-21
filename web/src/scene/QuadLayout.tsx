// The classic UnrealEd quad: Perspective + Top/Front/Side ortho, sharing ONE built scene via
// SceneResourcesProvider (quad-layout Part 1, Task 7) so geometry/textures are built once, not once
// per pane. Double-clicking a pane maximizes/restores it (CSS/state only, no new rendering logic).
//
// `selectedNames`/`onSelectActor` (Part 3, Task 13): a multi-actor selection set threaded to every
// pane identically, so Ctrl+tap/Ctrl+click in ANY pane composes onto the SAME lifted state (spec
// §9's cross-pane consistency requirement) -- one selection model, not four independent ones.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject, PointerEvent as ReactPointerEvent } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import type { Vec3 } from './camera'
import type { FrameRequest } from './frame'
import { DEFAULT_GRID_SIZE, GRID_SIZE_OPTIONS } from './grid'
import { ModeSelector } from './ModeSelector'
import { OrthoViewport } from './OrthoViewport'
import type { PaneId } from './paneLayout'
import { toggleMaximize } from './paneLayout'
import { SceneResourcesProvider } from './SceneResourcesContext'
import { SelectionKeys } from './SelectionKeys'
import { applyModeKey, canChangeMode, keyForMode, resolveEffectiveMode } from './shadingMode'
import type { ShadingMode } from './shadingMode'
import { Viewport3D } from './Viewport3D'

export interface QuadLayoutProps {
  // Threaded straight to Viewport3D's `postStage` call (Ctrl/Cmd-drag actor translation, Task 8) --
  // the level name the currently-shown scene/atlas/lightmap were fetched for (App.tsx's own `level`
  // state, non-null by the time this component ever renders).
  level: string
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // Surface (single-polygon texture) selection -- see Viewport3D.tsx's identical prop doc for the
  // full model. A distinct set from `selectedNames`, threaded to every pane the same way.
  selectedSurfaces: ReadonlySet<string>
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onDeselect: () => void
  // Threaded to every pane's own `onStaged` (Task 10) -- fires once a Ctrl/Cmd-drag gesture's
  // `postStage` call resolves, so App.tsx's `stagedNames` (SaveBar's gate) stays current. See
  // Viewport3D.tsx's identical prop doc.
  onStaged?: (names: string[]) => void
  // The shared "confirmed staged" visual position store, App.tsx-owned (Critical 2, final review
  // fix wave) -- forwarded verbatim to BOTH Viewport3D and every OrthoViewport, so every pane reads/
  // writes the SAME state (see Viewport3D.tsx's identical prop doc for the full picture).
  stagedOffsets: Record<string, Vec3>
  stagedOffsetsRef: MutableRefObject<Record<string, Vec3>>
  setStagedOffsets: (next: Record<string, Vec3>) => void
  // Surfaces a failed `postStage` call -- see Viewport3D.tsx's identical prop doc (Important 3).
  onStageError?: (message: string) => void
  // The real shading-mode gating signal (Task 19, buildStatus.ts's resolveBuildSolved).
  buildSolved: boolean
  // Lifted to App.tsx (unified-sidebar migration): the org panel that used to live inside this
  // component now renders from Sidebar.tsx, a sibling of QuadLayout in App.tsx -- so the `F`-key
  // framing mechanism SelectionKeys already used here (frameActors/frameRequest) is a controlled
  // prop instead of local state, the one shared instance App's org-panel entry drives too.
  frameRequest: FrameRequest | null
  frameActors: (names: ReadonlySet<string>) => void
}

// Real UnrealEd's classic default arrangement (dev/docs/unrealed/rendering.md: bottom-left is the
// 3D perspective pane, live-verified): top-left=Top, top-right=Front, bottom-left=Perspective,
// bottom-right=Side. DOM order drives the 2x2 CSS grid's implicit placement (index.css's
// `.quad-layout` has no explicit grid-area) -- this array's order IS the layout.
const PANES: PaneId[] = ['top', 'front', 'perspective', 'side']

// Classic UnrealEd's own default per pane (a judgment call -- neither spec pins this down):
// Perspective opens shaded/lit, the three ortho panes open wireframe (their long-standing role).
const DEFAULT_MODES: Record<PaneId, ShadingMode> = {
  perspective: 'lit',
  top: 'wireframe',
  front: 'wireframe',
  side: 'wireframe',
}

function isTypingTarget(t: EventTarget | null): boolean {
  return t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}

const MODE_KEYS = new Set(['1', '2', '3', '4'])

export function QuadLayout({
  level,
  scene,
  atlas,
  lightmap,
  selectedNames,
  onSelectActor,
  selectedSurfaces,
  onSelectSurface,
  onDeselect,
  onStaged,
  stagedOffsets,
  stagedOffsetsRef,
  setStagedOffsets,
  onStageError,
  buildSolved,
  frameRequest,
  frameActors,
}: QuadLayoutProps) {
  const [maximized, setMaximized] = useState<PaneId | null>(null)

  // Focused pane (Task 20): set on a pointerdown anywhere inside a pane, via bubbling -- no per-pane
  // component change needed, since neither Viewport3D nor OrthoViewport calls stopPropagation on
  // pointerdown. `1`-`4` targets whichever pane was focused most recently.
  const [focusedPane, setFocusedPane] = useState<PaneId>('perspective')
  const [modes, setModes] = useState<Record<PaneId, ShadingMode>>(DEFAULT_MODES)
  // Grid visibility toggle (Part 8, Task 28) -- one switch for all three ortho panes.
  const [showGrid, setShowGrid] = useState(true)
  // Base grid size (dev/docs/GUI.md "The world-anchored grid") -- UnrealEd's own persistent "Grid
  // Size" preference: the smallest grid unit the escalation algorithm (grid.ts) builds from as a
  // pane zooms. One value for all three ortho panes, same convention as showGrid/showRadii.
  const [baseGridSize, setBaseGridSize] = useState<number>(DEFAULT_GRID_SIZE)
  // Collision-cylinder / light-radius overlay toggle -- one switch for all four panes (mirrors
  // showGrid's convention). Default OFF: radii clutter a level fast, unlike the grid.
  const [showRadii, setShowRadii] = useState(false)
  // Mover solid-geometry toggle (GUI.md "Movers"): a Mover always renders wireframe-outline-only by
  // default, in every shading mode -- this ADDS its solid geometry on top when true. Default OFF,
  // mirroring showRadii's convention. Only the perspective pane reads it (ortho panes are always
  // wireframe, so it has no visible effect there -- expected, not wired to be disabled for it).
  const [showMoverSolid, setShowMoverSolid] = useState(false)

  // Resizable panes (bug report item 3): the column/row split as a fraction (0..1) of the quad's
  // own box, in plain component state per the ask -- no persistence needed. `MIN_FRAC`/`MAX_FRAC`
  // keep every pane at least a usable sliver, never fully collapsed by a runaway drag.
  const [colFrac, setColFrac] = useState(0.5)
  const [rowFrac, setRowFrac] = useState(0.5)
  const quadRef = useRef<HTMLDivElement | null>(null)
  const resizeDrag = useRef<{ axis: 'col' | 'row'; pointerId: number } | null>(null)

  const onSplitterPointerDown = useCallback((axis: 'col' | 'row') => (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    resizeDrag.current = { axis, pointerId: e.pointerId }
  }, [])
  const onSplitterPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = resizeDrag.current
    const rect = quadRef.current?.getBoundingClientRect()
    if (!drag || drag.pointerId !== e.pointerId || !rect) return
    const MIN_FRAC = 0.15
    const MAX_FRAC = 0.85
    if (drag.axis === 'col') {
      setColFrac(Math.min(MAX_FRAC, Math.max(MIN_FRAC, (e.clientX - rect.left) / rect.width)))
    } else {
      setRowFrac(Math.min(MAX_FRAC, Math.max(MIN_FRAC, (e.clientY - rect.top) / rect.height)))
    }
  }, [])
  const onSplitterPointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (resizeDrag.current?.pointerId === e.pointerId) resizeDrag.current = null
    e.currentTarget.releasePointerCapture(e.pointerId)
  }, [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target) || !MODE_KEYS.has(e.key)) return
      setModes((cur) => applyModeKey(cur, focusedPane, e.key as '1' | '2' | '3' | '4', buildSolved))
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [focusedPane, buildSolved])

  // The visible mode-selector's click handler (Task 20 follow-up): drives applyModeKey with the
  // clicked pane + mode's own key, the exact same gating/switch logic the `1`-`4` keys already use.
  const setPaneMode = useCallback(
    (pane: PaneId, mode: ShadingMode) => {
      setModes((cur) => applyModeKey(cur, pane, keyForMode(mode), buildSolved))
    },
    [buildSolved],
  )

  return (
    <div className="quad-layout-root">
      <SceneResourcesProvider scene={scene} atlas={atlas} lightmap={lightmap} stagedOffsets={stagedOffsets}>
        <SelectionKeys selectedNames={selectedNames} onFrame={frameActors} onDeselect={onDeselect} />
        <div
          className="quad-layout"
          data-maximized={maximized ?? undefined}
          ref={quadRef}
          style={maximized === null ? { gridTemplateColumns: `${colFrac}fr ${1 - colFrac}fr`, gridTemplateRows: `${rowFrac}fr ${1 - rowFrac}fr` } : undefined}
        >
        {/* Overlay toolbar (Movers/Radii/Grid), positioned relative to THIS element (`.quad-layout`,
            the quad grid itself), not `.quad-layout-root` (bug fix: `.quad-layout-root` also spans
            the org-panel sidebar, so a button anchored to it by a hardcoded `right` offset smaller
            than the sidebar's width landed INSIDE the sidebar instead of over the quad -- see
            dev/docs/GUI.md "Toolbar overlap"). One flex row, not per-button hand-computed `right`
            offsets -- adding/removing/resizing a button no longer needs every sibling's offset
            recomputed. */}
        <div className="quad-toolbar">
          {/* Movers solid-geometry toggle (GUI.md "Movers") -- stays enabled regardless of the
              focused pane's current shading mode: the click still flips the stored toggle state,
              which matters the instant that pane switches to a non-wireframe mode, even though it
              has no immediate visible effect while wireframe (or an ortho pane) is active. Never
              disabled/greyed on `modes`/`focusedPane`. */}
          <button
            type="button"
            className="mover-solid-toggle"
            onClick={() => setShowMoverSolid((v) => !v)}
            aria-pressed={showMoverSolid}
          >
            Movers: {showMoverSolid ? 'on' : 'off'}
          </button>
          <button
            type="button"
            className="radii-toggle"
            onClick={() => setShowRadii((v) => !v)}
            aria-pressed={showRadii}
          >
            Radii: {showRadii ? 'on' : 'off'}
          </button>
          {/* Grid control (owner ruling): a single checkbox+dropdown pair, not two separate buttons
              -- the dropdown stays visible but DISABLED (not hidden) while the checkbox is off, so
              toggling Grid never shifts the toolbar's layout and the last-chosen size stays visible. */}
          <div className="grid-control">
            <label className="grid-control-toggle">
              <input
                type="checkbox"
                checked={showGrid}
                onChange={(e) => setShowGrid(e.target.checked)}
              />
              Grid
            </label>
            <select
              className="grid-size-select"
              aria-label="Grid size"
              value={baseGridSize}
              disabled={!showGrid}
              onChange={(e) => setBaseGridSize(Number(e.target.value))}
            >
              {GRID_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>
        {PANES.map((pane) => (
          <div
            key={pane}
            className="quad-pane"
            data-pane={pane}
            data-testid={`quad-pane-${pane}`}
            hidden={maximized !== null && maximized !== pane}
            onPointerDown={() => setFocusedPane(pane)}
            onDoubleClick={() => setMaximized((cur) => toggleMaximize(cur, pane))}
          >
            <div className="quad-pane-label">
              {pane}
              {pane === focusedPane && <span className="quad-pane-focus-dot" aria-hidden="true" />}
            </div>
            {pane === 'perspective' ? (
              <Viewport3D
                level={level}
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
                frameRequest={frameRequest}
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
                showRadii={showRadii}
                showMoverSolid={showMoverSolid}
              />
            ) : (
              <OrthoViewport
                level={level}
                axis={pane}
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
                frameRequest={frameRequest}
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
                showGrid={showGrid}
                baseGridSize={baseGridSize}
                showRadii={showRadii}
              />
            )}
            {/* Owner ruling: ortho panes are ALWAYS wireframe, no mode choice -- only perspective
                gets the selector (canChangeMode). */}
            {canChangeMode(pane) && (
              <ModeSelector
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
                buildSolved={buildSolved}
                onSelect={(mode) => setPaneMode(pane, mode)}
              />
            )}
          </div>
        ))}
        {/* Drag-to-resize splitters (bug report item 3): plain component state, no persistence --
            hidden while a pane is maximized (nothing left to divide). */}
        {maximized === null && (
          <>
            <div
              className="quad-splitter quad-splitter-col"
              style={{ left: `${colFrac * 100}%` }}
              onPointerDown={onSplitterPointerDown('col')}
              onPointerMove={onSplitterPointerMove}
              onPointerUp={onSplitterPointerUp}
            />
            <div
              className="quad-splitter quad-splitter-row"
              style={{ top: `${rowFrac * 100}%` }}
              onPointerDown={onSplitterPointerDown('row')}
              onPointerMove={onSplitterPointerMove}
              onPointerUp={onSplitterPointerUp}
            />
          </>
        )}
      </div>
      </SceneResourcesProvider>
    </div>
  )
}
