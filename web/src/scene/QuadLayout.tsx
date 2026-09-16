// The classic UnrealEd quad: Perspective + Top/Front/Side ortho, sharing ONE built scene via
// SceneResourcesProvider (quad-layout Part 1, Task 7) so geometry/textures are built once, not once
// per pane. Double-clicking a pane maximizes/restores it (CSS/state only, no new rendering logic).
//
// `selectedNames`/`onSelectActor` (Part 3, Task 13): a multi-actor selection set threaded to every
// pane identically, so Ctrl+tap/Ctrl+click in ANY pane composes onto the SAME lifted state (spec
// §9's cross-pane consistency requirement) -- one selection model, not four independent ones.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import { OrgPanel } from '../panels/OrgPanel'
import type { FrameRequest } from './frame'
import { unionBBox } from './frame'
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
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // OrgPanel's own batch-select shape (Task 23): a folder-node click replaces/adds a whole actor
  // set at once -- distinct from the single-name onSelectActor above, which selectionSet.ts's
  // toggleSelection doesn't need to grow a bulk form to cover.
  onSelectMany: (names: ReadonlySet<string>, additive: boolean) => void
  onDeselect: () => void
  // The real shading-mode gating signal (Task 19, buildStatus.ts's resolveBuildSolved).
  buildSolved: boolean
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
  scene,
  atlas,
  lightmap,
  selectedNames,
  onSelectActor,
  onSelectMany,
  onDeselect,
  buildSolved,
}: QuadLayoutProps) {
  const [maximized, setMaximized] = useState<PaneId | null>(null)
  const [frameRequest, setFrameRequest] = useState<FrameRequest | null>(null)
  // A plain counter, not React state, so pressing `F` on the SAME selection twice still produces a
  // distinct `seq` each time (FrameRequest's own doc comment) without needing frameRequest itself
  // in this callback's dependency array (which would race a rapid double-press against the state
  // update it triggers).
  const frameSeq = useRef(0)

  // Reused, not re-specified, by Part 6's org panel (Task 23): folder-node selection frames its
  // actor set through this SAME callback, not a second framing mechanism.
  const frameActors = useCallback(
    (names: ReadonlySet<string>) => {
      const bbox = unionBBox(scene.actors.filter((a) => names.has(a.name)))
      if (!bbox) return // nothing to frame -- unionBBox's own no-op signal (frame.ts)
      frameSeq.current += 1
      setFrameRequest({ bbox, seq: frameSeq.current })
    },
    [scene.actors],
  )

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

  // OrgPanel's folder-node/find-result selection reuses BOTH mechanisms this plan already built --
  // selectedNames (via onSelectMany, not a second selection model) and frameActors (Task 15,
  // verbatim, not a second framing mechanism) -- spec §5's own requirement.
  const handleOrgSelect = useCallback(
    (names: string[], additive: boolean) => {
      const nameSet = new Set(names)
      onSelectMany(nameSet, additive)
      frameActors(nameSet)
    },
    [onSelectMany, frameActors],
  )

  return (
    <div className="quad-layout-root">
      <SceneResourcesProvider scene={scene} atlas={atlas} lightmap={lightmap}>
        <SelectionKeys selectedNames={selectedNames} onFrame={frameActors} onDeselect={onDeselect} />
        <button
          type="button"
          className="grid-toggle"
          onClick={() => setShowGrid((v) => !v)}
          aria-pressed={showGrid}
        >
          Grid: {showGrid ? 'on' : 'off'}
        </button>
        {/* Base grid-size dropdown (dev/docs/GUI.md "The world-anchored grid") -- UnrealEd's own
            "Grid Size" preference, the SMALLEST grid unit the escalation algorithm builds from as a
            pane zooms out. Positioned further left than .grid-toggle/.radii-toggle so the three
            don't overlap (index.css's own comment has the offset math). */}
        <select
          className="grid-size-select"
          aria-label="Grid size"
          value={baseGridSize}
          onChange={(e) => setBaseGridSize(Number(e.target.value))}
        >
          {GRID_SIZE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              Grid Size: {n}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="radii-toggle"
          onClick={() => setShowRadii((v) => !v)}
          aria-pressed={showRadii}
        >
          Radii: {showRadii ? 'on' : 'off'}
        </button>
        {/* Movers solid-geometry toggle (GUI.md "Movers") -- stays enabled regardless of the focused
            pane's current shading mode: the click still flips the stored toggle state, which matters
            the instant that pane switches to a non-wireframe mode, even though it has no immediate
            visible effect while wireframe (or an ortho pane) is active. Never disabled/greyed on
            `modes`/`focusedPane`. */}
        <button
          type="button"
          className="mover-solid-toggle"
          onClick={() => setShowMoverSolid((v) => !v)}
          aria-pressed={showMoverSolid}
        >
          Movers: {showMoverSolid ? 'on' : 'off'}
        </button>
        <div
          className="quad-layout"
          data-maximized={maximized ?? undefined}
          ref={quadRef}
          style={maximized === null ? { gridTemplateColumns: `${colFrac}fr ${1 - colFrac}fr`, gridTemplateRows: `${rowFrac}fr ${1 - rowFrac}fr` } : undefined}
        >
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
                scene={scene}
                atlas={atlas}
                lightmap={lightmap}
                selectedNames={selectedNames}
                onSelectActor={onSelectActor}
                onDeselect={onDeselect}
                frameRequest={frameRequest}
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
                showRadii={showRadii}
                showMoverSolid={showMoverSolid}
              />
            ) : (
              <OrthoViewport
                axis={pane}
                selectedNames={selectedNames}
                onSelectActor={onSelectActor}
                onDeselect={onDeselect}
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
      <OrgPanel actors={scene.actors} selectedNames={selectedNames} onSelectActor={handleOrgSelect} />
    </div>
  )
}
