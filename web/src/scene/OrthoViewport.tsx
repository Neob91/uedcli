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

import type { SceneActor } from '../api'
import type { Vec3 } from './camera'
import { BrushOutlines } from './BrushOutlines'
import { useDragGesture } from './dragGesture'
import type { DragGestureCallbacks } from './dragGesture'
import type { FrameRequest } from './frame'
import { bboxCenter } from './frame'
import { GridOverlay } from './GridOverlay'
import { MARKER_COLOR } from './markers'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { orthoBasis, orthoPan, orthoZoom, screenToWorld } from './orthoCamera'
import { useSceneResourcesContext } from './SceneResourcesContext'
import { SelectionMarkers } from './SelectionMarkers'
import { pickActor, resolveHitActor, resolveSegmentHitActor, resolveTapSelection } from './selection'
import type { Ray } from './selection'
import type { ShadingMode } from './shadingMode'
// `THREE.ColorManagement.enabled` is a process-wide singleton r3f reasserts on every render of
// EVERY mounted Canvas (Viewport3D.tsx's own `CANVAS_COLOR_MANAGEMENT` doc comment) -- this pane's
// Canvas MUST spread the identical constant, or the two fight over that global flag on every
// shared re-render (constant in the quad layout), silently breaking Viewport3D's fix too.
import { CANVAS_COLOR_MANAGEMENT } from './Viewport3D'

// Far enough to enclose a whole UE1 level (+/-32768 UU) from any starting center -- matches
// Viewport3D's far=131072 reasoning.
const ORTHO_HALF_RANGE = 65536
const INITIAL_WORLD_UNITS_PER_PIXEL = 4

// Same fallback dot size/tint as Viewport3D's identical marker rendering -- a room/brush is
// typically tens-to-hundreds of UU across, so 24 UU reads clearly without dwarfing nearby geometry.
const MARKER_SIZE = 24
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)

export function initialOrthoPose(): OrthoPose {
  return { center: [0, 0, 0], worldUnitsPerPixel: INITIAL_WORLD_UNITS_PER_PIXEL }
}

// Scratch objects for OrthoCameraRig's basis matrix (module-scope: avoid allocating every frame).
const _xAxis = new THREE.Vector3()
const _yAxis = new THREE.Vector3()
const _zAxis = new THREE.Vector3()
const _basis = new THREE.Matrix4()

/** Applies `pose`/`axis` to the R3F default (orthographic) camera every frame: axis-locked
 * position/orientation (looking along `orthoBasis(axis).forward` through `pose.center`), and a
 * frustum sized from `worldUnitsPerPixel` × the container's own pixel size so the pane's on-screen
 * scale matches `pose` exactly regardless of the pane's CSS size. Publishes the live camera object
 * to `cameraRef` for the outer pointer handlers' raycast.
 *
 * Orientation is built directly from `orthoBasis`'s (right, up, forward) via `Matrix4.makeBasis`,
 * NOT `camera.up` + `lookAt` -- three.js's `lookAt` derives local +X (screen-right) as
 * `cross(up, eye-target)`, which for every one of this module's three axis bases works out to the
 * NEGATION of `orthoBasis`'s own `right` (confirmed live: dragging right visibly panned the wrong
 * way -- bug report item 5). `makeBasis` pins local +X/+Y/+Z to `right`/`up`/`-forward` (a camera
 * looks down its local -Z) exactly, so the rendered screen-right always matches `orthoBasis.right`. */
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
    const { forward, right, up } = orthoBasis(axis)
    cam.position.set(
      pose.center[0] - forward[0] * ORTHO_HALF_RANGE,
      pose.center[1] - forward[1] * ORTHO_HALF_RANGE,
      pose.center[2] - forward[2] * ORTHO_HALF_RANGE,
    )
    _xAxis.set(right[0], right[1], right[2])
    _yAxis.set(up[0], up[1], up[2])
    _zAxis.set(-forward[0], -forward[1], -forward[2])
    _basis.makeBasis(_xAxis, _yAxis, _zAxis)
    cam.quaternion.setFromRotationMatrix(_basis)
    const halfW = (size.width / 2) * pose.worldUnitsPerPixel
    const halfH = (size.height / 2) * pose.worldUnitsPerPixel
    cam.left = -halfW
    cam.right = halfW
    cam.top = halfH
    cam.bottom = -halfH
    cam.near = 0.1
    cam.far = ORTHO_HALF_RANGE * 2
    cam.updateProjectionMatrix()
  })
  return null
}

export interface OrthoViewportProps {
  axis: OrthoAxis
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // `F`-frame (Part 3, Task 15): a new (higher `seq`) request recenters `pose.center` on the bbox
  // and fits its extent on THIS axis's screen plane.
  frameRequest?: FrameRequest | null
  // Per-pane shading mode (Part 4, Task 20): 'wireframe' draws ONLY the CSG-colored brush rings (no
  // solid mesh) -- ortho's own long-standing default, see below; the other three draw the mesh too.
  mode?: ShadingMode
  // Grid visibility (Part 8, Task 28) -- a single toggle for all three ortho panes, owned by
  // QuadLayout, not a per-pane preference (classic level editors have one "show grid" switch).
  showGrid?: boolean
}

const SELECTION_BOX_COLOR = 0x00e5ff
// Leaves a visible margin around the framed bbox rather than filling the pane edge-to-edge.
const FRAME_FIT_MARGIN = 0.9

