// R3F perspective viewport: draws the scene payload's polys textured+lit, matching `level photo
// --native`'s render.rs. Each poly draws base-texture * shading with MeshBasicMaterial (still no
// scene lights): a lightmapped world surf multiplies by its baked lumel grid (the lightmap atlas,
// sampled through a second `uv1` set); every other poly multiplies by a per-face KEY_LIGHT flat
// shade carried in per-vertex colours (render.rs's own fallback for unlit surfs). Owns the
// faithful UnrealEd drag-fly camera (spec, "Camera") and click-to-select. This is the ONLY place
// model data meets three.js -- Viewport3D draws what `serve` hands it and owns no model/diff/solve
// logic of its own (spec, "The client").
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject, PointerEvent as ReactPointerEvent } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import { BrushOutlines } from './BrushOutlines'
import type { CameraPose, Vec3 } from './camera'
import { cameraBasis, dollyAndTurn, flyInput, flyMove, look, orbit, pan, zoom } from './camera'
import type { DragGestureCallbacks } from './dragGesture'
import { useDragGesture } from './dragGesture'
import type { FrameRequest } from './frame'
import { bboxCenter, bboxMaxExtent } from './frame'
import { MARKER_COLOR } from './markers'
import { MeshWireframe } from './MeshWireframe'
import { PointActorMarker } from './PointActorMarker'
import { RadiiOverlays } from './RadiiOverlays'
import { SelectionHighlight, SurfaceSelectionHighlight } from './SelectionHighlight'
import { SelectionMarkers } from './SelectionMarkers'
import { selectedNonBrushBoxes } from './selectionBoxes'
import type { ShadingMode } from './shadingMode'
import { usesUnlitMaterials } from './shadingMode'
import { useSceneResourcesContext } from './useSceneResourcesContext'
import { isTap } from './selection'
import { resolveTapSelect } from './tapSelect'
import { computeTwoFingerDelta } from './touchGesture'
import type { TouchPoint } from './touchGesture'
import { applyCameraPose, CANVAS_COLOR_MANAGEMENT, WIREFRAME_LINE_HIT_WORLD_UNITS } from './viewportRender'

const INITIAL_POSE: CameraPose = { position: [0, -500, 200], pitch: -10, yaw: 90 }

function CameraRig({ pose, cameraRef }: { pose: CameraPose; cameraRef: MutableRefObject<THREE.Camera | null> }) {
  const { camera } = useThree()
  useEffect(() => {
    cameraRef.current = camera
  }, [camera, cameraRef])
  useFrame(() => {
    applyCameraPose(camera as THREE.PerspectiveCamera, pose)
  })
  return null
}

const FLY_KEYS = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyQ', 'KeyE'])
const FLY_SPEED_UU_PER_SEC = 600

/** WASD (horizontal) + Q/E (vertical) fly movement, independent of any mouse button -- lets you
 * move without holding RMB at all. Listens on `window` (not just the viewport) so it works
 * whenever no text input has focus; translation only, via `flyMove`, applied every frame so it's
 * frame-rate independent and works while multiple keys are held at once. */
function FlyKeys({ setPose }: { setPose: (fn: (prev: CameraPose) => CameraPose) => void }) {
  const held = useRef<Set<string>>(new Set())

  useEffect(() => {
    const isTypingTarget = (t: EventTarget | null) =>
      t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
    const onKeyDown = (e: KeyboardEvent) => {
      if (!FLY_KEYS.has(e.code) || isTypingTarget(e.target)) return
      held.current.add(e.code)
    }
    const onKeyUp = (e: KeyboardEvent) => {
      held.current.delete(e.code)
    }
    const onBlur = () => held.current.clear() // losing window focus mid-press must not stick a key "held"
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [])

  useFrame((_state, delta) => {
    if (held.current.size === 0) return
    const input = flyInput(held.current)
    if (input.forward === 0 && input.right === 0 && input.up === 0) return
    setPose((prev) => flyMove(prev, input, FLY_SPEED_UU_PER_SEC, delta))
  })

  return null
}

const SELECTION_BOX_COLOR = 0x00e5ff

// `THREE.Color` reads 0..1 components -- built once from `markers.MARKER_COLOR` (module-scope: a
// plain data object, no WebGL context needed).
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)

