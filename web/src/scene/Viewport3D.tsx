// R3F perspective viewport: draws the scene payload's polys textured+lit, matching `level photo
// --native`'s render.rs. Each poly draws base-texture * shading with MeshBasicMaterial (still no
// scene lights): a lightmapped world surf multiplies by its baked lumel grid (the lightmap atlas,
// sampled through a second `uv1` set); every other poly multiplies by a per-face KEY_LIGHT flat
// shade carried in per-vertex colours (render.rs's own fallback for unlit surfs). Owns the
// faithful UnrealEd drag-fly camera (spec, "Camera") and click-to-select. This is the ONLY place
// model data meets three.js -- Viewport3D draws what `serve` hands it and owns no model/diff/solve
// logic of its own (spec, "The client").
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  MouseEvent as ReactMouseEvent,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, SceneActor, ScenePayload } from '../api'
import type { CameraPose, Vec3 } from './camera'
import { cameraBasis, dollyAndTurn, flyMove, look, orbit, pan, zoom } from './camera'
import type { GeometryGroup } from './geometry'
import { buildGeometryData } from './geometry'
import { actorsNeedingMarkers, MARKER_COLOR } from './markers'
import { isTap, pickActor, resolveHitActor } from './selection'
import type { Ray } from './selection'
import { computeTwoFingerDelta } from './touchGesture'
import type { TouchPoint } from './touchGesture'

const INITIAL_POSE: CameraPose = { position: [0, -500, 200], pitch: -10, yaw: 90 }

/** Extracts one `THREE.Texture` per atlas entry, keyed by `tex_index`, by drawing that entry's rect
 * out of the atlas image onto its own canvas -- so each texture can tile with RepeatWrapping (a
 * shared atlas can't repeat past a tile boundary; bug A). NearestFilter matches the low-res look;
 * `flipY=false` keeps the atlas's image-row UV convention (V grows downward). Every live-reload
 * swaps `atlas` and rebuilds the map, disposing the previous textures so nothing leaks; `currentRef`
 * tracks what's live for the unmount / lost-race cleanup too. */
function useTextures(atlas: AtlasPayload): Map<number, THREE.Texture> {
  const [textures, setTextures] = useState<Map<number, THREE.Texture>>(() => new Map())
  const currentRef = useRef<Map<number, THREE.Texture>>(new Map())

  useEffect(() => {
    let disposed = false
    const img = new Image()
    img.onload = () => {
      if (disposed) return
      const next = new Map<number, THREE.Texture>()
      for (const [key, rect] of Object.entries(atlas.manifest)) {
        const canvas = document.createElement('canvas')
        canvas.width = rect.w
        canvas.height = rect.h
        const ctx = canvas.getContext('2d')
        if (!ctx) continue
        ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h)
        const tex = new THREE.CanvasTexture(canvas)
        tex.wrapS = THREE.RepeatWrapping
        tex.wrapT = THREE.RepeatWrapping
        tex.magFilter = THREE.NearestFilter
        tex.minFilter = THREE.NearestFilter
        tex.flipY = false
        tex.needsUpdate = true
        next.set(Number(key), tex)
      }
      currentRef.current.forEach((t) => t.dispose())
      currentRef.current = next
      setTextures(next)
    }
    img.src = `data:image/png;base64,${atlas.png_base64}`
    return () => {
      disposed = true
    }
  }, [atlas.png_base64, atlas.manifest])

  useEffect(() => {
    return () => {
      currentRef.current.forEach((t) => t.dispose()) // unmount: release whatever's still held
      currentRef.current = new Map()
    }
  }, [])

  return textures
}

/** Decodes the lightmap atlas PNG into one `THREE.Texture` on `uv1` (channel 1, the second UV set
 * the geometry carries for lit polys). NearestFilter + ClampToEdge match render.rs's nearest,
 * edge-clamped lumel sampling (the atlas's 1-lumel gutter absorbs the clamp); `NoColorSpace` keeps
 * the stored multiplier linear (no sRGB decode); `flipY=false` matches the image-row V convention.
 * `null` (no lit polys) when the payload is absent or empty. Disposes on swap/unmount. */
