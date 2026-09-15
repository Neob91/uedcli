// One orthographic pane (Top/Front/Side, quad-layout Part 1, Task 6): the SAME shared built scene
// (geometry/materials/markers, SceneResourcesContext) viewed through a different, axis-locked
// camera, with the same mouse-only pointer-lock/capture/tap plumbing Perspective uses
// (useDragGesture, Task 4) -- a drag pans, both-button-drag or scroll zooms (main spec's "Camera"
// section), a tap selects. Desktop/mouse-only in this slice; ortho touch parity is deferred
// (dragGesture.ts's own note).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject, PointerEvent as ReactPointerEvent } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { Vec3 } from './camera'
import { BrushOutlines } from './BrushOutlines'
import { useDragGesture } from './dragGesture'
import type { DragGestureCallbacks } from './dragGesture'
import type { FrameRequest } from './frame'
import { GridOverlay } from './GridOverlay'
import { MARKER_COLOR } from './markers'
import { PointActorMarker } from './PointActorMarker'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { orthoBasis, orthoDragZoom, orthoFrameFit, orthoLineHitThresholdUU, orthoPan, orthoZoom, screenToWorld } from './orthoCamera'
import { RadiiOverlays } from './RadiiOverlays'
import { useSceneResourcesContext } from './SceneResourcesContext'
import { SelectionHighlight } from './SelectionHighlight'
import { SelectionMarkers } from './SelectionMarkers'
import { selectedNonBrushBoxes } from './selectionBoxes'
import { resolveTapSelect } from './tapSelect'
import type { ShadingMode } from './shadingMode'
import { usesUnlitMaterials } from './shadingMode'
// `THREE.ColorManagement.enabled` is a process-wide singleton r3f reasserts on every render of
// EVERY mounted Canvas (Viewport3D.tsx's own `CANVAS_COLOR_MANAGEMENT` doc comment) -- this pane's
// Canvas MUST spread the identical constant, or the two fight over that global flag on every
// shared re-render (constant in the quad layout), silently breaking Viewport3D's fix too.
import { CANVAS_COLOR_MANAGEMENT } from './Viewport3D'

// Far enough to enclose a whole UE1 level (+/-32768 UU) from any starting center -- matches
// Viewport3D's far=131072 reasoning.
const ORTHO_HALF_RANGE = 65536
const INITIAL_WORLD_UNITS_PER_PIXEL = 4

// Same fallback dot tint as Viewport3D's identical marker rendering.
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)
// Point actors must always render on top of brush wireframe/highlight (owner ruling, ortho panes
// only) -- depthTest off so real world depth along the view axis can't hide a marker "behind" a
// brush, and higher than every other renderOrder in this pane (grid's -10, brush outlines' default
// 0) so draw order is explicit rather than incidental scene-graph position.
const MARKER_RENDER_ORDER = 10

export function initialOrthoPose(): OrthoPose {
  return { center: [0, 0, 0], worldUnitsPerPixel: INITIAL_WORLD_UNITS_PER_PIXEL }
}

