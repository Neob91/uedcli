// Vertex + pivot markers for a selected brush (bug report item 7) -- ports `actor diagram
// --highlight`'s `_draw_vertex_dot`/`_draw_pivot_marker` (uedcli/preview.py, ~lines 597-611) to the
// GUI: a small square dot at every poly vertex, in the brush's own brightened wire color. A second
// dot, same square glyph, marks the brush's PrePivot-shifted "local origin"
// (`BrushHighlight.local_origin`, `Location - R·PrePivot`, computed server-side the same way
// `preview.py` does). It renders once per selected brush, same as the vertex dots -- UED22's
// `DrawLevelBrush` draws it for every highlighted brush, not just one (see `preview.py`'s
// `_scene_geometry`, `is_hi_actor`).
//
// The pivot cross is a different thing entirely and is deliberately NOT per-brush: real UED22 draws
// exactly ONE, from a single global pivot location, anchored to whichever actor was most recently
// the SOLE selection, and only when that actor snaps to the grid. See GUI-PARITY.md "Pivot-cross ...
// Part 4" for the disassembly + live capture, and `selectionSet.ts`'s `pivotAnchor`.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { worldUnitsPerPixelAt } from './markers'
import { pivotAnchor } from './selectionSet'
import { resolveWireColor, scaleColor, toThreeColor } from './selectionColor'

// UED22 draws the global pivot cross in `C_BrushWire` -- the SAME FColor member (UEditorEngine
// +0x1ac) its builder brush uses, `(255,63,63)` in our own `uned/UED22/unrealtournament.ini`.
// Confirmed by disassembly of our own `Editor.dll` and by reading the literal pixels out of a live
// UED22 render (GUI-PARITY.md).
const PIVOT_RED = new THREE.Color(255 / 255, 63 / 255, 63 / 255)

// Both the vertex/local-origin dots and the pivot marker are gizmos, not geometry markers -- board
// item `vertex-handles-should-be-screen-size-constant`: they must hold a constant SCREEN size
// regardless of zoom/distance, like PivotMarker below (see its own doc comment for the mechanism).
// 📖 GUI-PARITY.md "Vertex handle screen size": UED22 itself (`UnEdRend.cpp`'s `DrawLevelBrush`)
// confirms this is genuinely how the real editor draws vertex handles -- and confirms the exact
// mechanism (project the vertex to 2D, then draw a fixed-size 2D screen dot via `Draw2DPoint`, no
// distance falloff at all) -- but its own literal size (a ~2px dot) is tuned for a low-res 1990s
// software renderer and would be barely visible on a modern high-DPI canvas; `VERTEX_DOT_SCREEN_PX`
// is a practical modern size, not a copy of UED22's literal pixel count (see that doc for detail).
const VERTEX_DOT_SCREEN_PX = 6
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

/** The one global pivot gizmo -- constant SCREEN size regardless of zoom/distance (bug report:
 * "pivot's size should be the same on screen, regardless of zoom"), which is also what UED22 does
 * (it projects the pivot to 2D and draws three fixed-size `Draw2DPoint`s). Rescales its own sprite
 * every frame from the live camera/viewport state rather than using a fixed world-unit `scale`. */
function PivotMarker({ position, texture }: { position: [number, number, number]; texture: THREE.Texture | null }) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const { camera, size } = useThree()
  const worldPos = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    const sprite = spriteRef.current
    if (!sprite) return
    // `position` is LOCAL to this sprite's parent chain, which includes the world-handedness
    // mirror group (`<group scale={[1,-1,1]}>` in Viewport3D/OrthoViewport) -- but `camera` sits
    // OUTSIDE that group, already in real world space (its own pose is reflected separately by
    // `applyCameraPose`). Building the distance from the raw local `position` mixed camera
    // world-space against marker local-space, silently wrong by the group's Y-flip -- the huge (or
    // occasionally tiny) pivot bug in the perspective pane specifically (invisible in ortho, since
    // ortho's branch of `worldUnitsPerPixelAt` never uses `point`/distance at all). Read the
    // sprite's own resolved WORLD position instead -- three.js has already applied every parent
    // transform (including the mirror) to it, correct regardless of which group structure this
    // sits inside.
    sprite.getWorldPosition(worldPos)
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

