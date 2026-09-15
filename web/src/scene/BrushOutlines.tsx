// CSG-colored brush wireframe rings (quad-layout Part 2, Task 10): the shared rendering piece both
// Perspective and ortho panes draw from buildBrushRings' pure logic (Task 9). Non-bold rings use the
// cheap LineLoop/LineBasicMaterial path (a 1px-only line is fine -- they don't need to stand out).
//
// Bold (selected) rings use Line2/LineMaterial (`three/examples/jsm/lines`, already inside the
// pinned `three` package -- a deeper import path, NOT a new npm dependency) instead of
// `LineBasicMaterial`'s own `linewidth`. Per the spec's own review finding: WebGL, via ANGLE/OpenGL
// Core Profile on virtually every desktop browser, ignores `LineBasicMaterial.linewidth` above 1px
// (matching three.js's own documented limitation almost verbatim) -- a straightforward
// `linewidth={3}` port would very likely render the "bolder" selected ring at the exact same 1px
// weight as every other ring, silently failing the "matches `actor diagram`" requirement's bolder-
// line half.
//
// Step A (a real-browser visual comparison confirming the selected ring is VISIBLY thicker) could
// NOT be run in this build environment -- no Chromium-family browser was available in this sandbox
// (confirmed: no chromium/chromium-browser/google-chrome binary, no committed headless-browser
// harness in this worktree). Given the underlying fact is well-established platform behavior, not a
// coin flip, Step B's fix is applied PREEMPTIVELY here rather than shipping a change whose "bolder"
// half is very likely a silent no-op. Flagged in the build report for a real-browser confirmation
// before merge -- Task 10's own Step A is not considered done, only its Step B fallback.
import { useEffect, useMemo } from 'react'
import type { MutableRefObject } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'

import type { SceneActor } from '../api'
import type { BrushRing, BrushRingMode } from './brushRings'
import { buildBrushRings, mergeThinRings } from './brushRings'

// `preview.py`'s `_line(..., weight=2, ...)` is the actual highlighted-edge width `actor diagram`
// renders (bug report item 8) -- this was 3, visibly bolder than that reference.
const BOLD_LINEWIDTH_PX = 2

/** `Line2`/`LineGeometry` draw an open polyline, not an automatically-closed loop (unlike
 * `THREE.LineLoop`) -- append the first vertex again at the end to close the ring. */
function closedLoopPositions(verts: number[]): number[] {
  if (verts.length < 3) return verts
  return [...verts, verts[0], verts[1], verts[2]]
}

/** Every ordinary-weight (non-selected) ring, merged into ONE `LineSegments` draw call (bug report
 * item 4 -- see `mergeThinRings`' docstring for the measured cost this replaces). Per-vertex color
 * reproduces each ring's own CSG hue; `userData.segmentOwners` lets the outer viewport's raycast
 * resolve a hit segment back to its owning actor (Viewport3D/OrthoViewport's `performTapSelect`),
 * the same role `userData.actorName` plays on a single-actor object like `BoldRing`. */
function MergedThinWireframe({ rings }: { rings: BrushRing[] }) {
  const merged = useMemo(() => mergeThinRings(rings), [rings])
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(merged.positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(merged.colors, 3))
    return geo
  }, [merged])
  useEffect(() => () => geometry.dispose(), [geometry])
  if (merged.segmentOwners.length === 0) return null
  return (
    <lineSegments geometry={geometry} userData={{ segmentOwners: merged.segmentOwners }}>
      <lineBasicMaterial vertexColors />
    </lineSegments>
  )
}

/** The bold (selected) ring path: real pixel-width via `Line2`/`LineMaterial`'s `resolution`
 * uniform, which must track the canvas's own pixel size on resize -- the real added-complexity cost
 * this task's Step B warns about. `depthTest={false}` matches the pre-existing selection-highlight
 * look (always-on-top, matching `preview.py --highlight`'s "ignores facing/depth"). */
function BoldRing({ verts, color, actorName }: { verts: number[]; color: THREE.Color; actorName: string }) {
  const { size } = useThree()
  const geometry = useMemo(() => {
    const geo = new LineGeometry()
    geo.setPositions(closedLoopPositions(verts))
    return geo
  }, [verts])
  const material = useMemo(
    () => new LineMaterial({ color: color.getHex(), linewidth: BOLD_LINEWIDTH_PX, depthTest: false, transparent: false }),
    [color],
  )
  useEffect(() => {
    material.resolution.set(size.width, size.height)
  }, [material, size.width, size.height])
  useEffect(
    () => () => {
      geometry.dispose()
      material.dispose()
    },
    [geometry, material],
  )
  const line = useMemo(() => {
    const l = new Line2(geometry, material)
    l.userData = { actorName }
    return l
  }, [geometry, material, actorName])
  return <primitive object={line} />
}

export interface BrushOutlinesProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
  mode: BrushRingMode
  // Exposes the rendered ring objects for the outer viewport's click-to-select raycast (bug report
  // item 6: in wireframe/ortho views, a click must only hit a brush's own outline LINES, never
  // anywhere inside its silhouette) -- mirrors Viewport3D/OrthoViewport's existing `markerGroupRef`
  // pattern for marker sprites.
  groupRef?: MutableRefObject<THREE.Group | null>
}

/** Renders every ring `buildBrushRings` selects for `mode` -- ordinary weight for every non-selected
 * brush (`'csg-all'`) or nothing (`'selected-only'` when unselected), bold for every SELECTED one
 * (Part 3, Task 14: one ring per selected actor, not just one overall). Non-bold rings share ONE
 * merged draw call (`MergedThinWireframe`, item 4); bold (selected) rings stay individual `BoldRing`
 * objects -- there are only ever a handful of those, so merging them buys nothing and would lose
 * `Line2`'s real pixel-width support. */
export function BrushOutlines({ actors, selectedNames, mode, groupRef }: BrushOutlinesProps) {
  const rings = useMemo(() => buildBrushRings(actors, selectedNames, mode), [actors, selectedNames, mode])
  const boldRings = useMemo(() => rings.filter((r) => r.bold), [rings])
  const thinRings = useMemo(() => rings.filter((r) => !r.bold), [rings])
  return (
    <group ref={groupRef}>
      <MergedThinWireframe rings={thinRings} />
      {boldRings.map((ring, i) => {
        const color = new THREE.Color(ring.color[0] / 255, ring.color[1] / 255, ring.color[2] / 255)
        return <BoldRing key={`${ring.actorName}-${i}`} verts={ring.verts} color={color} actorName={ring.actorName} />
      })}
    </group>
  )
}