/** Applies `pose`/`axis` to the R3F default (orthographic) camera every frame: axis-locked
 * position/orientation (looking along `orthoBasis(axis).forward` through `pose.center`), and a
 * frustum sized from `worldUnitsPerPixel` × the container's own pixel size so the pane's on-screen
 * scale matches `pose` exactly regardless of the pane's CSS size. Publishes the live camera object
 * to `cameraRef` for the outer pointer handlers' raycast.
 *
 * Orientation is built via `camera.up` + `lookAt` (a PROPER rotation, always valid), THEN mirrors
 * the projection's NDC-x term -- the same fix `Viewport3D.tsx`'s `applyCameraPose` applies to the
 * perspective camera, for the identical reason. This file used to build the rotation directly from
 * `orthoBasis`'s (right, up, forward) via `Matrix4.makeBasis` (local +X/+Y/+Z pinned to
 * `right`/`up`/`-forward`); that matrix is IMPROPER (determinant -1) for all three axes, a direct
 * consequence of this world being left-handed (`Viewport3D.tsx`'s own doc comment), and
 * `quaternion.setFromRotationMatrix` silently mis-decomposes an improper matrix -- confirmed live
 * (and by a standalone port of three.js's own algorithm) to produce a camera looking along a
 * COMPLETELY WRONG axis for `front`/`side` (only `top` happened to end up pointing the right way,
 * merely upside-down), which is why front/side rendered entirely blank while top looked fine. Real
 * root cause of the Front/Side blank-pane regression -- `Viewport3D.tsx`'s comment already predicted
 * exactly this failure mode for this exact pattern, but the fix wasn't ported here at the same time.
 *
 * `lookAt` derives local +X (screen-right) as `cross(up, eye-target)`, which for every one of this
 * module's three axis bases works out to the NEGATION of `orthoBasis`'s own `right` (this file's
 * previous doc comment already noted this, citing bug report item 5 -- dragging right visibly
 * panned the wrong way when this was tried before the mirror-projection technique existed). Negating
 * `projectionMatrix`'s NDC-x term restores the intended screen-right without touching the
 * already-correct look direction/up, so pan direction stays correct too. `projectionMatrixInverse`
 * is kept in sync for the same reason `Viewport3D.tsx` keeps it in sync: `performTapSelect`'s
 * `THREE.Raycaster.setFromCamera` unprojects screen points through it.
 *
 * Pure THREE.js math -- no WebGL context needed, so it's unit-tested directly
 * (`OrthoViewport.test.ts`) without mounting a `<Canvas>`, mirroring `Viewport3D.tsx`'s
 * `applyCameraPose`. */
export function applyOrthoCameraPose(
  cam: THREE.OrthographicCamera,
  pose: OrthoPose,
  axis: OrthoAxis,
  viewportPx: { width: number; height: number },
): void {
  const { forward, up } = orthoBasis(axis)
  const x = pose.center[0] - forward[0] * ORTHO_HALF_RANGE
  const y = pose.center[1] - forward[1] * ORTHO_HALF_RANGE
  const z = pose.center[2] - forward[2] * ORTHO_HALF_RANGE
  cam.position.set(x, y, z)
  cam.up.set(up[0], up[1], up[2])
  cam.lookAt(x + forward[0], y + forward[1], z + forward[2])
  cam.updateMatrixWorld(true) // r3f does this before rendering; explicit here so this function is
  // self-contained for direct (non-r3f) callers, e.g. OrthoViewport.test.ts's Vector3.project(cam),
  // which reads matrixWorldInverse without updating it itself (Viewport3D.tsx's applyCameraPose has
  // the identical call for the identical reason).
  const halfW = (viewportPx.width / 2) * pose.worldUnitsPerPixel
  const halfH = (viewportPx.height / 2) * pose.worldUnitsPerPixel
  cam.left = -halfW
  cam.right = halfW
  cam.top = halfH
  cam.bottom = -halfH
  cam.near = 0.1
  cam.far = ORTHO_HALF_RANGE * 2
  cam.updateProjectionMatrix()
  cam.projectionMatrix.elements[0] *= -1
  cam.projectionMatrixInverse.elements[0] *= -1
}

function OrthoCameraRig({
  pose,
  axis,
  cameraRef,
}: {
  pose: OrthoPose
  axis: OrthoAxis
  cameraRef: MutableRefObject<THREE.OrthographicCamera | null>
}) {
  const { camera, size } = useThree()
  useFrame(() => {
    const cam = camera as THREE.OrthographicCamera
    cameraRef.current = cam
    applyOrthoCameraPose(cam, pose, axis, size)
  })
  return null
}