/** A vertex or local-origin handle dot for a selected brush -- constant SCREEN size regardless of
 * zoom/distance, same mechanism as `PivotMarker` above (see its doc comment for why the sprite is
 * rescaled every frame from live camera/viewport state instead of a fixed world-unit `scale`). */
function VertexDot({ position, color, renderOrder }: { position: [number, number, number]; color: THREE.Color; renderOrder: number }) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const { camera, size } = useThree()
  const worldPos = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    const sprite = spriteRef.current
    if (!sprite) return
    sprite.getWorldPosition(worldPos)
    const scale = VERTEX_DOT_SCREEN_PX * worldUnitsPerPixelAt(camera, worldPos, size.height)
    sprite.scale.set(scale, scale, 1)
  })
  return (
    <sprite ref={spriteRef} position={position} renderOrder={renderOrder}>
      <spriteMaterial color={color} depthTest={false} />
    </sprite>
  )
}

export interface SelectionMarkersProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
}

/** Renders vertex-handle dots for every SELECTED brush actor (one full set per actor, matching
 * `preview.py`'s per-`--highlight`ed-actor loop), plus ONE pivot cross for the whole selection.
 * Non-brush actors already get their own color-tint highlight elsewhere
 * (`ActorSelectionHighlight`/sprite tint in Viewport3D/OrthoViewport) -- out of scope here. */
export function SelectionMarkers({ actors, selectedNames }: SelectionMarkersProps) {
  const pivotTexture = usePivotTexture()
  const selectedBrushes = useMemo(
    () => actors.filter((a): a is SceneActor & { brush: NonNullable<SceneActor['brush']> } => selectedNames.has(a.name) && a.brush != null),
    [actors, selectedNames],
  )
  // The ONE global pivot cross. Anchor = the actor that was most recently the sole selection
  // (`pivotAnchor`). Shown only when that actor SNAPS TO THE GRID: UED22's own visibility test is
  // `GPivotShown = (SnapCount > 0) || (Count > 1)`, where `SnapCount` counts selected actors whose
  // `bEdShouldSnap` is set. Exactly two classes in `uned/UED22`'s packages default it True --
  // `Engine.Brush` and `Engine.ClipMarker` (an editor-only clip-plane marker this GUI never renders)
  // -- so "is a brush" is the stand-in here. Live-verified in real UED22: a lone selected brush
  // shows the cross; a lone selected Light shows nothing. The `Count > 1` term never fires from
  // clicking alone, because UED22 recomputes the flag only at exactly one selected actor -- also
  // live-verified (three Lights selected: still no cross). Detail: GUI-PARITY.md.
  const pivotBrush = useMemo(() => {
    const anchor = pivotAnchor(selectedNames)
    if (anchor === undefined) return null
    return actors.find((a) => a.name === anchor && a.brush != null) ?? null
  }, [actors, selectedNames])

  return (
    <group>
      {pivotBrush && <PivotMarker position={pivotBrush.location} texture={pivotTexture} />}
      {selectedBrushes.map((actor) => {
        // Real UED22: a brush's vertex-handle dots are `VertexColor = WireColor * 1.2`
        // (`UnEdRend.cpp`'s `DrawLevelBrush`, `selectionColor.ts`'s doc comment) -- always this,
        // regardless of selection (vertex dots only ever draw on a selected brush here anyway).
        const color = toThreeColor(scaleColor(resolveWireColor(actor.brush.csg_class, actor.brush.color), 1.2))
        const verts: [number, number, number][] = []
        for (const poly of actor.brush.polys) {
          for (let i = 0; i + 2 < poly.length; i += 3) {
            verts.push([poly[i], poly[i + 1], poly[i + 2]])
          }
        }
        return (
          <group key={actor.name}>
            {verts.map((v, i) => (
              <VertexDot key={i} position={v} color={color} renderOrder={VERTEX_DOT_RENDER_ORDER} />
            ))}
            <VertexDot position={actor.brush.local_origin} color={color} renderOrder={VERTEX_DOT_RENDER_ORDER} />
          </group>
        )
      })}
    </group>
  )
}
