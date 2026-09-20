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
import { postStage } from '../api'
import { BrushOutlines } from './BrushOutlines'
import { DirectionalArrows } from './DirectionalArrows'
import { moveAlongAxis } from './actorMove'
import type { CameraPose, Vec3 } from './camera'
import { cameraBasis, dollyAndTurn, flyInput, flyMove, look, orbit, pan, zoom } from './camera'
import type { DragGestureCallbacks } from './dragGesture'
import { useDragGesture } from './dragGesture'
import { applyDelta, applyStagedOffsets, resolveActorMoveAxis, stagedLocationsFor } from './dragStage'
import type { MoveDragAccumulator } from './moveDragThreshold'
import { accumulateMoveDragFrame, freshMoveDragAccumulator } from './moveDragThreshold'
import type { FrameRequest } from './frame'
import { bboxCenter, bboxMaxExtent } from './frame'
import { DEFAULT_MARKER_FOOTPRINT_UU, MARKER_COLOR, MARKER_RENDER_ORDER, worldUnitsPerPixelAt } from './markers'
import { MeshWireframe, SelectedMeshWireframe } from './MeshWireframe'
import { MoveJoystick } from './MoveJoystick'
import type { JoystickVector } from './joystick'
import { PointActorMarker } from './PointActorMarker'
import { RadiiOverlays } from './RadiiOverlays'
import { ActorSelectionHighlight, SurfaceSelectionHighlight } from './SelectionHighlight'
import { SELECTED_SPRITE_TINT, UNSELECTED_SPRITE_TINT } from './selectionColor'
import { SelectionMarkers } from './SelectionMarkers'
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

/** The touch joystick/up-down-buttons' counterpart to `FlyKeys` above -- same `flyMove`/
 * `FLY_SPEED_UU_PER_SEC` mechanics, driven by `MoveJoystick.tsx`'s continuous analog input instead
 * of held keys. A separate ref/component (not folded into `FlyKeys`' `held` set) so touch input
 * never touches keyboard state -- the two channels are fully independent, satisfying "must not
 * interfere with... keyboard controls when both are present" (a touch-capable laptop with a
 * keyboard). `inputRef.current` is mutated directly by `MoveJoystick`'s callbacks (Viewport3D's
 * `onStickChange`/`onVerticalChange`), read fresh every frame here -- the same ref-based, no-React-
 * state-per-move pattern `FlyKeys`' `held` set already uses, for the same reason (a re-render per
 * pointer-move would be wasteful). */
function TouchFlyInput({
  inputRef,
  setPose,
}: {
  inputRef: MutableRefObject<{ forward: number; right: number; up: number }>
  setPose: (fn: (prev: CameraPose) => CameraPose) => void
}) {
  useFrame((_state, delta) => {
    const input = inputRef.current
    if (input.forward === 0 && input.right === 0 && input.up === 0) return
    setPose((prev) => flyMove(prev, input, FLY_SPEED_UU_PER_SEC, delta))
  })
  return null
}

// `THREE.Color` reads 0..1 components -- built once from `markers.MARKER_COLOR` (module-scope: a
// plain data object, no WebGL context needed).
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)

