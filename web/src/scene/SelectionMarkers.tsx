// Vertex + pivot markers for a selected brush (bug report item 7) -- ports `actor diagram
// --highlight`'s `_draw_vertex_dot`/`_draw_pivot_marker` (uedcli/preview.py, ~lines 597-611) to the
// GUI: a small square dot at every poly vertex, in the brush's own brightened wire color, plus a
// distinct marker at the actor's true pivot (`Location`). `SceneActor` carries no `PrePivot` field
// today, so the separate PrePivot-shifted "local origin" dot preview.py also draws (coincides with
// Location only when PrePivot is zero) is not reproduced -- flagged as a known gap, not silently
// dropped.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { SceneActor } from '../api'

// Matches `preview.py`'s `_PIVOT_RED`.
const PIVOT_RED = new THREE.Color(255 / 255, 63 / 255, 63 / 255)

// World-unit sizes -- used as-is for the vertex dots (they mark a precise point on already-drawn
// geometry, so a fixed world size is fine there). The pivot marker below is different: bug report
// "pivot's size should be the same on screen, regardless of zoom" -- it's a gizmo, not a geometry
// marker, so it needs constant SCREEN size instead (see PivotMarker).
const VERTEX_DOT_SIZE = 6
const PIVOT_MARKER_SCREEN_PX = 14

/** World units per screen pixel at `point`, for either camera kind this app uses -- the constant-
 * screen-size scale factor. Ortho: the frustum height / zoom is already screen-independent of
 * `point`. Perspective: depends on distance to `point` (foreshortening), the standard vFOV-based
 * sprite-scale-compensation formula. */
function worldUnitsPerPixelAt(camera: THREE.Camera, point: THREE.Vector3, viewportHeightPx: number): number {
  if (camera instanceof THREE.OrthographicCamera) {
    return (camera.top - camera.bottom) / camera.zoom / viewportHeightPx
  }
  if (camera instanceof THREE.PerspectiveCamera) {
    const distance = camera.position.distanceTo(point)
    const vFOV = THREE.MathUtils.degToRad(camera.fov)
    return (2 * Math.tan(vFOV / 2) * distance) / viewportHeightPx
  }
  return 1
}

function brighten(rgb: [number, number, number], factor = 1.2): THREE.Color {
  return new THREE.Color(
    Math.min(1, (rgb[0] / 255) * factor),
    Math.min(1, (rgb[1] / 255) * factor),
    Math.min(1, (rgb[2] / 255) * factor),
  )
}

/** A white "+" crosshair over a filled square, drawn once and tinted red via `SpriteMaterial.color`
 * -- mirrors `sceneResources.ts`'s `useMarkerTexture` pattern. Matches `_draw_pivot_marker`: a 4px
 * crosshair plus a 3x3 square, both the same color. Returns null (falls back to a plain colored
 * square sprite) in an environment with no canvas 2D backend, e.g. jsdom under vitest. */
function usePivotTexture(): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  useEffect(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.strokeStyle = 'white'
    ctx.fillStyle = 'white'
    ctx.lineWidth = size / 8
    const c = size / 2
    const arm = size * 0.45
    ctx.beginPath()
    ctx.moveTo(c - arm, c)
    ctx.lineTo(c + arm, c)
    ctx.moveTo(c, c - arm)
    ctx.lineTo(c, c + arm)
    ctx.stroke()
    const sq = size * 0.18
    ctx.fillRect(c - sq / 2, c - sq / 2, sq, sq)
    const tex = new THREE.CanvasTexture(canvas)
    tex.needsUpdate = true
    setTexture(tex)
    return () => tex.dispose()
  }, [])
  return texture
}

/** The pivot gizmo for one selected brush -- constant SCREEN size regardless of zoom/distance (bug
 * report: "pivot's size should be the same on screen, regardless of zoom"). Rescales its own sprite
 * every frame from the live camera/viewport state rather than using a fixed world-unit `scale`. */
function PivotMarker({ position, texture }: { position: [number, number, number]; texture: THREE.Texture | null }) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const { camera, size } = useThree()
  useFrame(() => {
    const sprite = spriteRef.current
    if (!sprite) return
    const worldPos = new THREE.Vector3(...position)
    const scale = PIVOT_MARKER_SCREEN_PX * worldUnitsPerPixelAt(camera, worldPos, size.height)
    sprite.scale.set(scale, scale, 1)
  })
  return (
    <sprite ref={spriteRef} position={position}>
      <spriteMaterial map={texture ?? undefined} color={PIVOT_RED} depthTest={false} transparent />
    </sprite>
  )
}

export interface SelectionMarkersProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
}

/** Renders vertex + pivot markers for every SELECTED brush actor (one full set per actor, matching
 * `preview.py`'s per-`--highlight`ed-actor loop). Non-brush actors already get their own AABB-box
 * highlight elsewhere (`selectedNonBrushBoxes` in Viewport3D/OrthoViewport) -- out of scope here. */
export function SelectionMarkers({ actors, selectedNames }: SelectionMarkersProps) {
  const pivotTexture = usePivotTexture()
  const selectedBrushes = useMemo(
    () => actors.filter((a): a is SceneActor & { brush: NonNullable<SceneActor['brush']> } => selectedNames.has(a.name) && a.brush != null),
    [actors, selectedNames],
  )

  return (
    <group>
      {selectedBrushes.map((actor) => {
        const color = brighten(actor.brush.color)
        const verts: [number, number, number][] = []
        for (const poly of actor.brush.polys) {
          for (let i = 0; i + 2 < poly.length; i += 3) {
            verts.push([poly[i], poly[i + 1], poly[i + 2]])
          }
        }
        return (
          <group key={actor.name}>
            {verts.map((v, i) => (
              <sprite key={i} position={v} scale={[VERTEX_DOT_SIZE, VERTEX_DOT_SIZE, 1]}>
                <spriteMaterial color={color} depthTest={false} />
              </sprite>
            ))}
            <PivotMarker position={actor.location} texture={pivotTexture} />
          </group>
        )
      })}
    </group>
  )
}