function useLightmapTexture(lightmap: LightmapPayload | null): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  const currentRef = useRef<THREE.Texture | null>(null)

  useEffect(() => {
    if (!lightmap || Object.keys(lightmap.manifest).length === 0) {
      currentRef.current?.dispose()
      currentRef.current = null
      // Clear a stale texture when a level has (or loses) all its lights -- a genuine external-
      // system sync, not derivable during render.
      // oxlint-disable-next-line react/set-state-in-effect
      setTexture(null)
      return
    }
    let disposed = false
    const img = new Image()
    img.onload = () => {
      if (disposed) return
      const tex = new THREE.Texture(img)
      tex.channel = 1
      tex.wrapS = THREE.ClampToEdgeWrapping
      tex.wrapT = THREE.ClampToEdgeWrapping
      tex.magFilter = THREE.NearestFilter
      tex.minFilter = THREE.NearestFilter
      tex.colorSpace = THREE.NoColorSpace
      tex.flipY = false
      tex.needsUpdate = true
      currentRef.current?.dispose()
      currentRef.current = tex
      setTexture(tex)
    }
    img.src = `data:image/png;base64,${lightmap.png_base64}`
    return () => {
      disposed = true
    }
  }, [lightmap])

  useEffect(() => {
    return () => {
      currentRef.current?.dispose()
      currentRef.current = null
    }
  }, [])

  return texture
}

const UNTEXTURED_GREY = 0x808080

/** A soft white circular dot, drawn once and shared by every marker sprite (tinted per-class via
 * `SpriteMaterial.color`) -- one texture upload instead of one per marker. `THREE.Sprite` always
 * faces the camera on its own (no billboard math needed here), so this is the whole visual: a class-
 * coloured dot icon, matching UnrealEd's point-actor icon convention better than a solid cube. */
function useMarkerTexture(): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  const ref = useRef<THREE.Texture | null>(null)

  useEffect(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) return // e.g. a test/jsdom environment with no canvas 2D backend -- no marker texture
    const r = size / 2
    const gradient = ctx.createRadialGradient(r, r, 0, r, r, r)
    gradient.addColorStop(0, 'rgba(255,255,255,1)')
    gradient.addColorStop(0.7, 'rgba(255,255,255,1)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const tex = new THREE.CanvasTexture(canvas)
    tex.needsUpdate = true
    ref.current = tex
    setTexture(tex)
    return () => {
      tex.dispose()
      ref.current = null
    }
  }, [])

  return texture
}

/** The cull side + alpha-test + blend material state for a draw group, from its server-resolved
 * `masked`/`twoSided`/`blend` attrs alone (the map/lightMap are wired on separately). Single source
 * for the render-decision -> three.js mapping, unit-tested without a WebGL context.
 * - `twoSided` -> DoubleSide, else FrontSide (render.rs's backface cull; PF_TwoSided|PF_Portal exempt).
 * - `masked` -> alphaTest 0.5 against the texture's mask alpha (holes: fences, rotor).
 * - `translucent` -> half-opacity NormalBlending (see-through); `modulated` -> MultiplyBlending.
 *   Approximations of UE1's additive/modulate-2x, not pixel-exact (spec). */
export function resolveMaterialState(
  group: Pick<GeometryGroup, 'masked' | 'twoSided' | 'blend'>,
): Pick<THREE.MeshBasicMaterialParameters, 'side' | 'alphaTest' | 'transparent' | 'blending' | 'opacity'> {
  const state: ReturnType<typeof resolveMaterialState> = {
    side: group.twoSided ? THREE.DoubleSide : THREE.FrontSide,
    alphaTest: group.masked ? 0.5 : 0,
  }
  if (group.blend === 'translucent') {
    state.transparent = true
    state.blending = THREE.NormalBlending
    state.opacity = 0.5
  } else if (group.blend === 'modulated') {
    state.transparent = true
    state.blending = THREE.MultiplyBlending
  }
  return state
}

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

/** One brush poly ring, drawn as a closed line loop in the brush's own CSG colour. A tiny
 * standalone component (rather than inline JSX) so its `BufferGeometry` is built once per ring via
 * `useMemo`/disposed via `useEffect`, matching how `bufferGeometry`/textures are disposed elsewhere
 * in this file. */