export interface Viewport3DProps {
  level: string
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
  // Fires once a Ctrl/Cmd-drag gesture's `postStage` call resolves (Task 10) -- the staged actor
  // names, so App.tsx's own `stagedNames` bookkeeping (SaveBar's gate) stays current without this
  // component (or App) re-deriving the full staging state on every drag. Optional: a caller that
  // doesn't care about the Save/Discard bar (e.g. a future embedding) can omit it.
  onStaged?: (names: string[]) => void
  // The shared "confirmed staged" visual position store (final review fix wave, Critical 2) --
  // owned by App.tsx (plan.md's File Structure table), not a private copy of this component. Every
  // pane reads/writes the SAME `stagedOffsets`/`stagedOffsetsRef`/`setStagedOffsets`, so a drag in
  // one pane previews live in the others too, and App's Discard/Save-success/Load-accept handlers
  // can actually clear what's on screen. `stagedOffsetsRef` mirrors `stagedOffsets` synchronously
  // (React state is async) for the same-callback read/write pattern `onDrag`/`onPointerUp` need.
  stagedOffsets: Record<string, Vec3>
  stagedOffsetsRef: MutableRefObject<Record<string, Vec3>>
  setStagedOffsets: (next: Record<string, Vec3>) => void
  // Surfaces a failed `postStage` call (final review fix wave, Important 3) -- App.tsx shows it the
  // same way it already shows a failed Load/Rebuild. Optional, matching `onStaged`'s convention.
  onStageError?: (message: string) => void
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
  level,
  scene,
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
  // The mobile move-joystick/up-down-buttons' live input (board item
  // mobile-3d-move-joystick-visual-design-pending) -- mutated directly by MoveJoystick's callbacks
  // below, read every frame by TouchFlyInput. A ref, not React state: matches FlyKeys' own `held`
  // set (a per-move re-render would be wasteful and isn't needed for anything visible).
  const touchFlyInput = useRef<{ forward: number; right: number; up: number }>({ forward: 0, right: 0, up: 0 })
  const onJoystickStickChange = useCallback((v: JoystickVector) => {
    touchFlyInput.current.forward = v.forward
    touchFlyInput.current.right = v.right
  }, [])
  const onJoystickVerticalChange = useCallback((up: number) => {
    touchFlyInput.current.up = up
  }, [])
  const cameraRef = useRef<THREE.Camera | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  // The Movers:on toggle's own solid mesh (board item `mover-polys-unselectable-in-movers-on-mode`):
  // a separate ref from `meshRef` since it's a distinct <mesh>, only mounted when `showMoverSolid` is
  // on and `mode !== 'wireframe'` -- see performTapSelect below.
  const moverMeshRef = useRef<THREE.Mesh | null>(null)
  const meshPickRef = useRef<THREE.Mesh | null>(null)
  const meshEdgePickRef = useRef<THREE.LineSegments | null>(null)
  const markerGroupRef = useRef<THREE.Group | null>(null)
  // Wireframe-mode click-to-select (bug report item 6): with no solid mesh drawn, a hit must come
  // from the brush outline LINES themselves, never a bounding-box fallback -- see performTapSelect.
  const brushGroupRef = useRef<THREE.Group | null>(null)
  // A Mover's own always-visible outline (`BrushOutlines.tsx`'s `moverGroupRef`) -- wired into
  // performTapSelect's raycast candidates in EVERY mode, not just wireframe (board item
  // `mover-not-selectable-via-wireframe-click`).
  const moverOutlineGroupRef = useRef<THREE.Group | null>(null)
  // Geometry/textures/markers are built ONCE and shared across every pane via
  // SceneResourcesContext (Part 0, Tasks 1-2) -- Viewport3D no longer builds its own (Task 3;
  // camera/pointer handling/click-to-select are UNCHANGED in this task).
  const {
    bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
    moverGeometry, moverMaterials, moverUnlitMaterials, moverTriangleOwners, moverTrianglePolyIndex,
    meshWireframeGeometry, meshPickGeometry, meshTriangleOwners, meshTrianglePolyIndex,
    meshEdgePickGeometry, meshEdgeOwners, meshEdgePolyIndex,
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
  // below (BrushOutlines, ActorSelectionHighlight) draws one per SELECTED actor, not just this
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

  // `stagedOffsets`/`stagedOffsetsRef`/`setStagedOffsets` are now App-owned props (Critical 2, final
  // review fix wave) -- see Viewport3DProps' own doc comment. `dragMovedRef` tracks whether the
  // CURRENT gesture actually displaced anything, so a plain Ctrl+click with no real movement doesn't
  // fire a no-op `postStage`. `moveDragAccRef` gates the move branch on the SAME tap-vs-drag
  // threshold `onTap` already respects (Critical 1) -- reset fresh at every pointerdown, below.
  // `preGestureOffsetsRef` snapshots `stagedOffsetsRef.current` at the same reset point, so a failed
  // `postStage` (Important 3) can revert exactly THIS gesture's own displacement without clobbering
  // an earlier, already-staged move.
  const dragMovedRef = useRef(false)
  const moveDragAccRef = useRef<MoveDragAccumulator>(freshMoveDragAccumulator())
  const preGestureOffsetsRef = useRef<Record<string, Vec3>>({})

  // `scene.actors`, with every staged actor's world-space fields (location/bbox/brush polys+
  // local_origin/directional_arrow lines) translated to its current staged position -- the single
  // derived array fed to every position-driven overlay below (BrushOutlines, SelectionMarkers,
  // DirectionalArrows, RadiiOverlays) so a Ctrl/Cmd-drag move is reflected consistently across all
  // of them, not just the point-actor marker sprite (which patches `.location` inline below, since
  // it reads from the separately-sourced `markerActors` context list, not this array). A brush/mesh
  // actor's own BAKED CSG solid mesh (`bufferGeometry`) is the one thing this can't move -- see
  // `applyStagedOffset`'s own doc comment for why, and Viewport3D's mesh `<mesh ref={meshRef} .../>`
  // below (unchanged, still reads `scene.actors`-derived geometry, not this array).
  const effectiveActors = useMemo(() => applyStagedOffsets(scene.actors, stagedOffsets), [scene.actors, stagedOffsets])

  // Selected non-brush (sprite/mesh) actor names -- drives the UED22-matched color-tint highlight
  // below (GUI-PARITY.md "Selection highlight rendering"), which replaced the plain cyan AABB box
  // this codebase used before that RE finding: UED22 has no generic selection bounding box by
  // default, only this color tint.
  const selectedNonBrushNames = useMemo(
    () => new Set(scene.actors.filter((a) => !a.brush && selectedNames.has(a.name)).map((a) => a.name)),
    [scene.actors, selectedNames],
  )

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
        moverMeshObject: moverMeshRef.current,
        moverTriangleOwners,
        moverTrianglePolyIndex,
        meshPickObject: meshPickRef.current,
        meshTriangleOwners,
        meshTrianglePolyIndex,
        meshEdgePickObject: meshEdgePickRef.current,
        meshEdgeOwners,
        meshEdgePolyIndex,
        markerObjects: markerGroupRef.current?.children ?? [],
        brushObjects: mode === 'wireframe' ? (brushGroupRef.current?.children ?? []) : [],
        // Not gated to wireframe mode -- see `TapSelectParams.moverOutlineObjects`' doc comment.
        moverOutlineObjects: moverOutlineGroupRef.current?.children ?? [],
        actors: scene.actors,
        triangleOwners,
        trianglePolyIndex,
      })
      if (action.kind === 'select-actor') onSelectActor(action.name, action.additive)
      else if (action.kind === 'select-surface') onSelectSurface(action.actor, action.polyIndex, action.additive)
      else if (action.kind === 'deselect') onDeselect()
    },
    [
      scene.actors, triangleOwners, trianglePolyIndex, meshTriangleOwners, meshTrianglePolyIndex,
      meshEdgeOwners, meshEdgePolyIndex,
      moverTriangleOwners, moverTrianglePolyIndex, onSelectActor, onSelectSurface, onDeselect, mode,
    ],
  )

  // Mouse-only pointer-lock/capture/tap-vs-drag plumbing, shared with ortho panes (Part 0, Task 4).
  const dragCallbacks = useMemo<DragGestureCallbacks>(
    () => ({
      onDrag: (dx, dy, buttons, altKey, additive) => {
        // Ctrl/Cmd-drag actor translation (spec "Interaction design") -- resolved BEFORE the camera
        // dispatch below, and returns unconditionally once resolved: an actor-move gesture must
        // never also move the camera. `selectedNames.size > 0` is baked into `resolveActorMoveAxis`
        // itself, so Ctrl held with nothing selected correctly falls through to the camera dispatch.
        const axis = resolveActorMoveAxis(additive, buttons, selectedNames)
        if (axis) {
          // Critical 1 (final review fix wave): apply no move while this gesture's CUMULATIVE
          // movement is still within the tap-vs-drag threshold -- and, since `axis` is truthy
          // (Ctrl/Cmd held over a non-empty selection), still `return` unconditionally either way,
          // never falling through to the camera dispatch below (Ctrl/Cmd stays a multi-select
          // gesture-in-progress, not a camera move, until it's resolved as one or the other).
          const frame = accumulateMoveDragFrame(moveDragAccRef.current, dx, dy)
          if (frame) {
            const camera = cameraRef.current
            const rect = containerRef.current?.getBoundingClientRect()
            if (camera && rect && primarySelectedActor) {
              // Constant-screen-size scale factor, the SAME mechanism `SelectionMarkers.tsx`'s
              // `VertexDot`/`PivotMarker` use (`markers.ts`'s `worldUnitsPerPixelAt`) -- anchored on
              // the primary selected actor's location, reflected into three.js's world space (the
              // content group applies `scale={[1,-1,1]}`; the camera is posed in that SAME reflected
              // space by `applyCameraPose`, see its own doc comment) so the distance-to-camera term is
              // correct, not mixing reflected-camera against unreflected-actor coordinates.
              const worldPos = new THREE.Vector3(
                primarySelectedActor.location[0],
                -primarySelectedActor.location[1],
                primarySelectedActor.location[2],
              )
              const worldUnitsPerPixel = worldUnitsPerPixelAt(camera, worldPos, rect.height)
              const delta = moveAlongAxis(frame.dx, axis, worldUnitsPerPixel)
              const next = applyDelta(stagedOffsetsRef.current, selectedNames, delta, scene.actors)
              stagedOffsetsRef.current = next
              setStagedOffsets(next) // local preview only -- no network call per pointer-move frame
              dragMovedRef.current = true
            }
          }
          return
        }
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
    [orbitPivot, performTapSelect, selectedNames, primarySelectedActor, scene.actors, stagedOffsetsRef, setStagedOffsets],
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
      // Reset the actor-move gesture trackers fresh for this NEW gesture (Critical 1's threshold
      // accumulator must not carry over from a previous drag; Important 3's revert-on-failure
      // snapshot must reflect what was staged BEFORE this gesture, not some earlier one).
      moveDragAccRef.current = freshMoveDragAccumulator()
      preGestureOffsetsRef.current = stagedOffsetsRef.current
      mouseDrag.onPointerDown(e)
    },
    [mouseDrag, stagedOffsetsRef],
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
      // Ctrl/Cmd-drag actor translation, drag-end (spec "Interaction design"): the existing tap-vs-
      // drag boundary this hook already has, not a second pointerup listener. `postStage` fires
      // exactly ONCE here, with the gesture's final computed position(s) -- never per pointer-move
      // frame (those only update local preview state, see dragCallbacks.onDrag above). A plain
      // Ctrl+click with no horizontal movement never set dragMovedRef, so this is a no-op then.
      if (dragMovedRef.current) {
        dragMovedRef.current = false
        const locations = stagedLocationsFor(stagedOffsetsRef.current, selectedNames)
        if (Object.keys(locations).length > 0) {
          postStage(level, locations)
            .then((result) => onStaged?.(result.staged))
            .catch((e2: unknown) => {
              // Important 3 (final review fix wave): a stage call CAN fail for real reasons (the
              // actor was deleted externally, a level switch mid-flight) -- revert exactly THIS
              // gesture's own displacement (an earlier, already-staged move survives) and surface
              // the failure the same way App.tsx already shows a Load/Rebuild failure.
              setStagedOffsets(preGestureOffsetsRef.current)
              stagedOffsetsRef.current = preGestureOffsetsRef.current
              onStageError?.(String(e2))
            })
        }
      }
      mouseDrag.onPointerUp(e)
    },
    [mouseDrag, performTapSelect, level, selectedNames, onStaged, stagedOffsetsRef, setStagedOffsets, onStageError],
  )

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
        <TouchFlyInput inputRef={touchFlyInput} setPose={setPose} />
        {/* All world content is reflected by R = diag(1,-1,1): the world is left-handed, and this is
            the handedness fix (viewportRender.ts's applyCameraPose reflects the camera pose by the
            same R). three.js compensates for the group's negative determinant -- winding (frontFace)
            and sprites both come out correct with no per-consumer patch. The camera rig/background
            stay OUTSIDE the group. */}
        <group scale={[1, -1, 1]}>
        {mode !== 'wireframe' && <mesh ref={meshRef} geometry={bufferGeometry} material={activeMaterials} />}
        {/* Movers: wireframe-outline-only by default in every mode (GUI.md "Movers") -- their solid
            geometry is split OUT of `bufferGeometry` above (SceneResourcesContext) and only drawn
            here when the "Movers: on" toggle is active, ADDITIONALLY on top of the outline (never
            replacing it -- `BrushOutlines` below still draws every Mover's ring unconditionally).
            `ref={moverMeshRef}` makes it a real click-to-select target (board item
            `mover-polys-unselectable-in-movers-on-mode`) -- without it a click here fell through to
            whatever solid geometry happened to sit behind the Mover, since this mesh wasn't part of
            `performTapSelect`'s raycast candidates at all. */}
        {mode !== 'wireframe' && showMoverSolid && (
          <mesh ref={moverMeshRef} geometry={moverGeometry} material={activeMoverMaterials} />
        )}
        {/* A selected WHOLE BRUSH is shown as a selected ACTOR (its bold, brightened outline ring +
            SelectionMarkers' vertex/pivot markers, both drawn below in every mode), NOT by lighting
            up its faces -- matching `actor diagram`/UED22 (owner ruling). The old additive-white
            per-face overlay for `selectedNames` is removed (it read as "all faces selected" and had
            no UED22 basis). Only a genuine SINGLE-face `selectedSurfaces` pick still lights one poly: */}
        {mode !== 'wireframe' && (
          <SurfaceSelectionHighlight
            bufferGeometry={bufferGeometry}
            triangleOwners={triangleOwners}
            trianglePolyIndex={trianglePolyIndex}
            selectedSurfaces={selectedSurfaces}
            materials={activeMaterials}
          />
        )}
        {/* Same surface-pick highlight, targeted at the Movers:on solid mesh's OWN geometry/owner
            arrays (board item `mover-poly-select-in-movers-on-mode-not`): the mover mesh above is a
            separate `THREE.BufferGeometry` from `bufferGeometry`, with its own `moverTriangleOwners`/
            `moverTrianglePolyIndex` -- a selected mover poly's (owner, polyIndex) pair never appears
            in the world mesh's arrays, so the instance above never builds a group for it. Gated
            identically to the mover mesh itself (`showMoverSolid`, plus wireframe's existing gate) so
            it only exists while that geometry is actually drawn. */}
        {mode !== 'wireframe' && showMoverSolid && (
          <SurfaceSelectionHighlight
            bufferGeometry={moverGeometry}
            triangleOwners={moverTriangleOwners}
            trianglePolyIndex={moverTrianglePolyIndex}
            selectedSurfaces={selectedSurfaces}
            materials={activeMoverMaterials}
          />
        )}
        {/* A selected mesh actor (never a brush) lights up in UED22's own measured color, not this
            codebase's white surface-pick overlay -- GUI-PARITY.md "Selection highlight rendering". */}
        {mode !== 'wireframe' && (
          <ActorSelectionHighlight
            bufferGeometry={bufferGeometry}
            triangleOwners={triangleOwners}
            selectedActorNames={selectedNonBrushNames}
            materials={activeMaterials}
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
            //
            // `depthTest={mode !== 'wireframe'}` (owner ruling): a marker is OCCLUDED behind geometry
            // in the solid shading modes (a torch icon behind a wall is hidden, UED22 parity), but in
            // wireframe mode -- where there's no solid mesh to occlude it -- it always shows.
            // `renderOrder={MARKER_RENDER_ORDER}` (see its doc comment above): draws after a
            // coincident-depth surface highlight regardless of the transparent-sort tiebreak.
            const spriteTex = actor.sprite ? textures.sprite.get(actor.sprite.tex_index) : undefined
            const isSelected = selectedNames.has(actor.name)
            // A staged (not-yet-saved) Ctrl/Cmd-drag move -- "confirmed staged" visual state until
            // Save/Discard (Task 10's own scope clears it). Only the marker position moves this way;
            // a brush/mesh actor's baked CSG geometry stays at its trunk position until a Rebuild
            // (see stagedOffsets's own doc comment above).
            const markerPosition = stagedOffsets[actor.name] ?? actor.location
            if (actor.sprite && spriteTex) {
              return (
                <PointActorMarker
                  key={actor.name}
                  position={markerPosition}
                  width={actor.sprite.width}
                  height={actor.sprite.height}
                  userData={{ actorName: actor.name }}
                  renderOrder={MARKER_RENDER_ORDER}
                >
                  <spriteMaterial
                    map={spriteTex}
                    color={isSelected ? SELECTED_SPRITE_TINT : UNSELECTED_SPRITE_TINT}
                    depthWrite={false}
                    depthTest={mode !== 'wireframe'}
                  />
                </PointActorMarker>
              )
            }
            if (!markerTexture) return null
            return (
              <PointActorMarker
                key={actor.name}
                position={markerPosition}
                width={DEFAULT_MARKER_FOOTPRINT_UU}
                height={DEFAULT_MARKER_FOOTPRINT_UU}
                userData={{ actorName: actor.name }}
                renderOrder={MARKER_RENDER_ORDER}
              >
                <spriteMaterial
                  map={markerTexture}
                  color={isSelected ? MARKER_COLOR_THREE.clone().multiply(SELECTED_SPRITE_TINT) : MARKER_COLOR_THREE}
                  depthWrite={false}
                  depthTest={mode !== 'wireframe'}
                />
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
          actors={effectiveActors}
          selectedNames={selectedNames}
          mode={mode === 'wireframe' ? 'csg-all' : 'selected-only'}
          groupRef={brushGroupRef}
          moverGroupRef={moverOutlineGroupRef}
        />
        {/* A mesh actor (never a brush -- no CSG ring above) renders its own triangle-edge wireframe
            here instead, matching a brush's wireframe convention in this mode (GUI.md "Shading
            modes"). Solid mesh rendering in every other mode is unaffected (unchanged, above). */}
        {mode === 'wireframe' && <MeshWireframe geometry={meshWireframeGeometry} />}
        {mode === 'wireframe' && (
          <SelectedMeshWireframe
            positions={meshPickGeometry.attributes.position.array as Float32Array}
            triangleOwners={meshTriangleOwners}
            selectedActorNames={selectedNonBrushNames}
          />
        )}
        {/* Invisible raycast target for mesh actors in SOLID modes -- material.visible=false draws
            nothing but keeps the object raycastable. See tapSelect.ts / SceneResourcesContext. */}
        <mesh ref={meshPickRef} geometry={meshPickGeometry}>
          <meshBasicMaterial visible={false} />
        </mesh>
        {/* Invisible raycast target for mesh actors' own wireframe EDGES -- used INSTEAD of the fill
            target above in wireframe mode only (tapSelect.ts gates which one is a raycast
            candidate); mounted unconditionally like the fill target. */}
        <lineSegments ref={meshEdgePickRef} geometry={meshEdgePickGeometry}>
          <lineBasicMaterial visible={false} />
        </lineSegments>
        {/* Vertex + pivot markers for a selected brush (bug report item 7). */}
        <SelectionMarkers actors={effectiveActors} selectedNames={selectedNames} />
        {/* Directional-facing arrow gizmo (bDirectional) -- always on, every pane, never behind
            the Radii toggle (GUI-PARITY.md "Directional arrow gizmo"). */}
        <DirectionalArrows actors={effectiveActors} selectedNames={selectedNames} />
        {/* Collision-cylinder / light-radius overlays, toggled globally but scoped to the current
            selection (owner ruling 2026-09-15) -- draws nothing when nothing is selected. */}
        {showRadii && <RadiiOverlays actors={effectiveActors} view="perspective" selectedNames={selectedNames} />}
        </group>
      </Canvas>
      {/* Touch-only virtual joystick + up/down buttons (board item
          mobile-3d-move-joystick-visual-design-pending) -- a plain DOM overlay, not 3D content, so
          it sits outside <Canvas> like the other per-pane overlays (QuadLayout.tsx's
          .quad-pane-label/.mode-selector); MoveJoystick itself renders nothing on a non-touch
          device. Bottom-left of this pane is the one corner none of QuadLayout's own overlays uses
          for the perspective pane (top-left = pane label, bottom-right = mode selector, top-right =
          the quad-wide toolbar) -- see index.css's .move-joystick-controls. */}
      <MoveJoystick onStickChange={onJoystickStickChange} onVerticalChange={onJoystickVerticalChange} />
    </div>
  )
}
