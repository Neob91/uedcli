// Vertex + pivot markers for a selected brush (bug report item 7) -- ports `actor diagram
// --highlight`'s `_draw_vertex_dot`/`_draw_pivot_marker` (uedcli/preview.py, ~lines 597-611) to the
// GUI: a small square dot at every poly vertex, in the brush's own brightened wire color, plus a
// distinct marker at the actor's true pivot (`Location`). A third dot, same square glyph as the poly
// vertices, marks the brush's PrePivot-shifted "local origin" (`BrushHighlight.local_origin`,
// `Location - R·PrePivot`, computed server-side the same way `preview.py` does) -- coincides with
// the pivot only when PrePivot is zero. It renders for at most ONE actor even under a multi-selection
// (see `selectionSet.ts`'s `primarySelection`).
import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { worldUnitsPerPixelAt } from './markers'
import { primarySelection } from './selectionSet'
import { brightenWireColor } from './selectionColor'

// Matches `preview.py`'s `_PIVOT_RED`.
const PIVOT_RED = new THREE.Color(255 / 255, 63 / 255, 63 / 255)

// World-unit sizes -- used as-is for the vertex dots (they mark a precise point on already-drawn
// geometry, so a fixed world size is fine there). The pivot marker below is different: bug report
// "pivot's size should be the same on screen, regardless of zoom" -- it's a gizmo, not a geometry
// marker, so it needs constant SCREEN size instead (see PivotMarker).
const VERTEX_DOT_SIZE = 2
const PIVOT_MARKER_SCREEN_PX = 14
// The pivot renders above markers (10) and the selected ring (20) -- always on top, every pane.
const PIVOT_RENDER_ORDER = 40
// Vertex/local-origin dots also render above geometry (markers 10, selected ring 20), below the pivot.
const VERTEX_DOT_RENDER_ORDER = 30

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
    // renderOrder above everything (markers 10, selected ring 20): the pivot of a selected brush must
    // always be visible on top, in every pane and through walls (owner ruling). depthTest=false too.
    <sprite ref={spriteRef} position={position} renderOrder={PIVOT_RENDER_ORDER}>
      <spriteMaterial map={texture ?? undefined} color={PIVOT_RED} depthTest={false} transparent />
    </sprite>
  )
}

export interface SelectionMarkersProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
}

/** Renders vertex + pivot markers for every SELECTED brush actor (one full set per actor, matching
 * `preview.py`'s per-`--highlight`ed-actor loop). Non-brush actors already get their own color-tint
 * highlight elsewhere (`ActorSelectionHighlight`/sprite tint in Viewport3D/OrthoViewport) -- out of
 * scope here. */
export function SelectionMarkers({ actors, selectedNames }: SelectionMarkersProps) {
  const pivotTexture = usePivotTexture()
  const selectedBrushes = useMemo(
    () => actors.filter((a): a is SceneActor & { brush: NonNullable<SceneActor['brush']> } => selectedNames.has(a.name) && a.brush != null),
    [actors, selectedNames],
  )
  const primaryName = useMemo(() => primarySelection(selectedNames), [selectedNames])

  return (
    <group>
      {selectedBrushes.map((actor) => {
        const color = brightenWireColor(actor.brush.color)
        const verts: [number, number, number][] = []
        for (const poly of actor.brush.polys) {
          for (let i = 0; i + 2 < poly.length; i += 3) {
            verts.push([poly[i], poly[i + 1], poly[i + 2]])
          }
        }
        return (
          <group key={actor.name}>
            {verts.map((v, i) => (
              <sprite key={i} position={v} scale={[VERTEX_DOT_SIZE, VERTEX_DOT_SIZE, 1]} renderOrder={VERTEX_DOT_RENDER_ORDER}>
                <spriteMaterial color={color} depthTest={false} />
              </sprite>
            ))}
            {actor.name === primaryName && (
              <sprite position={actor.brush.local_origin} scale={[VERTEX_DOT_SIZE, VERTEX_DOT_SIZE, 1]} renderOrder={VERTEX_DOT_RENDER_ORDER}>
                <spriteMaterial color={color} depthTest={false} />
              </sprite>
            )}
            <PivotMarker position={actor.location} texture={pivotTexture} />
          </group>
        )
      })}
    </group>
  )
}
