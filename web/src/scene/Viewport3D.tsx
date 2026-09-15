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

import type { AtlasPayload, LightmapPayload, SceneActor, ScenePayload } from '../api'
import { BrushOutlines } from './BrushOutlines'
import type { CameraPose, Vec3 } from './camera'
import { cameraBasis, dollyAndTurn, flyMove, look, orbit, pan, zoom } from './camera'
import type { DragGestureCallbacks } from './dragGesture'
import { useDragGesture } from './dragGesture'
import type { FrameRequest } from './frame'
import { bboxCenter, bboxMaxExtent } from './frame'
import { MARKER_COLOR } from './markers'
import { RadiiOverlays } from './RadiiOverlays'
import { SelectionHighlight } from './SelectionHighlight'
import { SelectionMarkers } from './SelectionMarkers'
import type { ShadingMode } from './shadingMode'
import { usesUnlitMaterials } from './shadingMode'
import { useSceneResourcesContext } from './SceneResourcesContext'
import {
  canSelectBrushTap,
  isTap,
  pickActor,
  resolveHitActor,
  resolveSegmentHitActor,
  resolveTapAction,
} from './selection'
import type { Ray } from './selection'
import { computeTwoFingerDelta } from './touchGesture'
import type { TouchPoint } from './touchGesture'

// Re-exported so existing call sites (e.g. material.test.ts) keep importing it from here --
// the implementation moved to sceneResources.ts (quad-layout Part 0, Task 1).
export { resolveMaterialState } from './sceneResources'

const INITIAL_POSE: CameraPose = { position: [0, -500, 200], pitch: -10, yaw: 90 }

/** `render.rs` (this viewport's parity target, per the file header) shades by multiplying raw
 * 0-255 texel bytes directly by a flat/lightmap scalar -- no sRGB decode of the texture, no
 * re-encode of the result (`(rr * shade).clamp(0.0, 255.0)`). R3F's `<Canvas>` defaults do NOT
 * match that: with neither `linear` nor `legacy` set, it still applies a linear-to-sRGB ENCODE at
 * output (`gl.outputColorSpace = THREE.SRGBColorSpace`) even though nothing on the way in ever
 * decodes (every texture here defaults to `THREE.NoColorSpace` -- see `sceneResources.ts`'s
 * `useTextures`/`useMarkerTexture`), and `ColorManagement` auto-decodes hex/`THREE.Color` literals
 * (`UNTEXTURED_GREY`, `SELECTION_BOX_COLOR` -- constructed via `new THREE.Color(hex)`) as sRGB on
 * construction. (`MARKER_COLOR_THREE` below is built via `setRGB(r,g,b)` instead, whose default
 * `colorSpace` is already the working linear space -- its on-screen correction comes entirely
 * from the output-encode half, not from `legacy`.) A decode-less-but-still-encoded pipeline does
 * not merely dim a FEW things -- traced against three's own `LinearToSRGB`/`SRGBToLinear`
 * (`ColorManagement.js`), it brightens EVERY texel (0.5 renders as ~0.735) and darkens every
 * auto-decoded hex literal, in both cases moving away from the exact source value. `flat` (no
 * tone mapping, already present) doesn't touch either effect. `linear` (`outputColorSpace =
 * LinearSRGBColorSpace`, skips the output encode) + `legacy` (`ColorManagement.enabled = false`,
 * skips the hex-literal auto-decode) together make the whole pipeline a pure passthrough --
 * matching render.rs's zero-color-management model, and the invariant that a fullbright sprite
 * (no vertex color, no lightmap, default-white material) must display its exact source pixel.
 *
 * IMPORTANT: `ColorManagement.enabled` is a process-wide singleton, not per-`<Canvas>` -- r3f's
 * `configure()` sets it unconditionally on EVERY render of every mounted Canvas. Any sibling
 * `<Canvas>` in the app (e.g. an ortho pane) that doesn't also spread `CANVAS_COLOR_MANAGEMENT`
 * will flip this flag back on its own next render, silently undoing this fix here too -- every
 * `<Canvas>` in this app MUST spread the same `CANVAS_COLOR_MANAGEMENT` constant (OrthoViewport.tsx
 * does, quad-layout Part 8). */
