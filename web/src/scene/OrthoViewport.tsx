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
import { DEFAULT_GRID_SIZE } from './grid'
import { GridOverlay } from './GridOverlay'
import { DEFAULT_MARKER_FOOTPRINT_UU, MARKER_COLOR } from './markers'
import { MeshWireframe, SelectedMeshWireframe } from './MeshWireframe'
import { PointActorMarker } from './PointActorMarker'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { initialOrthoPose, orthoDragZoom, orthoFrameFit, orthoLineHitThresholdUU, orthoPan, orthoZoom, screenToWorld } from './orthoCamera'
import { RadiiOverlays } from './RadiiOverlays'
import { useSceneResourcesContext } from './useSceneResourcesContext'
import { ActorSelectionHighlight, SurfaceSelectionHighlight } from './SelectionHighlight'
import { SELECTED_SPRITE_TINT, UNSELECTED_SPRITE_TINT } from './selectionColor'
import { SelectionMarkers } from './SelectionMarkers'
import { resolveTapSelect } from './tapSelect'
import type { ShadingMode } from './shadingMode'
import { usesUnlitMaterials } from './shadingMode'
// `THREE.ColorManagement.enabled` is a process-wide singleton r3f reasserts on every render of
// EVERY mounted Canvas (viewportRender.ts's own `CANVAS_COLOR_MANAGEMENT` doc comment) -- this
// pane's Canvas MUST spread the identical constant, or the two fight over that global flag on every
// shared re-render (constant in the quad layout), silently breaking Viewport3D's fix too.
import { applyOrthoCameraPose, CANVAS_COLOR_MANAGEMENT } from './viewportRender'

// Same fallback dot tint as Viewport3D's identical marker rendering.
const MARKER_COLOR_THREE = new THREE.Color(...MARKER_COLOR)
// Point actors must always render on top of brush wireframe/highlight (owner ruling; Viewport3D.tsx
// sets the identical depthTest={false} on its own marker materials for the same reason -- a wall-
// mounted actor's Location often coincides with the wall surface, so depth-testing lost that marker
// to the wall's own geometry). This pane ALSO needs an explicit renderOrder, higher than everything
// else drawn here (grid's -10, brush outlines' default 0), so draw order is explicit rather than
// incidental scene-graph position; Viewport3D.tsx leaves its own marker renderOrder unset since its
// scene-graph insertion order already draws markers last.
const MARKER_RENDER_ORDER = 10

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
  // Surface (single-polygon texture) selection -- see Viewport3D.tsx's identical prop doc. Ortho
  // panes are always wireframe (no solid mesh drawn), so a surface hit never actually occurs here in
  // practice; threaded through anyway so this pane shares the exact same tap-resolution pipeline as
  // Viewport3D.tsx rather than special-casing itself out of it.
  selectedSurfaces: ReadonlySet<string>
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
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
  // The escalation algorithm's base/minimum step (dev/docs/GUI.md "The world-anchored grid") --
  // UnrealEd's own persistent "Grid Size" preference, owned by QuadLayout's dropdown, one value for
  // all three ortho panes (not per-pane, matching showGrid's convention).
  baseGridSize?: number
  // Collision-cylinder / light-radius overlay toggle -- one switch for every pane (QuadLayout),
  // mirroring showGrid's convention; default off. Scoped to the current selection (owner ruling
  // 2026-09-15) -- on shows only the selected actor(s)' radii, not every actor's.
  showRadii?: boolean
}