export interface OrthoViewportProps {
  axis: OrthoAxis
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // A tap that hits nothing selectable deselects everything (owner ruling 2026-09-15) -- see
  // Viewport3D.tsx's identical prop doc.
  onDeselect: () => void
  // `F`-frame (Part 3, Task 15): a new (higher `seq`) request recenters `pose.center` on the bbox
  // and fits its extent on THIS axis's screen plane.
  frameRequest?: FrameRequest | null
  // Per-pane shading mode (Part 4, Task 20): 'wireframe' draws ONLY the CSG-colored brush rings (no
  // solid mesh) -- ortho's own long-standing default, see below; the other three draw the mesh too.
  mode?: ShadingMode
  // Grid visibility (Part 8, Task 28) -- a single toggle for all three ortho panes, owned by
  // QuadLayout, not a per-pane preference (classic level editors have one "show grid" switch).
  showGrid?: boolean
  // Collision-cylinder / light-radius overlay toggle -- one switch for every pane (QuadLayout),
  // mirroring showGrid's convention; default off (radii clutter a level fast).
  showRadii?: boolean
}

const SELECTION_BOX_COLOR = 0x00e5ff

export function OrthoViewport({
  axis,
  selectedNames,
  onSelectActor,
  onDeselect,
  frameRequest = null,
  mode = 'wireframe',
  showGrid = true,
  showRadii = false,
}: OrthoViewportProps) {
  const [pose, setPose] = useState<OrthoPose>(initialOrthoPose)
  // The cursor's projected world-space (UU) position, for the coordinate readout (Task 28) -- null
  // when the pointer hasn't moved inside this pane yet (or has left it).
  const [hoverWorld, setHoverWorld] = useState<Vec3 | null>(null)
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors, actors } =
    useSceneResourcesContext()
  const activeMaterials = usesUnlitMaterials(mode) ? unlitMaterials : materials
  // Every SELECTED non-brush actor's AABB box (Task 14: one per selected actor) -- shared with
  // Viewport3D.tsx via `selectionBoxes.ts` (item 16).
  const nonBrushBoxes = useMemo(() => selectedNonBrushBoxes(actors, selectedNames), [actors, selectedNames])
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const markerGroupRef = useRef<THREE.Group | null>(null)
  // Wireframe-mode click-to-select (bug report item 6): see Viewport3D.tsx's identical comment --
  // with no solid mesh drawn, a hit must come from the brush outline LINES themselves, never a
  // bounding-box fallback.
  const brushGroupRef = useRef<THREE.Group | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Shared by the tap path (item 16: the raycast pipeline itself is shared with Viewport3D.tsx via
  // `tapSelect.ts`'s `resolveTapSelect`; only the ref wiring and this pane's own zoom-scaled line-hit
  // threshold live here) -- three.js's Raycaster handles an orthographic camera's parallel rays the
  // same way it handles a perspective one's.
  const performTapSelect = useCallback(
    (clientX: number, clientY: number, additive: boolean, shiftKey: boolean) => {
      const camera = cameraRef.current
      const rect = containerRef.current?.getBoundingClientRect()
      if (!camera || !rect) return
      const action = resolveTapSelect({
        camera,
        rect,
        clientX,
        clientY,
        additive,
        shiftKey,
        mode,
        // See Viewport3D.tsx's identical comment (bug report item 6): a click in wireframe/ortho
        // views must only hit near a brush's own outline, never anywhere inside its silhouette.
        // Scaled by zoom (orthoLineHitThresholdUU) so the click buffer stays a constant screen-space
        // width (owner report: 2D brush selection was near-pixel-exact once zoomed out, since a
        // fixed world-unit threshold shrinks on screen) -- Viewport3D's own fixed threshold is the
        // deliberate delta this pane's zoom range needs and the perspective pane doesn't.
        lineThreshold: orthoLineHitThresholdUU(pose.worldUnitsPerPixel),
        meshObject: meshRef.current,
        markerObjects: markerGroupRef.current?.children ?? [],
        brushObjects: mode === 'wireframe' ? (brushGroupRef.current?.children ?? []) : [],
        actors,
        triangleOwners,
      })
      if (action.kind === 'select') onSelectActor(action.name, action.additive)
      else if (action.kind === 'deselect') onDeselect()
    },
    [actors, triangleOwners, onSelectActor, onDeselect, mode, pose.worldUnitsPerPixel],
  )

  const dragCallbacks = useMemo<DragGestureCallbacks>(
    () => ({
      onDrag: (dx, dy, buttons) => {
        setPose((prev) => {
          // Both mouse buttons together: zoom (dy-driven -- drag down zooms in, drag up zooms out;
          // `orthoDragZoom`'s own sign convention, the OPPOSITE of `orthoZoom`'s wheel-delta one),
          // matching the main spec's ortho "Camera" paragraph ("drag-pan + both-button-drag zoom");
          // a plain single-button drag pans. Ortho marquee-select (plain LMB-drag, classic UnrealEd)
          // is explicitly deferred -- see dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/.
          if ((buttons & 1) !== 0 && (buttons & 2) !== 0) return orthoDragZoom(prev, dy)
          return orthoPan(prev, axis, dx, dy)
        })
      },
      onTap: (clientX, clientY, additive, shiftKey) => performTapSelect(clientX, clientY, additive, shiftKey),
      onWheel: (deltaY) => setPose((prev) => orthoZoom(prev, deltaY)),
    }),
    [axis, performTapSelect],
  )
  const mouseDrag = useDragGesture(dragCallbacks)

  // useDragGesture owns its own internal containerRef, but this component also needs one for
  // performTapSelect's getBoundingClientRect() -- share the SAME element by forwarding the hook's
  // ref callback onto ours (mirrors Viewport3D, which uses one ref for both roles because it isn't
  // going through this hook's own ref at all; OrthoViewport must merge the two since the hook owns
  // its ref internally).
  const setContainerRef = useCallback(
    (el: HTMLDivElement | null) => {
      containerRef.current = el
      mouseDrag.containerRef.current = el
    },
    [mouseDrag],
  )

  // `F`-frame (Task 15): recenter on the bbox and fit its extent on THIS axis's (right, up) screen
  // plane -- `worldUnitsPerPixel` set from the container's own current pixel size so the fit is
  // accurate regardless of which pane this is or how large it's currently rendered (a maximized
  // pane vs. a quarter-screen one). Falls back to a nominal 800x600 if the container hasn't laid
  // out yet (a `getBoundingClientRect()` of 0x0 would otherwise divide by zero). `orthoFrameFit`
  // clamps the result (GUI bug report: an unclamped fit on a degenerate/point-actor bbox blanks the
  // whole pane, not just the marker -- see its own doc comment).
  useEffect(() => {
    if (!frameRequest) return
    const rect = containerRef.current?.getBoundingClientRect()
    const viewW = rect && rect.width > 0 ? rect.width : 800
    const viewH = rect && rect.height > 0 ? rect.height : 600
    setPose(orthoFrameFit(frameRequest.bbox, axis, { width: viewW, height: viewH }))
    // `frameRequest` is replaced wholesale on every `F` press -- see Viewport3D's identical note.
  }, [frameRequest, axis])

  // Cursor UU coordinate readout (Task 28): tracks EVERY pointer move inside the pane, not just
  // drag moves -- `useDragGesture`'s own onPointerMove is a no-op when no drag is in progress
  // (`drag.current` is null on a plain hover), so this rides alongside it rather than through it.
  const onPointerMoveWithHover = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      mouseDrag.onPointerMove(e)
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect || rect.width === 0 || rect.height === 0) return
      setHoverWorld(screenToWorld(pose, axis, { w: rect.width, h: rect.height }, e.clientX - rect.left, e.clientY - rect.top))
    },
    [mouseDrag, pose, axis],
  )
  const onPointerLeave = useCallback(() => setHoverWorld(null), [])

  return (
    <div
      ref={setContainerRef}
      style={{ width: '100%', height: '100%', touchAction: 'none', position: 'relative' }}
      onPointerDown={mouseDrag.onPointerDown}
      onPointerMove={onPointerMoveWithHover}
      onPointerLeave={onPointerLeave}
      onPointerUp={mouseDrag.onPointerUp}
      onWheel={mouseDrag.onWheel}
      onContextMenu={mouseDrag.onContextMenu}
    >
      <Canvas {...CANVAS_COLOR_MANAGEMENT} orthographic>
        {/* `actor diagram`'s own ortho background convention (`preview.py`'s BG = 64, owner ruling
            2026-08-30) -- explicit and WebGL-native, not left to `.quad-layout`'s CSS background
            showing through a transparent canvas (bug report item 1). */}
        <color attach="background" args={['#404040']} />
        <OrthoCameraRig pose={pose} axis={axis} cameraRef={cameraRef} />
        {showGrid && <GridOverlay pose={pose} axis={axis} />}
        {mode !== 'wireframe' && <mesh ref={meshRef} geometry={bufferGeometry} material={activeMaterials} />}
        {/* Issue 1: a selected brush's surface "lights up" (additive brightness boost), same as the
            3D perspective pane -- no surface to light up in wireframe mode (no solid mesh above). */}
        {mode !== 'wireframe' && (
          <SelectionHighlight bufferGeometry={bufferGeometry} triangleOwners={triangleOwners} selectedNames={selectedNames} />
        )}
        <group ref={markerGroupRef}>
          {markerActors.map((actor) => {
            // A resolved DT_Sprite billboard draws the actor's REAL class icon at its own
            // world-space footprint, untinted -- mirrors Viewport3D's identical priority (real
            // sprite over the generic dot). Part 5, Task 21's verification found this branch (and
            // the fallback's scale/tint below) missing here entirely: an un-scaled default THREE.
            // Sprite is 1x1 UU, effectively invisible in a world scaled in hundreds/thousands of UU.
            const spriteTex = actor.sprite ? textures.sprite.get(actor.sprite.tex_index) : undefined
            if (actor.sprite && spriteTex) {
              return (
                <PointActorMarker
                  key={actor.name}
                  position={actor.location}
                  aspect={actor.sprite.width / actor.sprite.height}
                  userData={{ actorName: actor.name }}
                  renderOrder={MARKER_RENDER_ORDER}
                >
                  <spriteMaterial map={spriteTex} depthWrite={false} depthTest={false} />
                </PointActorMarker>
              )
            }
            if (!markerTexture) return null
            return (
              <PointActorMarker
                key={actor.name}
                position={actor.location}
                aspect={1}
                userData={{ actorName: actor.name }}
                renderOrder={MARKER_RENDER_ORDER}
              >
                <spriteMaterial map={markerTexture} color={MARKER_COLOR_THREE} depthWrite={false} depthTest={false} />
              </PointActorMarker>
            )
          })}
        </group>
        {/* Every brush wireframes in its own CSG colour (`actor diagram`'s ISO-mode convention,
            spec §2), selected one(s) bold -- the whole picture in wireframe mode (no solid mesh
            above); just the highlight ring on top of the mesh in any other mode (Part 4, Task 20). */}
        <BrushOutlines
          actors={actors}
          selectedNames={selectedNames}
          mode={mode === 'wireframe' ? 'csg-all' : 'selected-only'}
          groupRef={brushGroupRef}
        />
        {/* Vertex + pivot markers for a selected brush (bug report item 7). */}
        <SelectionMarkers actors={actors} selectedNames={selectedNames} />
        {/* Collision-cylinder / light-radius overlays, toggled globally (not by selection). */}
        {showRadii && <RadiiOverlays actors={actors} view={axis} />}
        {nonBrushBoxes.map(({ name, lo, hi }) => (
          <box3Helper key={name} args={[new THREE.Box3(new THREE.Vector3(...lo), new THREE.Vector3(...hi)), SELECTION_BOX_COLOR]} />
        ))}
      </Canvas>
      {/* Cursor UU coordinate readout (Task 28) -- the selected actor's own location/size is
          already shown by the side Inspector (spec §7's other clause), not duplicated here. */}
      {hoverWorld && (
        <div className="ortho-cursor-readout">
          {hoverWorld.map((c) => Math.round(c)).join(', ')}
        </div>
      )}
    </div>
  )
}