function BrushRingOutline({ verts, color }: { verts: number[]; color: THREE.Color }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    return geo
  }, [verts])

  useEffect(() => {
    return () => geometry.dispose()
  }, [geometry])

  return (
    <lineLoop geometry={geometry}>
      <lineBasicMaterial color={color} linewidth={2} depthTest={false} />
    </lineLoop>
  )
}

/** Selection outline: a brush actor's own AUTHORED polys (pre-CSG, world-transformed server-side,
 * `SceneActor.brush`), drawn in its CSG-classified colour -- matching `actor diagram --mode wire
 * --highlight`, NOT the CSG-solved `ScenePayload.polys`. A non-brush actor (no `brush`, out of
 * scope for this task) falls back to the plain AABB box, same as before. */
function SelectionHighlight({ actor, box }: { actor: SceneActor | null; box: THREE.Box3 | null }) {
  const color = useMemo(() => {
    const rgb = actor?.brush?.color
    return rgb ? new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255) : null
  }, [actor])

  if (!actor) return null
  if (!actor.brush || !color) return box ? <box3Helper args={[box, SELECTION_BOX_COLOR]} /> : null

  return (
    <group>
      {actor.brush.polys.map((verts, i) => (
        <BrushRingOutline key={i} verts={verts} color={color} />
      ))}
    </group>
  )
}

export interface Viewport3DProps {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedName?: string | null
  onSelectActor?: (name: string | null) => void
}

interface DragTracker {
  // Accumulated movement since pointerdown, in screen pixels -- NOT a start/current position pair.
  // Pointer-lock (below) freezes `clientX`/`clientY` at wherever the cursor was when the lock
  // engaged, so distance can only be measured by summing each move event's `movementX`/`movementY`.
  totalDx: number
  totalDy: number
}

// Which single touch contact is the tap-selection candidate: the FIRST finger down, tracked only
// while it stays the only contact. A second finger touching down invalidates it (the gesture is a
// two-finger pan/pinch, never a tap) -- see onPointerDown/onPointerUp below.
interface TouchTapTracker {
  pointerId: number
  totalDx: number
  totalDy: number
}