export const CANVAS_COLOR_MANAGEMENT = { flat: true, linear: true, legacy: true } as const

/** Applies `pose` to a `THREE.PerspectiveCamera` -- Z-up (`camera.up`), aimed via `lookAt` (a
 * proper, always-valid rotation -- keeps roll disambiguation simple for a Z-up world with no roll
 * of its own), THEN mirrors the projection horizontally (`projectionMatrix`'s NDC-x scale term
 * negated). The world is left-handed (X forward, Y right, Z up) but its raw coordinates feed
 * three.js's right-handed renderer verbatim (`geometry.ts` applies no axis flip), so a plain
 * (proper-rotation) camera necessarily renders this world's `right` on the wrong screen side --
 * confirmed live: a world-space arrow pointing toward +Y (`cameraBasis.right`) rendered on the LEFT
 * of this pane, matching the reported "meshes render reverted (mirror image)" bug, and matching a
 * fresh `level photo --native` (render.rs, this pane's own calibration target) of the identical
 * camera pose, which renders the SAME arrow on the RIGHT.
 *
 * This mirror has to happen at the PROJECTION step, not the view/rotation step: the "obvious"
 * alternative -- build the camera's local axes directly from `(right, up, -forward)` via
 * `Matrix4.makeBasis` (matching `OrthoViewport.tsx`'s `OrthoCameraRig`) -- produces an IMPROPER
 * matrix (determinant -1: `cross(right, up) == forward`, not `-forward`, a direct consequence of
 * the world being left-handed), and an improper matrix breaks BOTH obvious ways to apply it: (1)
 * `camera.quaternion.setFromRotationMatrix` assumes a proper rotation and silently produces a
 * camera looking in a WRONG direction (confirmed live: intended look direction `[1,0,0]`, actual
 * `[0,-1,0]`) -- not merely mirrored, pointed somewhere else entirely, so the scene vanishes at most
 * poses; (2) writing `camera.matrix`/`matrixWorld` directly (bypassing quaternion) DOES look the
 * right way and DOES carry the intended `right`/`up`/`forward` (confirmed live via
 * `transformDirection`), yet still projects every point through the mirror (confirmed live via
 * `Vector3.project`) -- an improper view matrix mirrors the render regardless of how "correct" its
 * individual axis vectors look, because a determinant-(-1) transform IS a reflection, full stop.
 * Negating the projection matrix's NDC-x term instead keeps the view/rotation step fully proper
 * (three.js's own well-tested `lookAt`, no custom matrix plumbing) and applies the one needed
 * mirror at a single, well-understood, easily-inverted spot.
 *
 * `projectionMatrixInverse` is kept in sync (the same element, negated the same way) because
 * `THREE.Raycaster.setFromCamera` (click-to-select, `performTapSelect` below) unprojects screen
 * points through it -- left stale, clicks would target the PRE-mirror screen position.
 *
 * Pure THREE.js math -- no WebGL context needed, so it's unit-tested directly (`Viewport3D.test.ts`)
 * without mounting a `<Canvas>`. */
export function applyCameraPose(camera: THREE.PerspectiveCamera, pose: CameraPose): void {
  camera.up.set(0, 0, 1)
  camera.position.set(pose.position[0], pose.position[1], pose.position[2])
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  camera.lookAt(
    pose.position[0] + forward[0],
    pose.position[1] + forward[1],
    pose.position[2] + forward[2],
  )
  camera.updateMatrixWorld(true) // r3f does this too before rendering; explicit here so this
  // function is self-contained for direct (non-r3f) callers, e.g. Viewport3D.test.ts's
  // Vector3.project(camera), which reads matrixWorldInverse without updating it itself.
  camera.updateProjectionMatrix()
  camera.projectionMatrix.elements[0] *= -1
  camera.projectionMatrixInverse.elements[0] *= -1
}

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
    const k = held.current
    if (k.size === 0) return
    const forward = (k.has('KeyW') ? 1 : 0) - (k.has('KeyS') ? 1 : 0)
    const right = (k.has('KeyA') ? 1 : 0) - (k.has('KeyD') ? 1 : 0)
    const up = (k.has('KeyE') ? 1 : 0) - (k.has('KeyQ') ? 1 : 0)
    if (forward === 0 && right === 0 && up === 0) return
    setPose((prev) => flyMove(prev, { forward, right, up }, FLY_SPEED_UU_PER_SEC, delta))
  })

  return null
}