export function OrthoViewport({
  axis,
  selectedNames,
  onSelectActor,
  selectedSurfaces,
  onSelectSurface,
  onDeselect,
  frameRequest = null,
  mode = 'wireframe',
  showGrid = true,
  baseGridSize = DEFAULT_GRID_SIZE,
  showRadii = false,
}: OrthoViewportProps) {
  const [pose, setPose] = useState<OrthoPose>(initialOrthoPose)
  // The cursor's projected world-space (UU) position, for the coordinate readout (Task 28) -- null
  // when the pointer hasn't moved inside this pane yet (or has left it).
  const [hoverWorld, setHoverWorld] = useState<Vec3 | null>(null)
  const {
    bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
    meshWireframeGeometry, meshPickGeometry, meshTriangleOwners, meshTrianglePolyIndex,
    textures, markerTexture, markerActors, actors,
  } = useSceneResourcesContext()
  const activeMaterials = usesUnlitMaterials(mode) ? unlitMaterials : materials
  // Selected non-brush (sprite/mesh) actor names -- drives the UED22-matched color-tint highlight
  // below (GUI-PARITY.md "Selection highlight rendering"), shared with Viewport3D.tsx's identical
  // computation (item 16 dedup candidate, not pulled out yet -- small enough to duplicate for now).
  const selectedNonBrushNames = useMemo(
    () => new Set(actors.filter((a) => !a.brush && selectedNames.has(a.name)).map((a) => a.name)),
    [actors, selectedNames],
  )
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const meshPickRef = useRef<THREE.Mesh | null>(null)
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
        meshPickObject: meshPickRef.current,
        meshTriangleOwners,
        meshTrianglePolyIndex,
        markerObjects: markerGroupRef.current?.children ?? [],
        brushObjects: mode === 'wireframe' ? (brushGroupRef.current?.children ?? []) : [],
        actors,
        triangleOwners,
        trianglePolyIndex,
      })
      if (action.kind === 'select-actor') onSelectActor(action.name, action.additive)
      else if (action.kind === 'select-surface') onSelectSurface(action.actor, action.polyIndex, action.additive)
      else if (action.kind === 'deselect') onDeselect()
    },
    [actors, triangleOwners, trianglePolyIndex, meshTriangleOwners, meshTrianglePolyIndex, onSelectActor, onSelectSurface, onDeselect, mode, pose.worldUnitsPerPixel],
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
        {/* All world content reflected by R = diag(1,-1,1) -- the left-handed-world handedness fix
            (applyOrthoCameraPose reflects the camera pose by the same R). See Viewport3D's note. */}
        <group scale={[1, -1, 1]}>
        {showGrid && <GridOverlay pose={pose} axis={axis} baseGridSize={baseGridSize} />}
        {mode !== 'wireframe' && <mesh ref={meshRef} geometry={bufferGeometry} material={activeMaterials} />}
        {/* A selected whole brush is shown as a selected ACTOR (bold brightened outline + markers),
            not by lighting up its faces -- see Viewport3D's note. Only a single-face pick lights one poly: */}
        {/* Texture (single-surface) selection highlight -- see Viewport3D.tsx's identical block
            (never actually visible here in practice: ortho panes are always wireframe). */}
        {mode !== 'wireframe' && (
          <SurfaceSelectionHighlight
            bufferGeometry={bufferGeometry}
            triangleOwners={triangleOwners}
            trianglePolyIndex={trianglePolyIndex}
            selectedSurfaces={selectedSurfaces}
            materials={activeMaterials}
          />
        )}
        {/* A selected mesh actor lights up in UED22's own measured color -- see Viewport3D.tsx's
            identical block (GUI-PARITY.md "Selection highlight rendering"). */}
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
            // A resolved DT_Sprite billboard draws the actor's REAL class icon at its own
            // world-space footprint, untinted -- mirrors Viewport3D's identical priority (real
            // sprite over the generic dot). Part 5, Task 21's verification found this branch (and
            // the fallback's scale/tint below) missing here entirely: an un-scaled default THREE.
            // Sprite is 1x1 UU, effectively invisible in a world scaled in hundreds/thousands of UU.
            const spriteTex = actor.sprite ? textures.sprite.get(actor.sprite.tex_index) : undefined
            const isSelected = selectedNames.has(actor.name)
            if (actor.sprite && spriteTex) {
              return (
                <PointActorMarker
                  key={actor.name}
                  position={actor.location}
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
                position={actor.location}
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
        {/* Every brush wireframes in its own CSG colour (`actor diagram`'s ISO-mode convention,
            spec §2), selected one(s) bold -- the whole picture in wireframe mode (no solid mesh
            above); just the highlight ring on top of the mesh in any other mode (Part 4, Task 20). */}
        <BrushOutlines
          actors={actors}
          selectedNames={selectedNames}
          mode={mode === 'wireframe' ? 'csg-all' : 'selected-only'}
          groupRef={brushGroupRef}
        />
        {/* Ortho panes are always wireframe -- a mesh actor draws its own triangle-edge wireframe
            here, matching a brush's wireframe convention (GUI.md "Shading modes"), instead of the
            solid mesh above (never drawn in this pane). */}
        {mode === 'wireframe' && <MeshWireframe geometry={meshWireframeGeometry} />}
        {mode === 'wireframe' && (
          <SelectedMeshWireframe
            positions={meshPickGeometry.attributes.position.array as Float32Array}
            triangleOwners={meshTriangleOwners}
            selectedActorNames={selectedNonBrushNames}
          />
        )}
        {/* Invisible raycast target so a DT_Mesh actor is click-selectable in this pane (no solid mesh
            drawn here). See tapSelect.ts / SceneResourcesContext. */}
        <mesh ref={meshPickRef} geometry={meshPickGeometry}>
          <meshBasicMaterial visible={false} />
        </mesh>
        {/* Vertex + pivot markers for a selected brush (bug report item 7). */}
        <SelectionMarkers actors={actors} selectedNames={selectedNames} />
        {/* Collision-cylinder / light-radius overlays, toggled globally but scoped to the current
            selection (owner ruling 2026-09-15) -- draws nothing when nothing is selected. */}
        {showRadii && <RadiiOverlays actors={actors} view={axis} selectedNames={selectedNames} />}
        </group>
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

