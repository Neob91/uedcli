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
import type { ShadingMode } from './shadingMode'
import { useSceneResourcesContext } from './SceneResourcesContext'
import { isTap, pickActor, resolveHitActor, resolveTapSelection } from './selection'
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

/** Applies `pose` to the R3F default camera every frame -- Z-up (`camera.up`), aimed via
 * `lookAt` rather than a manual quaternion (keeps roll disambiguation simple and correct for a
 * Z-up world with no roll of its own). Also publishes the live camera object to `cameraRef` so
 * the outer (non-R3F) pointer handlers can raycast through it for click-to-select. */
function CameraRig({ pose, cameraRef }: { pose: CameraPose; cameraRef: MutableRefObject<THREE.Camera | null> }) {
  const { camera } = useThree()
  useEffect(() => {
    cameraRef.current = camera
  }, [camera, cameraRef])
  useFrame(() => {
    camera.up.set(0, 0, 1)
    camera.position.set(pose.position[0], pose.position[1], pose.position[2])
    const { forward } = cameraBasis(pose.pitch, pose.yaw)
    camera.lookAt(
      pose.position[0] + forward[0],
      pose.position[1] + forward[1],
      pose.position[2] + forward[2],
    )
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
  // `F`-frame (Part 3, Task 15): a new (higher `seq`) request retargets the camera to fit `bbox`,
  // keeping the current viewing angle (pitch/yaw) and backing the position off far enough along it.
  frameRequest?: FrameRequest | null
  // Per-pane shading mode (Part 4, Task 20): 'wireframe' draws ONLY the CSG-colored brush rings (no
  // solid mesh); 'unlit'/'flat'/'lit' draw the existing solid mesh -- 'flat' renders identically to
  // 'unlit' for now (the main spec's own "Also open": its exact definition isn't pinned down yet).
  mode?: ShadingMode
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
  frameRequest = null,
  mode = 'lit',
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
  // Geometry/textures/markers are built ONCE and shared across every pane via
  // SceneResourcesContext (Part 0, Tasks 1-2) -- Viewport3D no longer builds its own (Task 3;
  // camera/pointer handling/click-to-select are UNCHANGED in this task).
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors } =
    useSceneResourcesContext()
  // 'unlit'/'lit' otherwise rendered the identical mesh (materials built once, shared across every
  // pane, with no per-mode variant) -- pick the lightmap-free array for 'unlit' so it genuinely
  // differs, matching the main spec's 4-distinct-shading-modes requirement (review finding).
  const activeMaterials = mode === 'unlit' ? unlitMaterials : materials

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
    (clientX: number, clientY: number, additive: boolean) => {
      const camera = cameraRef.current
      const rect = containerRef.current?.getBoundingClientRect()
      if (!camera || !rect) return
      const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)

      // PRIMARY: raycast the real drawn geometry (main scene mesh + point-actor marker sprites)
      // together, so the nearest hit wins regardless of which one it lands on. The main mesh
      // resolves via its per-triangle `triangleOwners` (real per-poly ownership, `ScenePoly.owner`);
      // a marker sprite resolves directly via its own `userData.actorName` (it IS one pickable
      // object, no per-triangle indirection needed). This is what lets a small brush fully enclosed
      // in a bigger brush's AABB, or a light/trigger/patrol point with no geometry of its own, be
      // selected by its OWN rendered shape. FALLBACK: ray-vs-AABB (`pickActor`) for a tap that lands
      // on neither -- e.g. an out-of-range CSG join.
      let hitActor: SceneActor | null = null
      const candidates: THREE.Object3D[] = [
        ...(meshRef.current ? [meshRef.current] : []),
        ...(markerGroupRef.current?.children ?? []),
      ]
      if (candidates.length > 0) {
        const hits = raycaster.intersectObjects(candidates, false)
        if (hits.length > 0) {
          const hit = hits[0]
          if (hit.object === meshRef.current) {
            hitActor = resolveHitActor(hit.faceIndex, triangleOwners, scene.actors)
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
        hitActor = pickActor(ray, scene.actors)
      }
      const result = resolveTapSelection(hitActor, additive)
      if (result) onSelectActor(result.name, result.additive)
    },
    [scene.actors, triangleOwners, onSelectActor],
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
      onTap: (clientX, clientY, additive) => performTapSelect(clientX, clientY, additive),
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
        if (isTap(0, 0, tap.totalDx, tap.totalDy)) performTapSelect(e.clientX, e.clientY, false) // touch has no Ctrl-equivalent
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
        <CameraRig pose={pose} cameraRef={cameraRef} />
        <FlyKeys setPose={setPose} />
        {mode !== 'wireframe' && <mesh ref={meshRef} geometry={bufferGeometry} material={activeMaterials} />}
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
        <BrushOutlines actors={scene.actors} selectedNames={selectedNames} mode={mode === 'wireframe' ? 'csg-all' : 'selected-only'} />
        {/* Every selected NON-brush actor (no CSG ring to draw) falls back to its own plain AABB
            box -- one per selected actor (Task 14), not just a single one. */}
        {selectedNonBrushBoxes.map(({ name, box }) => (
          <box3Helper key={name} args={[box, SELECTION_BOX_COLOR]} />
        ))}
      </Canvas>
    </div>
  )
}
