// The classic UnrealEd quad: Perspective + Top/Front/Side ortho, sharing ONE built scene via
// SceneResourcesProvider (quad-layout Part 1, Task 7) so geometry/textures are built once, not once
// per pane. Double-clicking a pane maximizes/restores it (CSS/state only, no new rendering logic).
//
// `selectedNames`/`onSelectActor` (Part 3, Task 13): a multi-actor selection set threaded to every
// pane identically, so Ctrl+tap/Ctrl+click in ANY pane composes onto the SAME lifted state (spec
// §9's cross-pane consistency requirement) -- one selection model, not four independent ones.
import { useCallback, useEffect, useRef, useState } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import { OrgPanel } from '../panels/OrgPanel'
import type { FrameRequest } from './frame'
import { unionBBox } from './frame'
import { OrthoViewport } from './OrthoViewport'
import type { PaneId } from './paneLayout'
import { toggleMaximize } from './paneLayout'
import { SceneResourcesProvider } from './SceneResourcesContext'
import { SelectionKeys } from './SelectionKeys'
import { applyModeKey, resolveEffectiveMode } from './shadingMode'
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

const PANES: PaneId[] = ['perspective', 'top', 'front', 'side']

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

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target) || !MODE_KEYS.has(e.key)) return
      setModes((cur) => applyModeKey(cur, focusedPane, e.key as '1' | '2' | '3' | '4', buildSolved))
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [focusedPane, buildSolved])

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
        <div className="quad-layout" data-maximized={maximized ?? undefined}>
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
                frameRequest={frameRequest}
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
              />
            ) : (
              <OrthoViewport
                axis={pane}
                selectedNames={selectedNames}
                onSelectActor={onSelectActor}
                frameRequest={frameRequest}
                mode={resolveEffectiveMode(modes[pane], buildSolved)}
                showGrid={showGrid}
              />
            )}
          </div>
        ))}
      </div>
      </SceneResourcesProvider>
      <OrgPanel actors={scene.actors} selectedNames={selectedNames} onSelectActor={handleOrgSelect} />
    </div>
  )
}