export interface Viewport3DProps {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // Surface (single-polygon texture) selection -- a DISTINCT selection kind from `selectedNames`
  // above (GUI.md "Selection & the Inspector"): a plain LMB-tap on a brush surface in a non-wireframe
  // mode selects just that one polygon; Shift+LMB on the same surface selects the whole brush
  // instead (`onSelectActor`). `selectedSurfaces` holds `selectionSet.ts`'s `surfaceKey` strings.
  selectedSurfaces: ReadonlySet<string>
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  // A tap that hits nothing selectable deselects everything (owner ruling 2026-09-15) -- the same
  // callback QuadLayout already wires to SelectionKeys' `Esc` handler, so a miss and `Esc` land on
  // one shared deselect path rather than two.
  onDeselect: () => void
  // `F`-frame (Part 3, Task 15): a new (higher `seq`) request retargets the camera to fit `bbox`,
  // keeping the current viewing angle (pitch/yaw) and backing the position off far enough along it.
  frameRequest?: FrameRequest | null
  // Per-pane shading mode (Part 4, Task 20): 'wireframe' draws ONLY the CSG-colored brush rings (no
  // solid mesh); 'unlit'/'flat'/'lit' draw the existing solid mesh -- 'flat' renders identically to
  // 'unlit' for now (the main spec's own "Also open": its exact definition isn't pinned down yet).
  mode?: ShadingMode
  // Collision-cylinder / light-radius overlay toggle -- one switch for every pane (QuadLayout),
  // mirroring the existing grid-toggle convention; default off. Scoped to the current selection
  // (owner ruling 2026-09-15) -- on shows only the selected actor(s)' radii, not every actor's.
  showRadii?: boolean
  // Mover solid-geometry toggle (GUI.md "Movers"): a Mover ALWAYS renders wireframe-outline-only by
  // default, in every shading mode -- this ADDS its solid (textured/lit per `mode`) geometry on top
  // of the outline when true; false (default) leaves it outline-only. No effect in 'wireframe' mode
  // (nothing solid draws there regardless).
  showMoverSolid?: boolean
}

// Which single touch contact is the tap-selection candidate: the FIRST finger down, tracked only
// while it stays the only contact. A second finger touching down invalidates it (the gesture is a
// two-finger pan/pinch, never a tap) -- see onPointerDown/onPointerUp below.
interface TouchTapTracker {
  pointerId: number
  totalDx: number
  totalDy: number
}