export function OrthoViewport({
  axis,
  selectedNames,
  onSelectActor,
  frameRequest = null,
  mode = 'wireframe',
  showGrid = true,
}: OrthoViewportProps) {
  const [pose, setPose] = useState<OrthoPose>(initialOrthoPose)
  // The cursor's projected world-space (UU) position, for the coordinate readout (Task 28) -- null
  // when the pointer hasn't moved inside this pane yet (or has left it).
  const [hoverWorld, setHoverWorld] = useState<Vec3 | null>(null)
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors, actors } =
    useSceneResourcesContext()
  // See Viewport3D.tsx's identical comment: 'unlit'/'lit' otherwise render the same mesh.
  const activeMaterials = mode === 'unlit' ? unlitMaterials : materials
  // Every SELECTED non-brush actor's AABB box (Task 14: one per selected actor) -- mirrors
  // Viewport3D's identical `selectedNonBrushBoxes`.
  const selectedNonBrushBoxes = useMemo(() => {
    return actors
      .filter((a) => selectedNames.has(a.name) && !a.brush)
      .map((a) => ({ name: a.name, box: new THREE.Box3(new THREE.Vector3(...a.bbox_lo), new THREE.Vector3(...a.bbox_hi)) }))
  }, [actors, selectedNames])
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const markerGroupRef = useRef<THREE.Group | null>(null)
  // Wireframe-mode click-to-select (bug report item 6): see Viewport3D.tsx's identical comment --
  // with no solid mesh drawn, a hit must come from the brush outline LINES themselves, never a
  // bounding-box fallback.
  const brushGroupRef = useRef<THREE.Group | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Shared by the tap path: raycasts the click point against the drawn geometry (main mesh via
  // triangleOwners, marker sprites via their own userData) -- the exact primary/fallback strategy
  // Viewport3D's performTapSelect uses, with the real ortho THREE.Camera (three.js's Raycaster
  // handles an orthographic camera's parallel rays the same way it handles a perspective one's).
  const performTapSelect = useCallback(
    (clientX: number, clientY: number, additive: boolean) => {
      const camera = cameraRef.current
      const rect = containerRef.current?.getBoundingClientRect()
      if (!camera || !rect) return
      const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)
      // See Viewport3D.tsx's identical comment (bug report item 6): a click in wireframe/ortho views
      // must only hit near a brush's own outline, never anywhere inside its silhouette.
      raycaster.params.Line = { threshold: 4 }
      raycaster.params.Line2 = { threshold: 6 }

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
            hitActor = resolveHitActor(hit.faceIndex, triangleOwners, actors)
          } else if (hit.object.userData.segmentOwners) {
            const segmentOwners = hit.object.userData.segmentOwners as (string | null)[]
            hitActor = resolveSegmentHitActor(hit.index, segmentOwners, actors)
          } else {
            const name = hit.object.userData.actorName as string | undefined
            hitActor = name ? (actors.find((a) => a.name === name) ?? null) : null
          }
        }
      }
      if (!hitActor) {
        const ray: Ray = {
          origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
          direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
        }
        // Never AABB-select a brush in wireframe mode (item 6) -- only its own outline lines, just
        // raycast above, may hit it there.
        const aabbCandidates = mode === 'wireframe' ? actors.filter((a) => !a.brush) : actors
        hitActor = pickActor(ray, aabbCandidates)
      }
      const result = resolveTapSelection(hitActor, additive)
      if (result) onSelectActor(result.name, result.additive)
    },
    [actors, triangleOwners, onSelectActor, mode],
  )

  const dragCallbacks = useMemo<DragGestureCallbacks>(
    () => ({
      onDrag: (dx, dy, buttons) => {
        setPose((prev) => {
          // Both mouse buttons together: zoom (dy-driven), matching the main spec's ortho "Camera"
          // paragraph ("drag-pan + both-button-drag zoom"); a plain single-button drag pans. Ortho
          // marquee-select (plain LMB-drag, classic UnrealEd) is explicitly deferred -- see
          // dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/.
          if ((buttons & 1) !== 0 && (buttons & 2) !== 0) return orthoZoom(prev, dy)
          return orthoPan(prev, axis, dx, dy)
        })
      },
      onTap: (clientX, clientY, additive) => performTapSelect(clientX, clientY, additive),
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
  // out yet (a `getBoundingClientRect()` of 0x0 would otherwise divide by zero).
  useEffect(() => {
    if (!frameRequest) return
    const center = bboxCenter(frameRequest.bbox)
    const { right, up } = orthoBasis(axis)
    const size: [number, number, number] = [
      frameRequest.bbox.hi[0] - frameRequest.bbox.lo[0],
      frameRequest.bbox.hi[1] - frameRequest.bbox.lo[1],
      frameRequest.bbox.hi[2] - frameRequest.bbox.lo[2],
    ]
    const extentAlong = (dir: [number, number, number]) =>
      Math.abs(dir[0] * size[0]) + Math.abs(dir[1] * size[1]) + Math.abs(dir[2] * size[2])
    const screenW = Math.max(extentAlong(right), 1)
    const screenH = Math.max(extentAlong(up), 1)
    const rect = containerRef.current?.getBoundingClientRect()
    const viewW = rect && rect.width > 0 ? rect.width : 800
    const viewH = rect && rect.height > 0 ? rect.height : 600
    const worldUnitsPerPixel = Math.max(screenW / (viewW * FRAME_FIT_MARGIN), screenH / (viewH * FRAME_FIT_MARGIN))
    setPose({ center, worldUnitsPerPixel })
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
        {selectedNonBrushBoxes.map(({ name, box }) => (
          <box3Helper key={name} args={[box, SELECTION_BOX_COLOR]} />
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

