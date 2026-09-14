// R3F perspective viewport: draws the scene payload's polys textured+unlit through the atlas
// (MeshBasicMaterial -- no lights, no lightmap; Slice 2 turns build_scene's carried `lightmap`
// field into the lit shading mode), owns the faithful UnrealEd drag-fly camera (spec, "Camera"),
// and click-to-select (spec, "Selection & inspector"). This is the ONLY place model data meets
// three.js -- Viewport3D draws what `serve` hands it and owns no model/diff/solve logic of its
// own (spec, "The client").
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  MouseEvent as ReactMouseEvent,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { AtlasPayload, ScenePayload } from '../api'
import type { CameraPose, Vec3 } from './camera'
import { cameraBasis, dollyAndTurn, look, orbit, pan, zoom } from './camera'
import { buildGeometryData } from './geometry'
import { isTap, pickActor } from './selection'
import type { Ray } from './selection'

const INITIAL_POSE: CameraPose = { position: [0, -500, 200], pitch: -10, yaw: 90 }

/** Loads the atlas PNG into a `THREE.Texture`, disposing the PREVIOUSLY committed texture once a
 * new one replaces it (every live-reload swaps `atlas`, so without this every reload cycle leaked
 * one full-size GPU texture -- review finding). `currentRef` tracks what's actually live (in state
 * or in flight); an unmount (or a load that lost the race) disposes through it too. */
function useAtlasTexture(atlas: AtlasPayload): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  const currentRef = useRef<THREE.Texture | null>(null)

  useEffect(() => {
    let disposed = false
    const loader = new THREE.TextureLoader()
    loader.load(`data:image/png;base64,${atlas.png_base64}`, (tex) => {
      if (disposed) {
        tex.dispose()
        return
      }
      tex.magFilter = THREE.NearestFilter
      tex.minFilter = THREE.NearestFilter
      tex.flipY = false // our atlas UVs are computed image-row-style (y grows downward)
      tex.needsUpdate = true
      currentRef.current?.dispose()
      currentRef.current = tex
      setTexture(tex)
    })
    return () => {
      disposed = true
    }
  }, [atlas.png_base64])

  useEffect(() => {
    return () => {
      currentRef.current?.dispose() // unmount: release whatever texture is still held
      currentRef.current = null
    }
  }, [])

  return texture
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

function SelectionHighlight({ box }: { box: THREE.Box3 | null }) {
  if (!box) return null
  return <box3Helper args={[box, 0x00e5ff]} />
}

export interface Viewport3DProps {
  scene: ScenePayload
  atlas: AtlasPayload
  selectedName?: string | null
  onSelectActor?: (name: string | null) => void
}

interface DragTracker {
  startX: number
  startY: number
  lastX: number
  lastY: number
}

export function Viewport3D({ scene, atlas, selectedName = null, onSelectActor }: Viewport3DProps) {
  const [pose, setPose] = useState<CameraPose>(INITIAL_POSE)
  const drag = useRef<DragTracker | null>(null)
  const cameraRef = useRef<THREE.Camera | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const texture = useAtlasTexture(atlas)

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

  const bufferGeometry = useMemo(() => {
    const built = buildGeometryData(scene.polys, atlas)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(built.positions, 3))
    geo.setAttribute('uv', new THREE.BufferAttribute(built.uvs, 2))
    geo.clearGroups()
    if (built.groups.nonMasked.count > 0) {
      geo.addGroup(built.groups.nonMasked.start, built.groups.nonMasked.count, 0)
    }
    if (built.groups.masked.count > 0) {
      geo.addGroup(built.groups.masked.start, built.groups.masked.count, 1)
    }
    geo.computeVertexNormals()
    return geo
  }, [scene, atlas])

  // Every live-reload replaces `bufferGeometry`/`materials` with fresh THREE objects; without an
  // explicit dispose the PREVIOUS ones (a full geometry buffer, two materials) leak every cycle
  // (review finding). The cleanup closes over the value from the render it belongs to, so it
  // always disposes the one being REPLACED, and disposes the final one on unmount too.
  useEffect(() => {
    return () => bufferGeometry.dispose()
  }, [bufferGeometry])

  const materials = useMemo(() => {
    const plain = new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide })
    const masked = new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide,
      alphaTest: 0.5,
    })
    return [plain, masked]
  }, [texture])

  useEffect(() => {
    return () => materials.forEach((m) => m.dispose())
  }, [materials])

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = { startX: e.clientX, startY: e.clientY, lastX: e.clientX, lastY: e.clientY }
    e.currentTarget.setPointerCapture(e.pointerId)
  }, [])

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const d = drag.current
      if (!d) return
      const dx = e.clientX - d.lastX
      const dy = e.clientY - d.lastY
      d.lastX = e.clientX
      d.lastY = e.clientY
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
      const d = drag.current
      drag.current = null
      if (!d || e.button !== 0 || e.altKey) return
      if (!isTap(d.startX, d.startY, e.clientX, e.clientY)) return // a real drag, not a selection tap

      const camera = cameraRef.current
      const rect = containerRef.current?.getBoundingClientRect()
      if (!camera || !rect) return
      const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)
      const ray: Ray = {
        origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
        direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
      }
      const hit = pickActor(ray, scene.actors)
      onSelectActor?.(hit ? hit.name : null)
    },
    [scene.actors, onSelectActor],
  )

  const onWheel = useCallback((e: ReactWheelEvent<HTMLDivElement>) => {
    setPose((prev) => zoom(prev, e.deltaY))
  }, [])

  const onContextMenu = useCallback((e: ReactMouseEvent<HTMLDivElement>) => e.preventDefault(), [])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      onContextMenu={onContextMenu}
    >
      <Canvas>
        <CameraRig pose={pose} cameraRef={cameraRef} />
        {texture && <mesh geometry={bufferGeometry} material={materials} />}
        <SelectionHighlight box={selectionBox} />
      </Canvas>
    </div>
  )
}