// `atlas`/`lightmap` stay in Viewport3DProps for API stability, but the built geometry/textures
// they used to drive locally now come from SceneResourcesContext (Task 3) -- unused here directly.
export function Viewport3D({
  scene,
  selectedNames,
  onSelectActor,
  selectedSurfaces,
  onSelectSurface,
  onDeselect,
  frameRequest = null,
  mode = 'lit',
  showRadii = false,
  showMoverSolid = false,
}: Viewport3DProps) {
  const [pose, setPose] = useState<CameraPose>(INITIAL_POSE)

  // `F`-frame (Task 15): retarget the pose to fit the requested bbox, keeping pitch/yaw (the current
  // viewing angle) and backing the camera off along its own forward vector far enough to fit the
  // bbox's largest extent -- a design choice (the plan doesn't specify the exact framing math): a
  // reorientation-free "dolly to fit" reads as less jarring than snapping to a fixed angle.
  useEffect(() => {
    if (!frameRequest) return
    const center = bboxCenter(frameRequest.bbox)
    const extent = bboxMaxExtent(frameRequest.bbox)
    setPose((prev) => {
      const { forward } = cameraBasis(prev.pitch, prev.yaw)
      const distance = extent * 1.5 + 100 // comfortable margin, never closer than 100 UU
      return {
        position: [
          center[0] - forward[0] * distance,
          center[1] - forward[1] * distance,
          center[2] - forward[2] * distance,
        ],
        pitch: prev.pitch,
        yaw: prev.yaw,
      }
    })
    // `frameRequest` is replaced wholesale (never mutated in place) by QuadLayout on every `F`
    // press, so depending on the object itself re-fires exactly when `seq` changes.
  }, [frameRequest])
  // Live screen position of every currently-down touch contact, by `pointerId` -- lets multi-touch
  // gestures (unlike `drag`, which assumes exactly one contact) compute each finger's own delta and
  // tell 1-finger from 2-finger gestures apart. Mouse/pen input never touches this map (gated on
  // `e.pointerType === 'touch'` below) so desktop behavior is unchanged.
  const touchPoints = useRef<Map<number, TouchPoint>>(new Map())
  const touchTap = useRef<TouchTapTracker | null>(null)
  const cameraRef = useRef<THREE.Camera | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const markerGroupRef = useRef<THREE.Group | null>(null)
  // Wireframe-mode click-to-select (bug report item 6): with no solid mesh drawn, a hit must come
  // from the brush outline LINES themselves, never a bounding-box fallback -- see performTapSelect.
  const brushGroupRef = useRef<THREE.Group | null>(null)
  // Geometry/textures/markers are built ONCE and shared across every pane via
  // SceneResourcesContext (Part 0, Tasks 1-2) -- Viewport3D no longer builds its own (Task 3;
  // camera/pointer handling/click-to-select are UNCHANGED in this task).
  const {
    bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
    moverGeometry, moverMaterials, moverUnlitMaterials, moverTriangleOwners,
    meshWireframeGeometry,
    textures, markerTexture, markerActors,
  } = useSceneResourcesContext()
  // 'unlit'/'lit' otherwise rendered the identical mesh (materials built once, shared across every
  // pane, with no per-mode variant) -- pick the lightmap-free array for 'unlit' so it genuinely
  // differs, matching the main spec's 4-distinct-shading-modes requirement (review finding).
  const activeMaterials = usesUnlitMaterials(mode) ? unlitMaterials : materials
  const activeMoverMaterials = usesUnlitMaterials(mode) ? moverUnlitMaterials : moverMaterials

  // A single "primary" selected actor (the first, by scene.actors order, whose name is in the set)
  // -- ONLY for the camera orbit pivot (Alt-drag), which stays single-target; Task 15's frame/`F`
  // key is the real multi-actor camera mechanism, out of this task's scope. Highlight rendering
  // below (BrushOutlines, the non-brush box fallback) draws one per SELECTED actor, not just this
  // one (Task 14).
  const primarySelectedActor = useMemo(
    () => scene.actors.find((a) => selectedNames.has(a.name)) ?? null,
    [scene.actors, selectedNames],
  )

  const orbitPivot: Vec3 = useMemo(() => {
    if (!primarySelectedActor) return [0, 0, 0]
    return [
      (primarySelectedActor.bbox_lo[0] + primarySelectedActor.bbox_hi[0]) / 2,
      (primarySelectedActor.bbox_lo[1] + primarySelectedActor.bbox_hi[1]) / 2,
      (primarySelectedActor.bbox_lo[2] + primarySelectedActor.bbox_hi[2]) / 2,
    ]
  }, [primarySelectedActor])

  // Every SELECTED non-brush actor's AABB box (Task 14: one per selected actor, not just one).
  const nonBrushBoxes = useMemo(() => selectedNonBrushBoxes(scene.actors, selectedNames), [scene.actors, selectedNames])

  // Shared by both the mouse tap path and the touch tap path (item 16: the raycast pipeline itself
  // is shared with OrthoViewport.tsx via `tapSelect.ts`'s `resolveTapSelect`; only the ref wiring
  // and this pane's own fixed line-hit threshold live here). Split out so onPointerUp's touch branch
  // can call the exact same selection logic as the existing mouse branch, instead of a second copy.
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
        // Wireframe mode draws no solid mesh -- a click must land near a brush's own outline LINE
        // (bug report item 6: UED22 never lets a click anywhere inside a brush's silhouette select
        // it in wireframe/ortho views). A fixed world-unit threshold (unlike OrthoViewport's
        // zoom-scaled one) is fine here: the perspective pane's own dolly-zoom already keeps nearby
        // geometry at a roughly stable screen size.
        lineThreshold: WIREFRAME_LINE_HIT_WORLD_UNITS,
        meshObject: meshRef.current,
        markerObjects: markerGroupRef.current?.children ?? [],
        brushObjects: mode === 'wireframe' ? (brushGroupRef.current?.children ?? []) : [],
        actors: scene.actors,
        triangleOwners,
        trianglePolyIndex,
      })
      if (action.kind === 'select-actor') onSelectActor(action.name, action.additive)
      else if (action.kind === 'select-surface') onSelectSurface(action.actor, action.polyIndex, action.additive)
      else if (action.kind === 'deselect') onDeselect()
    },
    [scene.actors, triangleOwners, trianglePolyIndex, onSelectActor, onSelectSurface, onDeselect, mode],
  )

  // Mouse-only pointer-lock/capture/tap-vs-drag plumbing, shared with ortho panes (Part 0, Task 4).
  const dragCallbacks = useMemo<DragGestureCallbacks>(
    () => ({
      onDrag: (dx, dy, buttons, altKey) => {
        setPose((prev) => {
          if (altKey && (buttons & 1) !== 0) return orbit(prev, orbitPivot, dx, dy)
          if ((buttons & 1) !== 0 && (buttons & 2) !== 0) return pan(prev, dx, dy)
          if ((buttons & 2) !== 0) return look(prev, dx, dy)
          if ((buttons & 1) !== 0) return dollyAndTurn(prev, dx, dy)
          return prev
        })
      },
      onTap: (clientX, clientY, additive, shiftKey) => performTapSelect(clientX, clientY, additive, shiftKey),
      onWheel: (deltaY) => setPose((prev) => zoom(prev, deltaY)),
    }),
    [orbitPivot, performTapSelect],
  )
  const mouseDrag = useDragGesture(dragCallbacks)
  const containerRef = mouseDrag.containerRef

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.pointerType === 'touch') {
        e.currentTarget.setPointerCapture(e.pointerId)
        const isFirstContact = touchPoints.current.size === 0
        touchPoints.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
        // Only the FIRST finger down is a tap candidate; a second finger arriving before the first
        // lifts means this is a two-finger gesture, never a tap (see onPointerUp).
        touchTap.current = isFirstContact ? { pointerId: e.pointerId, totalDx: 0, totalDy: 0 } : null
        return
      }
      mouseDrag.onPointerDown(e)
    },
    [mouseDrag],
  )

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.pointerType === 'touch') {
        const points = touchPoints.current
        const prev = points.get(e.pointerId)
        if (!prev) return // stray move with no matching pointerdown (shouldn't happen)
        const curr: TouchPoint = { x: e.clientX, y: e.clientY }

        if (points.size === 1) {
          // One finger: rotate in place, the mobile-3D-viewer convention (Google Maps 3D,
          // SketchFab). Applied on every move like the mouse paths below; whether the whole
          // gesture ends up being a tap is decided separately, at pointerup.
          const dx = curr.x - prev.x
          const dy = curr.y - prev.y
          points.set(e.pointerId, curr)
          if (touchTap.current?.pointerId === e.pointerId) {
            touchTap.current.totalDx += dx
            touchTap.current.totalDy += dy
          }
          if (dx !== 0 || dy !== 0) setPose((prevPose) => look(prevPose, dx, dy))
          return
        }

        // Two (or more -- extra fingers beyond the first two are ignored) fingers: pan from the
        // midpoint's movement + pinch-zoom from the separation-distance change, applied together
        // so both gestures compose naturally in one motion.
        const ids = [...points.keys()].slice(0, 2)
        const before: [TouchPoint, TouchPoint] = [points.get(ids[0])!, points.get(ids[1])!]
        points.set(e.pointerId, curr)
        const after: [TouchPoint, TouchPoint] = [points.get(ids[0])!, points.get(ids[1])!]
        const { panDx, panDy, zoomDelta } = computeTwoFingerDelta(before, after)
        if (panDx !== 0 || panDy !== 0 || zoomDelta !== 0) {
          setPose((prevPose) => zoom(pan(prevPose, panDx, panDy), zoomDelta))
        }
        return
      }

      mouseDrag.onPointerMove(e)
    },
    [mouseDrag],
  )

  const onPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.pointerType === 'touch') {
        e.currentTarget.releasePointerCapture(e.pointerId)
        touchPoints.current.delete(e.pointerId)
        const tap = touchTap.current
        if (tap?.pointerId !== e.pointerId) return // not the tap-candidate finger (or none survived)
        touchTap.current = null
        if (isTap(0, 0, tap.totalDx, tap.totalDy)) performTapSelect(e.clientX, e.clientY, false, false) // touch has no Ctrl/Shift-equivalent
        return
      }
      mouseDrag.onPointerUp(e)
    },
    [mouseDrag, performTapSelect],
  )

  const onWheel = mouseDrag.onWheel
  const onContextMenu = mouseDrag.onContextMenu

  return (
    <div
      ref={containerRef}
      // touch-action: none stops the browser from claiming a touch drag inside the viewport for
      // pull-to-refresh/page-scroll/pinch-zoom-the-page -- gestures below own it instead. Scoped to
      // this div only, so the rest of the page (org panel, inspector) still scrolls normally.
      style={{ width: '100%', height: '100%', touchAction: 'none' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      onContextMenu={onContextMenu}
    >
      {/* far spans a whole UE1 level (world is +/-32768 UU, so ~65k across); R3F's default far=1000
          clipped distant geometry to the background ("further objects render black"). near=1 keeps
          z-precision over that range. */}
      <Canvas {...CANVAS_COLOR_MANAGEMENT} camera={{ fov: 75, near: 1, far: 131072 }}>
        {/* UED22's real perspective viewport background (bug report item 2) -- explicit and
            WebGL-native rather than relying on `.quad-layout`'s CSS background showing through a
            transparent canvas (fragile: e.g. broken by an unrelated CSS parse failure). */}
        <color attach="background" args={['#000000']} />
        <CameraRig pose={pose} cameraRef={cameraRef} />
        <FlyKeys setPose={setPose} />
        {mode !== 'wireframe' && <mesh ref={meshRef} geometry={bufferGeometry} material={activeMaterials} />}
        {/* Movers: wireframe-outline-only by default in every mode (GUI.md "Movers") -- their solid
            geometry is split OUT of `bufferGeometry` above (SceneResourcesContext) and only drawn
            here when the "Movers: on" toggle is active, ADDITIONALLY on top of the outline (never
            replacing it -- `BrushOutlines` below still draws every Mover's ring unconditionally). */}
        {mode !== 'wireframe' && showMoverSolid && (
          <mesh geometry={moverGeometry} material={activeMoverMaterials} />
        )}
        {/* Issue 1: a selected brush's surface "lights up" (additive brightness boost), same as the
            2D ortho panes below -- no surface to light up in wireframe mode (no solid mesh above). */}
        {mode !== 'wireframe' && (
          <SelectionHighlight
            bufferGeometry={bufferGeometry}
            triangleOwners={triangleOwners}
            selectedNames={selectedNames}
            materials={activeMaterials}
          />
        )}
        {/* Texture (single-surface) selection highlight -- a DISTINCT selection kind from the
            whole-brush highlight above (GUI.md "Selection & the Inspector"); only ever one of the
            two sets is non-empty at a time (App.tsx clears the other kind on every selection
            change), so this and `SelectionHighlight` never light up the same brush at once. */}
        {mode !== 'wireframe' && (
          <SurfaceSelectionHighlight
            bufferGeometry={bufferGeometry}
            triangleOwners={triangleOwners}
            trianglePolyIndex={trianglePolyIndex}
            selectedSurfaces={selectedSurfaces}
            materials={activeMaterials}
          />
        )}
        {mode !== 'wireframe' && showMoverSolid && (
          <SelectionHighlight
            bufferGeometry={moverGeometry}
            triangleOwners={moverTriangleOwners}
            selectedNames={selectedNames}
            materials={activeMoverMaterials}
          />
        )}
        <group ref={markerGroupRef}>
          {markerActors.map((actor) => {
            // A resolved DT_Sprite billboard draws the actor's REAL class icon texture (its atlas
            // rect, cropped by `useTextures` above) at its own world-space footprint, untinted --
            // the actual sprite's colours, not a class-coloured guess. Falls back to the generic
            // grey dot (`markerTexture`/`MARKER_COLOR_THREE`) when there's no sprite, or the atlas
            // texture for it isn't in `textures.sprite` yet (e.g. mid-load). Deliberately the
            // SPRITE map, not the base `textures.map` -- see `useTextures`'s docstring for why
            // sharing the base (flipY=false) texture here renders the billboard upside-down.
            const spriteTex = actor.sprite ? textures.sprite.get(actor.sprite.tex_index) : undefined
            if (actor.sprite && spriteTex) {
              return (
                <PointActorMarker
                  key={actor.name}
                  position={actor.location}
                  aspect={actor.sprite.width / actor.sprite.height}
                  userData={{ actorName: actor.name }}
                >
                  <spriteMaterial map={spriteTex} depthWrite={false} />
                </PointActorMarker>
              )
            }
            if (!markerTexture) return null
            return (
              <PointActorMarker key={actor.name} position={actor.location} aspect={1} userData={{ actorName: actor.name }}>
                <spriteMaterial map={markerTexture} color={MARKER_COLOR_THREE} depthWrite={false} />
              </PointActorMarker>
            )
          })}
        </group>
        {/* Wireframe mode: every brush wireframes in its own CSG colour, matching `actor diagram`'s
            ISO-mode convention (Part 2) -- no solid mesh above. Any other mode: the textured/shaded
            mesh already renders every brush's contribution, so only the selected one's bold ring is
            still needed on top of it (Part 4, Task 20 -- supersedes the old `geometry_pinned`-based
            branching, which is now exactly what `mode` itself decides). */}
        <BrushOutlines
          actors={scene.actors}
          selectedNames={selectedNames}
          mode={mode === 'wireframe' ? 'csg-all' : 'selected-only'}
          groupRef={brushGroupRef}
        />
        {/* A mesh actor (never a brush -- no CSG ring above) renders its own triangle-edge wireframe
            here instead, matching a brush's wireframe convention in this mode (GUI.md "Shading
            modes"). Solid mesh rendering in every other mode is unaffected (unchanged, above). */}
        {mode === 'wireframe' && <MeshWireframe geometry={meshWireframeGeometry} />}
        {/* Vertex + pivot markers for a selected brush (bug report item 7). */}
        <SelectionMarkers actors={scene.actors} selectedNames={selectedNames} />
        {/* Collision-cylinder / light-radius overlays, toggled globally but scoped to the current
            selection (owner ruling 2026-09-15) -- draws nothing when nothing is selected. */}
        {showRadii && <RadiiOverlays actors={scene.actors} view="perspective" selectedNames={selectedNames} />}
        {/* Every selected NON-brush actor (no CSG ring to draw) falls back to its own plain AABB
            box -- one per selected actor (Task 14), not just a single one. */}
        {nonBrushBoxes.map(({ name, lo, hi }) => (
          <box3Helper key={name} args={[new THREE.Box3(new THREE.Vector3(...lo), new THREE.Vector3(...hi)), SELECTION_BOX_COLOR]} />
        ))}
      </Canvas>
    </div>
  )
}