const SELECTION_BOX_COLOR = 0x00e5ff

// A room/brush is typically tens-to-hundreds of UU across; 24 UU is visible without dwarfing small
// geometry it sits next to. Used only for the fallback dot marker -- a resolved sprite (below) uses
// its own real, texture-derived world footprint instead.
const MARKER_SIZE = 24

// `THREE.Color` reads 0..1 components -- built once from `markers.MARKER_COLOR` (module-scope: a
// plain data object, no WebGL context needed).
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)

export interface Viewport3DProps {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
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
  // mirroring the existing grid-toggle convention; default off (radii clutter a level fast).
  showRadii?: boolean
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
  onDeselect,
  frameRequest = null,
  mode = 'lit',
  showRadii = false,
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
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors } =
    useSceneResourcesContext()
  // 'unlit'/'lit' otherwise rendered the identical mesh (materials built once, shared across every
  // pane, with no per-mode variant) -- pick the lightmap-free array for 'unlit' so it genuinely
  // differs, matching the main spec's 4-distinct-shading-modes requirement (review finding).
  const activeMaterials = usesUnlitMaterials(mode) ? unlitMaterials : materials

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
  const selectedNonBrushBoxes = useMemo(() => {
    return scene.actors
      .filter((a) => selectedNames.has(a.name) && !a.brush)
      .map((a) => ({ name: a.name, box: new THREE.Box3(new THREE.Vector3(...a.bbox_lo), new THREE.Vector3(...a.bbox_hi)) }))
  }, [scene.actors, selectedNames])

  // Shared by both the mouse tap path and the touch tap path: raycasts the click/tap point against
  // the drawn geometry (see the comment below for the primary/fallback strategy) and reports the
  // hit actor. Split out so onPointerUp's touch branch can call the exact same selection logic as
  // the existing mouse branch, instead of a second copy.
  const performTapSelect = useCallback(
    (clientX: number, clientY: number, additive: boolean, shiftKey: boolean) => {
      const camera = cameraRef.current
      const rect = containerRef.current?.getBoundingClientRect()
      if (!camera || !rect) return
      const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)
      // Wireframe mode draws no solid mesh -- a click must land near a brush's own outline LINE
      // (bug report item 6: UED22 never lets a click anywhere inside a brush's silhouette select
      // it in wireframe/ortho views). `Line`/`LineLoop` (ThinRing) measure this threshold in WORLD
      // units; `Line2` (BoldRing, the selected ring) measures it in screen PIXELS -- both need
      // setting, or an unset one falls back to a threshold of 0 (line-exact clicks only).
      raycaster.params.Line = { threshold: 4 }
      raycaster.params.Line2 = { threshold: 6 }

      // PRIMARY: raycast the real drawn geometry (main scene mesh + point-actor marker sprites +,
      // in wireframe mode, the brush outline lines) together, so the nearest hit wins regardless of
      // which one it lands on. The main mesh resolves via its per-triangle `triangleOwners` (real
      // per-poly ownership, `ScenePoly.owner`); a marker sprite or outline ring resolves directly via
      // its own `userData.actorName` (each IS one pickable object, no per-triangle indirection
      // needed). This is what lets a small brush fully enclosed in a bigger brush's AABB, or a
      // light/trigger/patrol point with no geometry of its own, be selected by its OWN rendered
      // shape. FALLBACK: ray-vs-AABB (`pickActor`) for a tap that lands on neither -- e.g. an
      // out-of-range CSG join -- but NEVER for a brush actor in wireframe mode, where only its own
      // outline lines (just raycast above) may select it, per item 6.
      let hitActor: SceneActor | null = null
      const candidates: THREE.Object3D[] = [
        ...(meshRef.current ? [meshRef.current] : []),
        ...(markerGroupRef.current?.children ?? []),
        ...(mode === 'wireframe' ? (brushGroupRef.current?.children ?? []) : []),
      ]
      if (candidates.length > 0) {
        const hits = raycaster.intersectObjects(candidates, false)
        if (hits.length > 0) {
          const hit = hits[0]
          if (hit.object === meshRef.current) {
            hitActor = resolveHitActor(hit.faceIndex, triangleOwners, scene.actors)
          } else if (hit.object.userData.segmentOwners) {
            const segmentOwners = hit.object.userData.segmentOwners as (string | null)[]
            hitActor = resolveSegmentHitActor(hit.index, segmentOwners, scene.actors)
          } else {
            const name = hit.object.userData.actorName as string | undefined
            hitActor = name ? (scene.actors.find((a) => a.name === name) ?? null) : null
          }
        }
      }
      if (!hitActor) {
        const ray: Ray = {
          origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
          direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
        }
        const aabbCandidates = mode === 'wireframe' ? scene.actors.filter((a) => !a.brush) : scene.actors
        hitActor = pickActor(ray, aabbCandidates)
      }
      // Capture the raw hit-test result BEFORE the Shift gate below -- `resolveTapAction` needs both
      // (a click that actually landed on a brush, just rejected for lack of Shift, must leave the
      // current selection alone; only a tap that hit NOTHING at all deselects).
      const rawHit = hitActor
      // Wireframe mode: plain tap selects a brush directly. Non-wireframe (unlit/flat/lit): plain
      // LMB-drag is camera-fly (dolly+turn), so a brush hit needs Shift held to disambiguate a
      // selection tap from that (`selection.ts`'s `canSelectBrushTap`). A point-actor hit is
      // unaffected either way.
      if (hitActor?.brush && !canSelectBrushTap(mode, shiftKey)) hitActor = null
      const action = resolveTapAction(rawHit, hitActor, additive)
      if (action.kind === 'select') onSelectActor(action.name, action.additive)
      else if (action.kind === 'deselect') onDeselect()
    },
    [scene.actors, triangleOwners, onSelectActor, onDeselect, mode],
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
        {/* Issue 1: a selected brush's surface "lights up" (additive brightness boost), same as the
            2D ortho panes below -- no surface to light up in wireframe mode (no solid mesh above). */}
        {mode !== 'wireframe' && (
          <SelectionHighlight bufferGeometry={bufferGeometry} triangleOwners={triangleOwners} selectedNames={selectedNames} />
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
                <sprite
                  key={actor.name}
                  position={actor.location}
                  scale={[actor.sprite.width, actor.sprite.height, 1]}
                  userData={{ actorName: actor.name }}
                >
                  <spriteMaterial map={spriteTex} depthWrite={false} />
                </sprite>
              )
            }
            if (!markerTexture) return null
            return (
              <sprite
                key={actor.name}
                position={actor.location}
                scale={[MARKER_SIZE, MARKER_SIZE, 1]}
                userData={{ actorName: actor.name }}
              >
                <spriteMaterial map={markerTexture} color={MARKER_COLOR_THREE} depthWrite={false} />
              </sprite>
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
        {/* Vertex + pivot markers for a selected brush (bug report item 7). */}
        <SelectionMarkers actors={scene.actors} selectedNames={selectedNames} />
        {/* Collision-cylinder / light-radius overlays, toggled globally (not by selection). */}
        {showRadii && <RadiiOverlays actors={scene.actors} view="perspective" />}
        {/* Every selected NON-brush actor (no CSG ring to draw) falls back to its own plain AABB
            box -- one per selected actor (Task 14), not just a single one. */}
        {selectedNonBrushBoxes.map(({ name, box }) => (
          <box3Helper key={name} args={[box, SELECTION_BOX_COLOR]} />
        ))}
      </Canvas>
    </div>
  )
}