export function Viewport3D({ scene, atlas, lightmap, selectedName = null, onSelectActor }: Viewport3DProps) {
  const [pose, setPose] = useState<CameraPose>(INITIAL_POSE)
  const drag = useRef<DragTracker | null>(null)
  // Live screen position of every currently-down touch contact, by `pointerId` -- lets multi-touch
  // gestures (unlike `drag`, which assumes exactly one contact) compute each finger's own delta and
  // tell 1-finger from 2-finger gestures apart. Mouse/pen input never touches this map (gated on
  // `e.pointerType === 'touch'` below) so desktop behavior is unchanged.
  const touchPoints = useRef<Map<number, TouchPoint>>(new Map())
  const touchTap = useRef<TouchTapTracker | null>(null)
  const cameraRef = useRef<THREE.Camera | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const markerGroupRef = useRef<THREE.Group | null>(null)
  const textures = useTextures(atlas)
  const lightmapTexture = useLightmapTexture(lightmap)
  const markerTexture = useMarkerTexture()

  const selectedActor = useMemo(
    () => scene.actors.find((a) => a.name === selectedName) ?? null,
    [scene.actors, selectedName],
  )

  const orbitPivot: Vec3 = useMemo(() => {
    if (!selectedActor) return [0, 0, 0]
    return [
      (selectedActor.bbox_lo[0] + selectedActor.bbox_hi[0]) / 2,
      (selectedActor.bbox_lo[1] + selectedActor.bbox_hi[1]) / 2,
      (selectedActor.bbox_lo[2] + selectedActor.bbox_hi[2]) / 2,
    ]
  }, [selectedActor])

  const selectionBox = useMemo(() => {
    if (!selectedActor) return null
    return new THREE.Box3(
      new THREE.Vector3(...selectedActor.bbox_lo),
      new THREE.Vector3(...selectedActor.bbox_hi),
    )
  }, [selectedActor])

  // One draw group per (texture, masked?, two_sided?, blend, lit?) tuple, each with its own
  // material set from the server-resolved attrs (cull side, alphaTest, blend). The base map tiles
  // on `uv`; per-vertex `color` carries the KEY_LIGHT flat shade (unlit) or white (lit); a lit
  // group additionally samples the shared lightmap texture on `uv1` (`base*color*lightMap`, the
  // render.rs product). Untextured groups (tex_index < 0) get a flat grey base. Built together so
  // the geometry's group -> material-index mapping stays consistent.
  const { bufferGeometry, materials, triangleOwners } = useMemo(() => {
    const built = buildGeometryData(scene.polys, atlas, lightmap)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(built.positions, 3))
    geo.setAttribute('uv', new THREE.BufferAttribute(built.uvs, 2))
    geo.setAttribute('uv1', new THREE.BufferAttribute(built.uv1, 2))
    geo.setAttribute('color', new THREE.BufferAttribute(built.colors, 3))
    geo.clearGroups()
    const mats: THREE.Material[] = []
    const matIndex = new Map<string, number>()
    const intensity = lightmap?.intensity ?? 1
    for (const group of built.groups) {
      if (group.count === 0) continue
      const lit = group.lit && lightmapTexture !== null
      const key = `${group.texIndex}:${group.masked ? 1 : 0}:${group.twoSided ? 1 : 0}:${group.blend}:${lit ? 1 : 0}`
      let index = matIndex.get(key)
      if (index === undefined) {
        const map = group.texIndex >= 0 ? (textures.get(group.texIndex) ?? null) : null
        const params: THREE.MeshBasicMaterialParameters = {
          vertexColors: true,
          ...resolveMaterialState(group), // cull side + alphaTest + blend, from the resolved attrs
        }
        if (map) params.map = map
        else params.color = UNTEXTURED_GREY
        if (lit) {
          params.lightMap = lightmapTexture
          params.lightMapIntensity = intensity
        }
        index = mats.length
        mats.push(new THREE.MeshBasicMaterial(params))
        matIndex.set(key, index)
      }
      geo.addGroup(group.start, group.count, index)
    }
    geo.computeVertexNormals()
    return { bufferGeometry: geo, materials: mats, triangleOwners: built.triangleOwners }
  }, [scene, atlas, lightmap, textures, lightmapTexture])

  // Every live-reload replaces `bufferGeometry`/`materials` with fresh THREE objects; without an
  // explicit dispose the PREVIOUS ones (a full geometry buffer, its materials) leak every cycle.
  // The cleanup closes over the value from the render it belongs to, so it always disposes the one
  // being REPLACED, and disposes the final one on unmount too.
  useEffect(() => {
    return () => {
      bufferGeometry.dispose()
      materials.forEach((m) => m.dispose())
    }
  }, [bufferGeometry, materials])

  // Markers for pure point actors (no brush, no owned/rendered poly -- lights, triggers, patrol
  // nodes, sounds, or a DT_Mesh actor whose mesh never resolved): one billboard `THREE.Sprite` each,
  // always facing the camera -- the actor's real `DT_Sprite` icon texture (`actor.sprite`) when it
  // resolved, else the generic grey dot (`MARKER_COLOR`). Each sprite carries its actor's name
  // directly in `userData` -- unlike the main mesh (one merged BufferGeometry, so a raycast hit
  // needs `triangleOwners`+`faceIndex` to find its actor), a Sprite IS its own pickable object, so
  // `hit.object.userData.actorName` resolves it with no indirection.
  const markerActors = useMemo(() => {
    const ownedNames = new Set(triangleOwners.filter((n): n is string => n != null))
    return actorsNeedingMarkers(scene.actors, ownedNames)
  }, [scene, triangleOwners])

  // Shared by both the mouse tap path and the touch tap path: raycasts the click/tap point against
  // the drawn geometry (see the comment below for the primary/fallback strategy) and reports the
  // hit actor. Split out so onPointerUp's touch branch can call the exact same selection logic as
  // the existing mouse branch, instead of a second copy.
  const performTapSelect = useCallback(
    (clientX: number, clientY: number) => {
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
      onSelectActor?.(hitActor ? hitActor.name : null)
    },
    [scene.actors, triangleOwners, onSelectActor],
  )

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    if (e.pointerType === 'touch') {
      const isFirstContact = touchPoints.current.size === 0
      touchPoints.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
      // Only the FIRST finger down is a tap candidate; a second finger arriving before the first
      // lifts means this is a two-finger gesture, never a tap (see onPointerUp).
      touchTap.current = isFirstContact ? { pointerId: e.pointerId, totalDx: 0, totalDy: 0 } : null
      return
    }
    drag.current = { totalDx: 0, totalDy: 0 }
    // Pointer lock is requested lazily, on the first real MOVEMENT of a drag (see onPointerMove),
    // not here on plain pointerdown -- a tap that never moves (a selection click) never locks at
    // all, so the cursor stays visible and the browser's "has control of your pointer" banner never
    // fires for a plain click. It only shows for an actual drag, and only once per drag (locked for
    // that drag's duration, released in onPointerUp). Not applicable to touch at all -- there's no
    // OS cursor to hide, so touch never reaches this branch.
  }, [])

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

      const d = drag.current
      if (!d) return
      const dx = e.movementX
      const dy = e.movementY
      if (d.totalDx === 0 && d.totalDy === 0 && (dx !== 0 || dy !== 0) && !document.pointerLockElement) {
        // First real movement of this drag: lock now (hides the cursor for the rest of the drag,
        // with no screen-edge clamp on movementX/Y). Browsers can deny a request right after a
        // recent exit, which just falls back to the ordinary cursor for that one gesture --
        // movementX/Y still work unlocked too.
        e.currentTarget.requestPointerLock?.()
      }
      d.totalDx += dx
      d.totalDy += dy
      if (dx === 0 && dy === 0) return
      const buttons = e.buttons
      setPose((prev) => {
        if (e.altKey && (buttons & 1) !== 0) return orbit(prev, orbitPivot, dx, dy)
        if ((buttons & 1) !== 0 && (buttons & 2) !== 0) return pan(prev, dx, dy)
        if ((buttons & 2) !== 0) return look(prev, dx, dy)
        if ((buttons & 1) !== 0) return dollyAndTurn(prev, dx, dy)
        return prev
      })
    },
    [orbitPivot],
  )

  const onPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      e.currentTarget.releasePointerCapture(e.pointerId)
      if (e.pointerType === 'touch') {
        touchPoints.current.delete(e.pointerId)
        const tap = touchTap.current
        if (tap?.pointerId !== e.pointerId) return // not the tap-candidate finger (or none survived)
        touchTap.current = null
        if (isTap(0, 0, tap.totalDx, tap.totalDy)) performTapSelect(e.clientX, e.clientY)
        return
      }
      document.exitPointerLock?.()
      const d = drag.current
      drag.current = null
      if (!d || e.button !== 0 || e.altKey) return
      if (!isTap(0, 0, d.totalDx, d.totalDy)) return // a real drag, not a selection tap
      performTapSelect(e.clientX, e.clientY)
    },
    [performTapSelect],
  )

  const onWheel = useCallback((e: ReactWheelEvent<HTMLDivElement>) => {
    setPose((prev) => zoom(prev, e.deltaY))
  }, [])

  const onContextMenu = useCallback((e: ReactMouseEvent<HTMLDivElement>) => e.preventDefault(), [])

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
      <Canvas flat camera={{ fov: 75, near: 1, far: 131072 }}>
        <CameraRig pose={pose} cameraRef={cameraRef} />
        <FlyKeys setPose={setPose} />
        <mesh ref={meshRef} geometry={bufferGeometry} material={materials} />
        <group ref={markerGroupRef}>
          {markerActors.map((actor) => {
            // A resolved DT_Sprite billboard draws the actor's REAL class icon texture (its atlas
            // rect, cropped by `useTextures` above) at its own world-space footprint, untinted --
            // the actual sprite's colours, not a class-coloured guess. Falls back to the generic
            // grey dot (`markerTexture`/`MARKER_COLOR_THREE`) when there's no sprite, or the atlas
            // texture for it isn't in `textures` yet (e.g. mid-load).
            const spriteTex = actor.sprite ? textures.get(actor.sprite.tex_index) : undefined
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
        <SelectionHighlight actor={selectedActor} box={selectionBox} />
      </Canvas>
    </div>
  )
}
